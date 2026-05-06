"""
Pair Correlation Analyzer

Professional traders never take correlated positions blindly.
If EURUSD BUY and GBPUSD BUY trigger at the same time, it's
essentially double exposure to USD weakness — risky.

This module provides:
  - Real-time correlation matrix from recent price data
  - Known institutional correlation map (hardcoded fallback)
  - Overexposure detection (same-direction correlated signals)
  - Cross-pair confirmation (correlated pairs agree = stronger signal)
  - Inverse pair detection (EURUSD up = USDCHF down)
  - Currency exposure tracking (how much USD, EUR, etc. open)

Correlation ranges:
  +0.80 to +1.00 → Strong positive (EURUSD / GBPUSD)
  +0.50 to +0.79 → Moderate positive
  -0.50 to -0.79 → Moderate negative
  -0.80 to -1.00 → Strong negative (EURUSD / USDCHF)

Usage:
    ca = CorrelationAnalyzer()
    ca.update_prices({'EURUSD': df1, 'GBPUSD': df2, ...})
    result = ca.check_signal('GBPUSD', 'BUY', open_signals)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
import numpy as np
from utils.logger import setup_logger

logger = setup_logger('correlation')


# ═════════════════════════════════════════════════════════════════════════════
#  KNOWN CORRELATION MAP (institutional knowledge, fallback)
# ═════════════════════════════════════════════════════════════════════════════

# Positive correlations (move together)
POSITIVE_CORRELATIONS = {
    ('EURUSD', 'GBPUSD'):  0.85,
    ('EURUSD', 'AUDUSD'):  0.70,
    ('EURUSD', 'NZDUSD'):  0.65,
    ('GBPUSD', 'AUDUSD'):  0.60,
    ('GBPUSD', 'NZDUSD'):  0.55,
    ('AUDUSD', 'NZDUSD'):  0.90,
    ('EURJPY', 'GBPJPY'):  0.85,
    ('USDJPY', 'EURJPY'):  0.60,
    ('BTCUSDT', 'ETHUSDT'): 0.90,
    ('BTCUSDT', 'SOLUSDT'): 0.80,
    ('BTCUSDT', 'ADAUSDT'): 0.75,
    ('BTCUSDT', 'LINKUSDT'): 0.70,
    ('BTCUSDT', 'DOTUSDT'): 0.75,
    ('ETHUSDT', 'SOLUSDT'): 0.82,
    ('ETHUSDT', 'LINKUSDT'): 0.72,
    ('SOLUSDT', 'ADAUSDT'): 0.65,
    ('DOGEUSDT', 'PEPEUSDT'): 0.60,  # Meme coins
}

# Negative correlations (move opposite)
NEGATIVE_CORRELATIONS = {
    ('EURUSD', 'USDCHF'): -0.90,
    ('EURUSD', 'USDJPY'): -0.40,
    ('GBPUSD', 'USDCHF'): -0.80,
    ('GBPUSD', 'USDCAD'): -0.50,
    ('AUDUSD', 'USDCAD'): -0.60,
    ('XAUUSD', 'USDJPY'): -0.40,  # Gold vs Yen (both safe havens sometimes)
}

# All correlations combined (both directions)
KNOWN_CORRELATIONS: Dict[tuple, float] = {}
KNOWN_CORRELATIONS.update(POSITIVE_CORRELATIONS)
KNOWN_CORRELATIONS.update(NEGATIVE_CORRELATIONS)

# Currency exposure: which currencies are long/short for each pair direction
CURRENCY_EXPOSURE = {
    'EURUSD':  {'BUY': ('EUR+', 'USD-'), 'SELL': ('EUR-', 'USD+')},
    'GBPUSD':  {'BUY': ('GBP+', 'USD-'), 'SELL': ('GBP-', 'USD+')},
    'USDJPY':  {'BUY': ('USD+', 'JPY-'), 'SELL': ('USD-', 'JPY+')},
    'USDCHF':  {'BUY': ('USD+', 'CHF-'), 'SELL': ('USD-', 'CHF+')},
    'AUDUSD':  {'BUY': ('AUD+', 'USD-'), 'SELL': ('AUD-', 'USD+')},
    'USDCAD':  {'BUY': ('USD+', 'CAD-'), 'SELL': ('USD-', 'CAD+')},
    'NZDUSD':  {'BUY': ('NZD+', 'USD-'), 'SELL': ('NZD-', 'USD+')},
    'EURJPY':  {'BUY': ('EUR+', 'JPY-'), 'SELL': ('EUR-', 'JPY+')},
    'GBPJPY':  {'BUY': ('GBP+', 'JPY-'), 'SELL': ('GBP-', 'JPY+')},
    'EURGBP':  {'BUY': ('EUR+', 'GBP-'), 'SELL': ('EUR-', 'GBP+')},
    'AUDJPY':  {'BUY': ('AUD+', 'JPY-'), 'SELL': ('AUD-', 'JPY+')},
    'XAUUSD':  {'BUY': ('XAU+', 'USD-'), 'SELL': ('XAU-', 'USD+')},
    # Crypto — base currency is the token, quote is USDT
    'BTCUSDT':  {'BUY': ('BTC+', 'USD-'), 'SELL': ('BTC-', 'USD+')},
    'ETHUSDT':  {'BUY': ('ETH+', 'USD-'), 'SELL': ('ETH-', 'USD+')},
    'SOLUSDT':  {'BUY': ('SOL+', 'USD-'), 'SELL': ('SOL-', 'USD+')},
    'XRPUSDT':  {'BUY': ('XRP+', 'USD-'), 'SELL': ('XRP-', 'USD+')},
    'DOGEUSDT': {'BUY': ('DOGE+', 'USD-'), 'SELL': ('DOGE-', 'USD+')},
    'BNBUSDT':  {'BUY': ('BNB+', 'USD-'), 'SELL': ('BNB-', 'USD+')},
    'PEPEUSDT': {'BUY': ('PEPE+', 'USD-'), 'SELL': ('PEPE-', 'USD+')},
    'ADAUSDT':  {'BUY': ('ADA+', 'USD-'), 'SELL': ('ADA-', 'USD+')},
    'LINKUSDT': {'BUY': ('LINK+', 'USD-'), 'SELL': ('LINK-', 'USD+')},
    'DOTUSDT':  {'BUY': ('DOT+', 'USD-'), 'SELL': ('DOT-', 'USD+')},
    'TONUSDT':  {'BUY': ('TON+', 'USD-'), 'SELL': ('TON-', 'USD+')},
    'SUIUSDT':  {'BUY': ('SUI+', 'USD-'), 'SELL': ('SUI-', 'USD+')},
    'HYPEUSDT': {'BUY': ('HYPE+', 'USD-'), 'SELL': ('HYPE-', 'USD+')},
}


# ═════════════════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class CorrelationResult:
    """Result of correlation check for a potential signal."""
    action: str                         # 'ALLOW' | 'BLOCK' | 'WARN'
    reason: str
    correlated_pairs: List[str] = field(default_factory=list)
    correlation_values: Dict[str, float] = field(default_factory=dict)
    currency_exposure: Dict[str, int] = field(default_factory=dict)
    confirmation_boost: float = 0.0     # 0-3 bonus for cross-pair confirmation
    overexposure_penalty: float = 0.0   # 0-5 penalty for overexposure

    def to_dict(self) -> dict:
        return {
            'action': self.action,
            'reason': self.reason,
            'correlated_pairs': self.correlated_pairs,
            'confirmation_boost': self.confirmation_boost,
            'overexposure_penalty': self.overexposure_penalty,
            'exposure': self.currency_exposure,
        }


# ═════════════════════════════════════════════════════════════════════════════
#  CORRELATION ANALYZER
# ═════════════════════════════════════════════════════════════════════════════

class CorrelationAnalyzer:
    """Analyzes pair correlations to prevent overexposure."""

    MAX_SAME_CURRENCY_EXPOSURE = 3  # Max 3 positions with same currency
    STRONG_CORR_THRESHOLD = 0.75    # Block if correlation > this
    MODERATE_CORR_THRESHOLD = 0.50  # Warn if correlation > this

    def __init__(self):
        self._live_correlations: Dict[tuple, float] = {}
        self._price_cache: Dict[str, list] = {}

    def update_prices(self, pair: str, closes: list):
        """Update price cache for live correlation calculation."""
        if closes and len(closes) >= 20:
            self._price_cache[pair] = closes[-100:]  # Keep last 100 closes

    def calculate_live_correlations(self):
        """Calculate live correlation matrix from cached prices."""
        pairs = list(self._price_cache.keys())
        if len(pairs) < 2:
            return

        for i in range(len(pairs)):
            for j in range(i + 1, len(pairs)):
                p1, p2 = pairs[i], pairs[j]
                c1 = self._price_cache[p1]
                c2 = self._price_cache[p2]

                # Use overlapping length
                min_len = min(len(c1), len(c2))
                if min_len < 20:
                    continue

                try:
                    arr1 = np.array(c1[-min_len:], dtype=float)
                    arr2 = np.array(c2[-min_len:], dtype=float)

                    # Calculate Pearson correlation of returns
                    ret1 = np.diff(arr1) / arr1[:-1]
                    ret2 = np.diff(arr2) / arr2[:-1]

                    if len(ret1) < 10:
                        continue

                    corr = np.corrcoef(ret1, ret2)[0, 1]
                    if not np.isnan(corr):
                        self._live_correlations[(p1, p2)] = round(corr, 3)
                        self._live_correlations[(p2, p1)] = round(corr, 3)
                except Exception:
                    pass

    def get_correlation(self, pair1: str, pair2: str) -> float:
        """Get correlation between two pairs (live or fallback to known)."""
        # Try live first
        corr = self._live_correlations.get((pair1, pair2))
        if corr is not None:
            return corr

        # Fallback to known map
        corr = KNOWN_CORRELATIONS.get((pair1, pair2))
        if corr is not None:
            return corr
        corr = KNOWN_CORRELATIONS.get((pair2, pair1))
        if corr is not None:
            return corr

        return 0.0  # Unknown = no correlation assumed

    def check_signal(
        self,
        pair: str,
        direction: str,
        open_signals: List[dict],
    ) -> CorrelationResult:
        """
        Check if a new signal would create overexposure.

        Args:
            pair: The pair for the new signal
            direction: 'BUY' or 'SELL'
            open_signals: List of currently open signals
                          Each: {'pair': str, 'direction': str}

        Returns:
            CorrelationResult with action, reason, and modifiers
        """
        if not open_signals:
            return CorrelationResult(
                action='ALLOW',
                reason='No open signals — no correlation risk',
            )

        correlated = []
        corr_values = {}
        confirmation_boost = 0.0
        overexposure_penalty = 0.0
        block_reason = ''

        for sig in open_signals:
            sig_pair = sig['pair']
            sig_dir = sig['direction']

            if sig_pair == pair:
                # Same pair already open
                return CorrelationResult(
                    action='BLOCK',
                    reason=f'{pair} already has an open signal ({sig_dir})',
                    correlated_pairs=[pair],
                )

            corr = self.get_correlation(pair, sig_pair)
            abs_corr = abs(corr)

            if abs_corr < self.MODERATE_CORR_THRESHOLD:
                continue

            correlated.append(sig_pair)
            corr_values[sig_pair] = corr

            # Same direction + positive correlation = overexposure
            if corr > 0 and direction == sig_dir:
                if abs_corr >= self.STRONG_CORR_THRESHOLD:
                    overexposure_penalty += 3.0
                    block_reason = (
                        f"Strong correlation with {sig_pair} ({corr:+.2f}) — "
                        f"both {direction}, overexposure risk"
                    )
                else:
                    overexposure_penalty += 1.5

            # Same direction + negative correlation = conflicting
            elif corr < 0 and direction == sig_dir:
                # e.g., BUY EURUSD + BUY USDCHF (contradictory)
                if abs_corr >= self.STRONG_CORR_THRESHOLD:
                    block_reason = (
                        f"Contradictory signal: {pair} {direction} conflicts with "
                        f"{sig_pair} {sig_dir} (corr {corr:+.2f})"
                    )
                    overexposure_penalty += 2.0

            # Opposite direction + negative correlation = confirmation!
            elif corr < 0 and direction != sig_dir:
                # e.g., BUY EURUSD + SELL USDCHF = both say USD weak = confirmation
                confirmation_boost += min(1.5, abs_corr)

            # Opposite direction + positive correlation = also conflicting
            elif corr > 0 and direction != sig_dir:
                # e.g., BUY EURUSD + SELL GBPUSD (corr +0.85) = contradictory
                if abs_corr >= self.STRONG_CORR_THRESHOLD:
                    overexposure_penalty += 1.0

        # Check currency exposure
        exposure = self._calc_currency_exposure(pair, direction, open_signals)
        max_exposure = max(exposure.values()) if exposure else 0

        if max_exposure > self.MAX_SAME_CURRENCY_EXPOSURE:
            over_currencies = [c for c, v in exposure.items() if v > self.MAX_SAME_CURRENCY_EXPOSURE]
            block_reason = (
                f"Currency overexposure: {', '.join(over_currencies)} "
                f"({max_exposure} positions)"
            )
            overexposure_penalty += 2.0

        # Determine action
        if overexposure_penalty >= 4.0:
            action = 'BLOCK'
            reason = block_reason or f"High overexposure ({overexposure_penalty:.1f})"
        elif overexposure_penalty >= 2.0:
            action = 'WARN'
            reason = block_reason or f"Moderate correlation risk ({overexposure_penalty:.1f})"
        elif confirmation_boost > 0:
            action = 'ALLOW'
            reason = f"Cross-pair confirmation (+{confirmation_boost:.1f})"
        else:
            action = 'ALLOW'
            reason = 'No significant correlation risk'

        return CorrelationResult(
            action=action,
            reason=reason,
            correlated_pairs=correlated,
            correlation_values=corr_values,
            currency_exposure=exposure,
            confirmation_boost=min(3.0, confirmation_boost),
            overexposure_penalty=min(5.0, overexposure_penalty),
        )

    @staticmethod
    def _calc_currency_exposure(
        pair: str,
        direction: str,
        open_signals: List[dict],
    ) -> Dict[str, int]:
        """
        Calculate how many times each currency is exposed.
        Returns: {'USD': 3, 'EUR': 2, ...}
        """
        exposure: Dict[str, int] = {}

        # Add exposure from open signals
        for sig in open_signals:
            sp = sig['pair']
            sd = sig['direction']
            ce = CURRENCY_EXPOSURE.get(sp, {}).get(sd, ())
            for exp in ce:
                cur = exp[:-1]  # Remove +/- suffix
                exposure[cur] = exposure.get(cur, 0) + 1

        # Add exposure from the new signal
        ce = CURRENCY_EXPOSURE.get(pair, {}).get(direction, ())
        for exp in ce:
            cur = exp[:-1]
            exposure[cur] = exposure.get(cur, 0) + 1

        return exposure

    def get_correlated_pairs(self, pair: str, threshold: float = 0.50) -> List[tuple]:
        """
        Get all pairs correlated with the given pair above threshold.
        Returns list of (pair, correlation) sorted by abs(correlation).
        """
        results = []

        # Check live correlations first
        for (p1, p2), corr in self._live_correlations.items():
            if p1 == pair and abs(corr) >= threshold:
                results.append((p2, corr))

        # Fill from known if not in live
        seen = {r[0] for r in results}
        for (p1, p2), corr in KNOWN_CORRELATIONS.items():
            if p1 == pair and p2 not in seen and abs(corr) >= threshold:
                results.append((p2, corr))
            elif p2 == pair and p1 not in seen and abs(corr) >= threshold:
                results.append((p1, corr))

        return sorted(results, key=lambda x: abs(x[1]), reverse=True)
