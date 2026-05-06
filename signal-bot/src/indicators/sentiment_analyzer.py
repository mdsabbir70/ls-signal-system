"""
Market Sentiment Analyzer — Multi-Source Sentiment Engine

Aggregates sentiment from multiple external sources to provide
a market-wide sentiment reading that influences trade decisions.

Sources:
  1. Crypto Fear & Greed Index (alternative.me)
     - 0-25: Extreme Fear  → contrarian BUY signal for crypto
     - 25-45: Fear          → mild BUY bias
     - 45-55: Neutral       → no bias
     - 55-75: Greed         → mild SELL bias
     - 75-100: Extreme Greed → contrarian SELL signal for crypto

  2. VIX (Volatility Index) — Forex fear gauge
     - VIX < 15: Low vol (complacent) → trend-following works
     - VIX 15-25: Normal → standard conditions
     - VIX 25-35: Elevated → reduce position sizes, wider SL
     - VIX > 35: Extreme fear → forex safe-haven flows (JPY, CHF, USD up)

  3. Internal Performance Sentiment
     - Recent bot win rate trend → confidence gauge
     - Consecutive losses → reduce aggression

Output:
  SentimentResult with:
    - overall_sentiment: 'extreme_fear' | 'fear' | 'neutral' | 'greed' | 'extreme_greed'
    - fear_greed_index: 0-100 (crypto)
    - vix_level: float (forex)
    - score_modifier: -5 to +5
    - contrarian_signal: bool
    - risk_adjustment: 'normal' | 'reduce' | 'avoid'
    - summary: str

Caching: Each source cached independently (15-30 min TTL)

Usage:
    analyzer = SentimentAnalyzer(db)
    result = await analyzer.get_sentiment(pair, direction)
"""

from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass
from typing import Optional

import requests

from utils.logger import setup_logger

logger = setup_logger('sentiment')


# ═══════════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SentimentResult:
    """Combined sentiment from all sources."""
    # Fear & Greed (crypto)
    fear_greed_value: int = 50          # 0-100
    fear_greed_label: str = 'Neutral'   # Extreme Fear/Fear/Neutral/Greed/Extreme Greed

    # VIX (forex volatility)
    vix_value: float = 0.0
    vix_label: str = 'unknown'          # low/normal/elevated/extreme

    # Internal performance
    recent_win_rate: float = 0.0        # Last 20 trades win rate
    consecutive_losses: int = 0
    performance_trend: str = 'neutral'  # improving/stable/declining

    # Computed
    overall_sentiment: str = 'neutral'  # extreme_fear/fear/neutral/greed/extreme_greed
    score_modifier: float = 0.0         # -5 to +5
    contrarian_signal: bool = False     # Extreme sentiment = contrarian opportunity
    risk_adjustment: str = 'normal'     # normal/reduce/avoid
    summary: str = ''

    def to_dict(self) -> dict:
        return {
            'fear_greed_value': self.fear_greed_value,
            'fear_greed_label': self.fear_greed_label,
            'vix_value': round(self.vix_value, 2),
            'vix_label': self.vix_label,
            'recent_win_rate': round(self.recent_win_rate, 1),
            'consecutive_losses': self.consecutive_losses,
            'performance_trend': self.performance_trend,
            'overall_sentiment': self.overall_sentiment,
            'score_modifier': round(self.score_modifier, 1),
            'contrarian_signal': self.contrarian_signal,
            'risk_adjustment': self.risk_adjustment,
            'summary': self.summary,
        }


# ═══════════════════════════════════════════════════════════════════════
#  PAIR CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════

CRYPTO_PAIRS = {
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
    'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'MATICUSDT',
    'LINKUSDT', 'PEPEUSDT',
}

SAFE_HAVEN_CURRENCIES = {'JPY', 'CHF', 'USD'}

# VIX-sensitive pairs: pairs where high VIX causes predictable flows
VIX_SENSITIVE = {
    'USDJPY': 'inverse',    # High VIX → JPY strengthens → USDJPY drops
    'USDCHF': 'inverse',    # High VIX → CHF strengthens → USDCHF drops
    'EURUSD': 'inverse',    # High VIX → USD strengthens → EURUSD drops
    'GBPUSD': 'inverse',    # High VIX → USD strengthens → GBPUSD drops
    'AUDUSD': 'direct',     # High VIX → risk-off → AUDUSD drops (same as VIX effect)
    'NZDUSD': 'direct',     # Same as AUD
    'XAUUSD': 'safe_haven', # High VIX → gold rallies
}


# ═══════════════════════════════════════════════════════════════════════
#  SENTIMENT ANALYZER
# ═══════════════════════════════════════════════════════════════════════

class SentimentAnalyzer:
    """Multi-source market sentiment aggregator."""

    FNG_URL = 'https://api.alternative.me/fng/?limit=1&format=json'
    FNG_CACHE_TTL = 1800       # 30 minutes
    VIX_CACHE_TTL = 1800       # 30 minutes
    PERF_CACHE_TTL = 900       # 15 minutes

    def __init__(self, db=None):
        self.db = db
        self._fng_cache = {'value': None, 'ts': 0}
        self._vix_cache = {'value': None, 'ts': 0}
        self._perf_cache = {'value': None, 'ts': 0}

    async def get_sentiment(self, pair: str, direction: str = 'BUY') -> SentimentResult:
        """
        Get combined sentiment for a pair.

        Args:
            pair: Trading pair (e.g. 'EURUSD', 'BTCUSDT')
            direction: Proposed trade direction ('BUY' or 'SELL')

        Returns:
            SentimentResult with score_modifier and risk_adjustment
        """
        result = SentimentResult()
        is_crypto = pair in CRYPTO_PAIRS
        is_buy = direction == 'BUY'

        loop = asyncio.get_event_loop()

        # Fetch all sources in parallel
        tasks = []

        if is_crypto:
            tasks.append(loop.run_in_executor(None, self._fetch_fear_greed))
        else:
            tasks.append(loop.run_in_executor(None, self._fetch_vix))

        if self.db:
            tasks.append(loop.run_in_executor(None, self._fetch_performance))
        else:
            tasks.append(asyncio.sleep(0))

        fetched = await asyncio.gather(*tasks, return_exceptions=True)

        # Process Fear & Greed or VIX
        if is_crypto:
            fng = fetched[0] if not isinstance(fetched[0], Exception) else None
            if fng:
                result.fear_greed_value = fng['value']
                result.fear_greed_label = fng['label']
        else:
            vix = fetched[0] if not isinstance(fetched[0], Exception) else None
            if vix:
                result.vix_value = vix['value']
                result.vix_label = vix['label']

        # Process performance
        perf = fetched[1] if len(fetched) > 1 and not isinstance(fetched[1], Exception) else None
        if perf:
            result.recent_win_rate = perf['win_rate']
            result.consecutive_losses = perf['consec_losses']
            result.performance_trend = perf['trend']

        # Calculate sentiment score and modifier
        self._calculate_sentiment(result, pair, is_buy, is_crypto)

        return result

    # ── Fear & Greed Index ───────────────────────────────────────────

    def _fetch_fear_greed(self) -> Optional[dict]:
        """Fetch Crypto Fear & Greed Index from alternative.me."""
        now = time.time()
        if self._fng_cache['value'] and (now - self._fng_cache['ts']) < self.FNG_CACHE_TTL:
            return self._fng_cache['value']

        try:
            resp = requests.get(self.FNG_URL, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            entry = data.get('data', [{}])[0]
            value = int(entry.get('value', 50))
            label = entry.get('value_classification', 'Neutral')

            result = {'value': value, 'label': label}
            self._fng_cache = {'value': result, 'ts': now}

            # Save to DB for historical tracking
            self._save_sentiment_to_db('fear_greed', value, label)

            logger.info(f"Fear & Greed Index: {value} ({label})")
            return result

        except Exception as e:
            logger.warning(f"Fear & Greed fetch failed: {e}")
            # Return cached or default
            return self._fng_cache.get('value') or {'value': 50, 'label': 'Neutral'}

    # ── VIX (Volatility Index) ───────────────────────────────────────

    def _fetch_vix(self) -> Optional[dict]:
        """Fetch VIX level via yfinance or fallback."""
        now = time.time()
        if self._vix_cache['value'] and (now - self._vix_cache['ts']) < self.VIX_CACHE_TTL:
            return self._vix_cache['value']

        try:
            import yfinance as yf
            vix = yf.Ticker('^VIX')
            hist = vix.history(period='2d')
            if hist.empty:
                return self._vix_cache.get('value') or {'value': 20.0, 'label': 'normal'}

            current_vix = float(hist['Close'].iloc[-1])

            if current_vix < 15:
                label = 'low'
            elif current_vix < 25:
                label = 'normal'
            elif current_vix < 35:
                label = 'elevated'
            else:
                label = 'extreme'

            result = {'value': current_vix, 'label': label}
            self._vix_cache = {'value': result, 'ts': now}

            self._save_sentiment_to_db('vix', current_vix, label)

            logger.info(f"VIX: {current_vix:.1f} ({label})")
            return result

        except Exception as e:
            logger.warning(f"VIX fetch failed: {e}")
            return self._vix_cache.get('value') or {'value': 20.0, 'label': 'normal'}

    # ── Internal Performance ─────────────────────────────────────────

    def _fetch_performance(self) -> Optional[dict]:
        """Analyze recent bot performance as sentiment proxy."""
        if not self.db:
            return None

        now = time.time()
        if self._perf_cache['value'] and (now - self._perf_cache['ts']) < self.PERF_CACHE_TTL:
            return self._perf_cache['value']

        try:
            # Last 20 closed signals
            rows = self.db.execute(
                """SELECT status FROM signals
                   WHERE status IN ('CLOSED_TP', 'CLOSED_SL')
                   ORDER BY close_time DESC LIMIT 20"""
            )
            if not rows:
                return {'win_rate': 50.0, 'consec_losses': 0, 'trend': 'neutral'}

            statuses = [r['status'] for r in rows]
            wins = sum(1 for s in statuses if s == 'CLOSED_TP')
            win_rate = (wins / len(statuses)) * 100 if statuses else 50.0

            # Consecutive losses from most recent
            consec_losses = 0
            for s in statuses:
                if s == 'CLOSED_SL':
                    consec_losses += 1
                else:
                    break

            # Trend: compare first half vs second half
            half = len(statuses) // 2
            if half > 0:
                recent_wr = sum(1 for s in statuses[:half] if s == 'CLOSED_TP') / half
                older_wr = sum(1 for s in statuses[half:] if s == 'CLOSED_TP') / (len(statuses) - half)
                if recent_wr > older_wr + 0.1:
                    trend = 'improving'
                elif recent_wr < older_wr - 0.1:
                    trend = 'declining'
                else:
                    trend = 'stable'
            else:
                trend = 'neutral'

            result = {
                'win_rate': win_rate,
                'consec_losses': consec_losses,
                'trend': trend,
            }
            self._perf_cache = {'value': result, 'ts': now}
            return result

        except Exception as e:
            logger.warning(f"Performance fetch failed: {e}")
            return None

    # ── Sentiment Calculation ────────────────────────────────────────

    def _calculate_sentiment(self, result: SentimentResult, pair: str,
                             is_buy: bool, is_crypto: bool):
        """Calculate overall sentiment, score modifier, and risk adjustment."""
        modifier = 0.0
        risk = 'normal'
        contrarian = False
        parts = []

        if is_crypto:
            # ── Crypto: Fear & Greed based ──
            fng = result.fear_greed_value

            if fng <= 20:
                # Extreme Fear → contrarian BUY opportunity
                result.overall_sentiment = 'extreme_fear'
                contrarian = True
                if is_buy:
                    modifier += 3.0   # Boost BUY in extreme fear
                    parts.append('Extreme Fear favors contrarian BUY')
                else:
                    modifier -= 2.0   # Penalize SELL in extreme fear
                    parts.append('Extreme Fear discourages SELL')
            elif fng <= 40:
                result.overall_sentiment = 'fear'
                if is_buy:
                    modifier += 1.5
                    parts.append('Fear: mild BUY bias')
                else:
                    modifier -= 1.0
                    parts.append('Fear: mild SELL penalty')
            elif fng <= 60:
                result.overall_sentiment = 'neutral'
                parts.append('Sentiment neutral')
            elif fng <= 80:
                result.overall_sentiment = 'greed'
                if not is_buy:
                    modifier += 1.5
                    parts.append('Greed: mild SELL bias')
                else:
                    modifier -= 1.0
                    parts.append('Greed: mild BUY penalty')
            else:
                result.overall_sentiment = 'extreme_greed'
                contrarian = True
                if not is_buy:
                    modifier += 3.0
                    parts.append('Extreme Greed favors contrarian SELL')
                else:
                    modifier -= 2.0
                    parts.append('Extreme Greed discourages BUY')

        else:
            # ── Forex: VIX based ──
            vix = result.vix_value

            if vix <= 0:
                result.overall_sentiment = 'neutral'
                parts.append('VIX unavailable')
            elif vix < 15:
                result.overall_sentiment = 'greed'
                modifier += 1.0  # Low vol = trend-following works
                parts.append(f'VIX low ({vix:.0f}): trend-follow mode')
            elif vix < 25:
                result.overall_sentiment = 'neutral'
                parts.append(f'VIX normal ({vix:.0f})')
            elif vix < 35:
                result.overall_sentiment = 'fear'
                risk = 'reduce'
                parts.append(f'VIX elevated ({vix:.0f}): reduce size')

                # Safe-haven flow adjustments
                vix_sens = VIX_SENSITIVE.get(pair)
                if vix_sens == 'safe_haven':
                    # Gold rallies in fear
                    if is_buy:
                        modifier += 2.0
                        parts.append('Gold safe-haven BUY boost')
                    else:
                        modifier -= 1.5
                        parts.append('Gold safe-haven SELL penalty')
                elif vix_sens == 'inverse':
                    # USD/JPY/CHF strengthen → pair drops
                    if not is_buy:
                        modifier += 1.5
                        parts.append(f'{pair}: risk-off SELL bias')
                    else:
                        modifier -= 1.0
                        parts.append(f'{pair}: risk-off BUY penalty')
                elif vix_sens == 'direct':
                    # Risk currencies weaken
                    if not is_buy:
                        modifier += 1.5
                        parts.append(f'{pair}: risk-off SELL bias')
                    else:
                        modifier -= 1.5
                        parts.append(f'{pair}: risk-off BUY penalty')
            else:
                result.overall_sentiment = 'extreme_fear'
                risk = 'reduce'
                contrarian = True
                parts.append(f'VIX extreme ({vix:.0f}): max caution')

                vix_sens = VIX_SENSITIVE.get(pair)
                if vix_sens == 'safe_haven':
                    if is_buy:
                        modifier += 3.0
                        parts.append('Extreme fear: gold safe-haven rally')
                elif vix_sens in ('inverse', 'direct'):
                    if not is_buy:
                        modifier += 2.0
                        parts.append(f'{pair}: extreme fear SELL boost')
                    else:
                        modifier -= 2.0
                        parts.append(f'{pair}: extreme fear BUY penalty')

        # ── Performance adjustment (both crypto and forex) ──
        if result.consecutive_losses >= 5:
            modifier -= 2.0
            risk = 'reduce'
            parts.append(f'{result.consecutive_losses} consecutive losses: reduce')
        elif result.consecutive_losses >= 3:
            modifier -= 1.0
            parts.append(f'{result.consecutive_losses} consecutive losses: caution')

        if result.performance_trend == 'declining' and result.recent_win_rate < 40:
            modifier -= 1.0
            parts.append('Declining performance: reduce')

        if result.performance_trend == 'improving' and result.recent_win_rate > 60:
            modifier += 0.5
            parts.append('Strong recent performance')

        # Clamp modifier
        result.score_modifier = max(-5.0, min(5.0, round(modifier, 1)))
        result.contrarian_signal = contrarian
        result.risk_adjustment = risk
        result.summary = ' | '.join(parts) if parts else 'No sentiment data'

    # ── DB helpers ───────────────────────────────────────────────────

    def _save_sentiment_to_db(self, source: str, value: float, label: str):
        """Save sentiment reading to sentiment_history table."""
        if not self.db:
            return
        try:
            self.db.execute_write(
                """INSERT INTO sentiment_history (source, value, label)
                   VALUES (:p0, :p1, :p2)""",
                (source, value, label)
            )
        except Exception:
            pass  # Table might not exist yet — non-critical

    def get_latest_readings(self) -> dict:
        """Get latest cached readings (for API/dashboard)."""
        return {
            'fear_greed': self._fng_cache.get('value'),
            'vix': self._vix_cache.get('value'),
            'performance': self._perf_cache.get('value'),
        }
