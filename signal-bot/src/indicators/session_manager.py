"""
Session-Aware Trading Engine

Professional traders know WHEN to trade is as important as WHAT to trade.
This module provides:

  - Session detection (Tokyo, London, New York, Sydney)
  - Overlap zones (London-NY = highest liquidity & volatility)
  - Session-pair optimality scoring
  - Kill zones (high-probability entry windows)
  - Weekend gap protection
  - Session volatility expectations

Kill Zones (UTC) — institutional entry windows:
  London Open  :  07:00 – 09:00  (smart money enters)
  NY Open      :  13:00 – 15:00  (highest volume)
  London Close :  15:30 – 16:30  (position squaring)
  Asian Range  :  00:00 – 03:00  (range building for breakout)

Usage:
    sm = SessionManager()
    ctx = sm.get_context('EURUSD')
    # ctx.score_modifier  → +5 to -5 adjustment for confluence
    # ctx.in_kill_zone    → True if inside institutional window
    # ctx.session_quality → 'optimal' | 'acceptable' | 'poor'
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from utils.logger import setup_logger

logger = setup_logger('session_mgr')


# ═════════════════════════════════════════════════════════════════════════════
#  SESSION DEFINITIONS (UTC hours)
# ═════════════════════════════════════════════════════════════════════════════

SESSIONS = {
    'sydney': {
        'open': 22, 'close': 7,
        'peak_start': 0, 'peak_end': 3,
        'pairs': ['AUDUSD', 'NZDUSD', 'AUDJPY'],
        'volatility': 'low',
    },
    'tokyo': {
        'open': 0, 'close': 9,
        'peak_start': 1, 'peak_end': 6,
        'pairs': ['USDJPY', 'EURJPY', 'GBPJPY', 'AUDJPY', 'AUDUSD'],
        'volatility': 'low_medium',
    },
    'london': {
        'open': 7, 'close': 16,
        'peak_start': 7, 'peak_end': 11,
        'pairs': ['EURUSD', 'GBPUSD', 'EURGBP', 'USDCHF', 'XAUUSD',
                  'EURJPY', 'GBPJPY'],
        'volatility': 'high',
    },
    'new_york': {
        'open': 13, 'close': 22,
        'peak_start': 13, 'peak_end': 17,
        'pairs': ['EURUSD', 'GBPUSD', 'USDJPY', 'USDCAD', 'XAUUSD',
                  'USDCHF', 'NZDUSD'],
        'volatility': 'high',
    },
}

# ═════════════════════════════════════════════════════════════════════════════
#  KILL ZONES — institutional high-probability entry windows
# ═════════════════════════════════════════════════════════════════════════════

KILL_ZONES = {
    'london_open':  {'start': 7,  'end': 9,  'label': 'London Open KZ',  'strength': 0.9},
    'ny_open':      {'start': 13, 'end': 15, 'label': 'NY Open KZ',      'strength': 1.0},
    'london_close': {'start': 15, 'end': 17, 'label': 'London Close KZ', 'strength': 0.7},
    'asian_range':  {'start': 0,  'end': 3,  'label': 'Asian Range KZ',  'strength': 0.5},
}

# Crypto trades 24/7
CRYPTO_PAIRS = {
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'TONUSDT',
    'DOGEUSDT', 'BNBUSDT', 'PEPEUSDT', 'ADAUSDT', 'HYPEUSDT',
    'LINKUSDT', 'SUIUSDT', 'DOTUSDT',
}

# Session overlap definitions
OVERLAPS = {
    'london_ny':    {'start': 13, 'end': 16, 'boost': 1.5, 'label': 'London-NY Overlap'},
    'tokyo_london': {'start': 7,  'end': 9,  'boost': 1.2, 'label': 'Tokyo-London Overlap'},
    'sydney_tokyo': {'start': 0,  'end': 7,  'boost': 1.0, 'label': 'Sydney-Tokyo Overlap'},
}

# Pair → best session mapping (where the pair has the most liquidity)
PAIR_BEST_SESSION = {
    'EURUSD':  ['london', 'new_york'],
    'GBPUSD':  ['london', 'new_york'],
    'USDJPY':  ['tokyo', 'new_york'],
    'USDCHF':  ['london', 'new_york'],
    'AUDUSD':  ['sydney', 'tokyo'],
    'USDCAD':  ['new_york'],
    'NZDUSD':  ['sydney', 'tokyo'],
    'EURJPY':  ['london', 'tokyo'],
    'GBPJPY':  ['london', 'tokyo'],
    'EURGBP':  ['london'],
    'AUDJPY':  ['tokyo', 'sydney'],
    'XAUUSD':  ['london', 'new_york'],
}


# ═════════════════════════════════════════════════════════════════════════════
#  SESSION CONTEXT (output)
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class SessionContext:
    """Full session context for a trading pair."""
    pair: str
    active_sessions: List[str]          # Currently active sessions
    best_sessions: List[str]            # Optimal sessions for this pair
    session_quality: str                # 'optimal' | 'acceptable' | 'poor'
    in_kill_zone: bool                  # Inside institutional entry window
    kill_zone_name: str                 # Which KZ, if any
    kill_zone_strength: float           # 0-1 KZ quality
    in_overlap: bool                    # Inside session overlap
    overlap_name: str                   # Which overlap
    score_modifier: float               # -5 to +5 adjustment for confluence
    volatility_expected: str            # 'high' | 'medium' | 'low'
    is_weekend_gap_risk: bool           # Friday late / Sunday early
    summary: str                        # Human-readable summary

    def to_dict(self) -> dict:
        return {
            'active_sessions': self.active_sessions,
            'session_quality': self.session_quality,
            'in_kill_zone': self.in_kill_zone,
            'kill_zone': self.kill_zone_name,
            'in_overlap': self.in_overlap,
            'overlap': self.overlap_name,
            'score_modifier': self.score_modifier,
            'volatility': self.volatility_expected,
            'weekend_risk': self.is_weekend_gap_risk,
        }


# ═════════════════════════════════════════════════════════════════════════════
#  SESSION MANAGER
# ═════════════════════════════════════════════════════════════════════════════

class SessionManager:
    """Analyzes current trading session context for any pair."""

    def get_context(self, pair: str, utc_now: datetime = None) -> SessionContext:
        """
        Get full session context for a pair at the current (or given) time.
        """
        now = utc_now or datetime.now(timezone.utc)
        hour = now.hour
        minute = now.minute
        hour_frac = hour + minute / 60.0
        weekday = now.isoweekday()  # Mon=1, Sun=7

        is_crypto = pair in CRYPTO_PAIRS

        # 1. Active sessions
        active = self._get_active_sessions(hour)

        # 2. Best sessions for this pair
        best = PAIR_BEST_SESSION.get(pair, [])

        # 3. Session quality
        quality = self._calc_quality(pair, active, best, is_crypto)

        # 4. Kill zone check
        in_kz, kz_name, kz_strength = self._check_kill_zone(hour_frac)

        # 5. Overlap check
        in_overlap, overlap_name = self._check_overlap(hour)

        # 6. Weekend gap risk
        weekend_risk = self._check_weekend_risk(weekday, hour, is_crypto)

        # 7. Expected volatility
        vol = self._calc_volatility(active, in_overlap, in_kz)

        # 8. Score modifier (-5 to +5)
        modifier = self._calc_score_modifier(
            quality, in_kz, kz_strength, in_overlap,
            weekend_risk, is_crypto,
        )

        # 9. Summary
        summary = self._build_summary(
            active, quality, in_kz, kz_name, in_overlap, overlap_name,
            weekend_risk, modifier,
        )

        return SessionContext(
            pair=pair,
            active_sessions=active,
            best_sessions=best,
            session_quality=quality,
            in_kill_zone=in_kz,
            kill_zone_name=kz_name,
            kill_zone_strength=kz_strength,
            in_overlap=in_overlap,
            overlap_name=overlap_name,
            score_modifier=round(modifier, 1),
            volatility_expected=vol,
            is_weekend_gap_risk=weekend_risk,
            summary=summary,
        )

    # ── Internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _get_active_sessions(hour: int) -> List[str]:
        """Get currently active trading sessions."""
        active = []
        for name, sess in SESSIONS.items():
            o, c = sess['open'], sess['close']
            if o < c:
                if o <= hour < c:
                    active.append(name)
            else:  # Wraps midnight (sydney: 22-7)
                if hour >= o or hour < c:
                    active.append(name)
        return active

    @staticmethod
    def _calc_quality(pair: str, active: List[str], best: List[str],
                      is_crypto: bool) -> str:
        """Determine session quality for this pair."""
        if is_crypto:
            return 'optimal'  # Crypto is 24/7

        if not active:
            return 'poor'  # No session active

        # Check if any active session is in the pair's best sessions
        if any(s in best for s in active):
            return 'optimal'

        # Check if pair is at least listed in any active session
        for s in active:
            if pair in SESSIONS.get(s, {}).get('pairs', []):
                return 'acceptable'

        return 'poor'

    @staticmethod
    def _check_kill_zone(hour_frac: float) -> tuple:
        """Check if we're inside a kill zone. Returns (in_kz, name, strength)."""
        for name, kz in KILL_ZONES.items():
            if kz['start'] <= hour_frac < kz['end']:
                return True, kz['label'], kz['strength']
        return False, '', 0.0

    @staticmethod
    def _check_overlap(hour: int) -> tuple:
        """Check if we're in a session overlap. Returns (in_overlap, name)."""
        for name, ov in OVERLAPS.items():
            if ov['start'] <= hour < ov['end']:
                return True, ov['label']
        return False, ''

    @staticmethod
    def _check_weekend_risk(weekday: int, hour: int, is_crypto: bool) -> bool:
        """Check weekend gap risk (Friday late, Sunday/Saturday)."""
        if is_crypto:
            return False  # Crypto has no weekend gaps
        # Friday after 20:00 UTC
        if weekday == 5 and hour >= 20:
            return True
        # Saturday or Sunday
        if weekday in (6, 7):
            return True
        return False

    @staticmethod
    def _calc_volatility(active: List[str], in_overlap: bool,
                         in_kz: bool) -> str:
        """Estimate expected volatility."""
        if in_overlap:
            return 'high'
        if in_kz:
            return 'high'
        if 'london' in active or 'new_york' in active:
            return 'medium'
        if active:
            return 'low'
        return 'very_low'

    @staticmethod
    def _calc_score_modifier(quality: str, in_kz: bool, kz_strength: float,
                             in_overlap: bool, weekend_risk: bool,
                             is_crypto: bool) -> float:
        """
        Calculate score modifier: -5 to +5.
        This adjusts the confluence score based on session context.
        """
        mod = 0.0

        # Session quality
        if quality == 'optimal':
            mod += 2.0
        elif quality == 'acceptable':
            mod += 0.0
        elif quality == 'poor':
            mod -= 3.0

        # Kill zone bonus
        if in_kz:
            mod += 2.0 * kz_strength

        # Overlap bonus
        if in_overlap:
            mod += 1.5

        # Weekend penalty
        if weekend_risk:
            mod -= 5.0

        # Crypto gets a flat small bonus (always tradeable)
        if is_crypto and mod == 0.0:
            mod += 1.0

        return max(-5.0, min(5.0, mod))

    @staticmethod
    def _build_summary(active, quality, in_kz, kz_name, in_overlap,
                       overlap_name, weekend_risk, modifier) -> str:
        """Build human-readable session summary."""
        parts = []

        if active:
            sess_str = ', '.join(s.capitalize() for s in active)
            parts.append(f"Sessions: {sess_str}")
        else:
            parts.append("No active session")

        parts.append(f"Quality: {quality}")

        if in_kz:
            parts.append(f"Kill Zone: {kz_name}")
        if in_overlap:
            parts.append(f"Overlap: {overlap_name}")
        if weekend_risk:
            parts.append("Weekend gap risk")

        sign = '+' if modifier >= 0 else ''
        parts.append(f"Modifier: {sign}{modifier:.1f}")

        return ' | '.join(parts)
