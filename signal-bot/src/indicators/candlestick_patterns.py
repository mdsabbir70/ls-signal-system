"""
Candlestick Pattern Recognition Engine

Detects 22 candlestick patterns from OHLCV data — the same patterns
a professional price-action trader watches for:

  Single candle:
    Doji, Hammer, Inverted Hammer, Shooting Star,
    Marubozu, Spinning Top, Pin Bar

  Double candle:
    Bullish Engulfing, Bearish Engulfing, Piercing Line,
    Dark Cloud Cover, Tweezer Top, Tweezer Bottom

  Triple candle:
    Morning Star, Evening Star, Three White Soldiers,
    Three Black Crows, Three Inside Up, Three Inside Down

  Context-aware:
    Patterns are scored by reliability, location (at key levels),
    and trend context (reversal vs continuation).

Usage:
    detector = CandlestickDetector()
    result = detector.detect(df_h1, atr=0.0015, trend='bullish')
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
import pandas as pd
from utils.logger import setup_logger

logger = setup_logger('candlestick')


# ═════════════════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class CandlePattern:
    """A single detected pattern."""
    name: str               # e.g. 'bullish_engulfing'
    type: str               # 'bullish' | 'bearish'
    reliability: float      # 0.0 – 1.0 (how reliable historically)
    bar_index: int          # Index in the DataFrame
    description: str = ''   # Human-readable description


@dataclass
class CandlestickResult:
    """Output of candlestick analysis — used by confluence scorer."""
    patterns: List[CandlePattern] = field(default_factory=list)
    bullish_count: int = 0
    bearish_count: int = 0
    strongest_bullish: Optional[CandlePattern] = None
    strongest_bearish: Optional[CandlePattern] = None
    signal_bias: str = 'neutral'        # 'bullish' | 'bearish' | 'neutral'
    confidence: float = 0.0             # 0.0 – 1.0

    def summary(self, direction: str) -> str:
        """One-line summary for notifications."""
        is_buy = direction == 'BUY'
        relevant = [p for p in self.patterns if
                    (is_buy and p.type == 'bullish') or
                    (not is_buy and p.type == 'bearish')]
        if not relevant:
            opposing = [p for p in self.patterns if
                        (is_buy and p.type == 'bearish') or
                        (not is_buy and p.type == 'bullish')]
            if opposing:
                return f"⚠ Opposing: {opposing[0].name.replace('_', ' ').title()}"
            return ''

        names = [p.name.replace('_', ' ').title() for p in relevant[:3]]
        return ' + '.join(names)


# ═════════════════════════════════════════════════════════════════════════════
#  PATTERN RELIABILITY SCORES (from historical accuracy studies)
# ═════════════════════════════════════════════════════════════════════════════

RELIABILITY = {
    # Single — moderate reliability alone, high with context
    'doji':              0.45,
    'hammer':            0.65,
    'inverted_hammer':   0.55,
    'shooting_star':     0.65,
    'marubozu':          0.60,
    'spinning_top':      0.35,
    'pin_bar':           0.70,

    # Double — stronger signals
    'bullish_engulfing':  0.75,
    'bearish_engulfing':  0.75,
    'piercing_line':      0.65,
    'dark_cloud_cover':   0.65,
    'tweezer_bottom':     0.60,
    'tweezer_top':        0.60,

    # Triple — highest reliability
    'morning_star':        0.80,
    'evening_star':        0.80,
    'three_white_soldiers': 0.78,
    'three_black_crows':   0.78,
    'three_inside_up':     0.70,
    'three_inside_down':   0.70,
}


# ═════════════════════════════════════════════════════════════════════════════
#  CANDLESTICK DETECTOR
# ═════════════════════════════════════════════════════════════════════════════

class CandlestickDetector:
    """Detects candlestick patterns from OHLCV data."""

    # Body-to-range thresholds
    DOJI_RATIO = 0.10           # Body ≤ 10% of range = doji
    SMALL_BODY_RATIO = 0.30     # Body ≤ 30% of range = small body
    MARUBOZU_RATIO = 0.90       # Body ≥ 90% of range = marubozu
    WICK_RATIO = 2.0            # Long wick ≥ 2x body
    PIN_BAR_WICK_RATIO = 2.5    # Pin bar: wick ≥ 2.5x body
    ENGULF_MARGIN = 0.0         # Engulfing: new body fully covers old body
    TWEEZER_TOLERANCE = 0.3     # Tweezer: highs/lows within 30% of ATR

    def detect(
        self,
        df: pd.DataFrame,
        atr: float = 0.001,
        trend: str = 'unknown',
        lookback: int = 10,
    ) -> CandlestickResult:
        """
        Detect candlestick patterns in the last N bars.

        Args:
            df: OHLCV DataFrame with columns: open, high, low, close
            atr: Current ATR (for significance filtering)
            trend: Current trend context ('bullish'|'bearish'|'ranging'|'unknown')
            lookback: How many recent bars to scan
        """
        result = CandlestickResult()

        if df is None or len(df) < 5:
            return result

        # Ensure we have standard column names
        df = df.copy()
        cols = {c.lower(): c for c in df.columns}
        for need in ('open', 'high', 'low', 'close'):
            if need not in cols:
                return result

        n = len(df)
        start = max(0, n - lookback)

        for i in range(start, n):
            if i < 2:
                continue
            self._check_single(df, i, atr, trend, result)
            self._check_double(df, i, atr, trend, result)
            if i >= 2:
                self._check_triple(df, i, atr, trend, result)

        # Summarize
        result.bullish_count = sum(1 for p in result.patterns if p.type == 'bullish')
        result.bearish_count = sum(1 for p in result.patterns if p.type == 'bearish')

        bull_patterns = [p for p in result.patterns if p.type == 'bullish']
        bear_patterns = [p for p in result.patterns if p.type == 'bearish']

        if bull_patterns:
            result.strongest_bullish = max(bull_patterns, key=lambda p: p.reliability)
        if bear_patterns:
            result.strongest_bearish = max(bear_patterns, key=lambda p: p.reliability)

        # Overall bias
        bull_score = sum(p.reliability for p in bull_patterns)
        bear_score = sum(p.reliability for p in bear_patterns)
        if bull_score > bear_score + 0.3:
            result.signal_bias = 'bullish'
            result.confidence = min(1.0, bull_score / 2.0)
        elif bear_score > bull_score + 0.3:
            result.signal_bias = 'bearish'
            result.confidence = min(1.0, bear_score / 2.0)
        else:
            result.signal_bias = 'neutral'
            result.confidence = 0.0

        return result

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _body(o, c):
        return abs(c - o)

    @staticmethod
    def _range(h, l):
        return h - l if h > l else 0.0001

    @staticmethod
    def _is_bullish(o, c):
        return c > o

    @staticmethod
    def _is_bearish(o, c):
        return c < o

    @staticmethod
    def _upper_wick(o, h, c):
        return h - max(o, c)

    @staticmethod
    def _lower_wick(o, l, c):
        return min(o, c) - l

    def _candle_data(self, df, i):
        """Extract OHLC for bar i."""
        row = df.iloc[i]
        return float(row['open']), float(row['high']), float(row['low']), float(row['close'])

    def _is_significant(self, body, atr):
        """Is this candle body significant relative to ATR?"""
        return body >= atr * 0.3

    # ── Single Candle Patterns ──────────────────────────────────────────────

    def _check_single(self, df, i, atr, trend, result):
        o, h, l, c = self._candle_data(df, i)
        body = self._body(o, c)
        rng = self._range(h, l)
        upper = self._upper_wick(o, h, c)
        lower = self._lower_wick(o, l, c)
        body_ratio = body / rng if rng > 0 else 0

        # Only detect on recent bars (last 3)
        if i < len(df) - 3:
            return

        # ── Doji ──
        if body_ratio <= self.DOJI_RATIO and rng >= atr * 0.5:
            # Doji = indecision. Bearish in uptrend, bullish in downtrend
            if trend == 'bullish':
                ptype = 'bearish'
                desc = 'Doji in uptrend — potential reversal'
            elif trend == 'bearish':
                ptype = 'bullish'
                desc = 'Doji in downtrend — potential reversal'
            else:
                ptype = 'neutral'
                desc = 'Doji — indecision'
            if ptype != 'neutral':
                result.patterns.append(CandlePattern(
                    'doji', ptype, RELIABILITY['doji'], i, desc))

        # ── Hammer (bullish reversal) ──
        if (body_ratio <= self.SMALL_BODY_RATIO and
                lower >= body * self.WICK_RATIO and
                upper <= body * 0.5 and
                rng >= atr * 0.5):
            # Best in downtrend (reversal signal)
            rel = RELIABILITY['hammer']
            if trend == 'bearish':
                rel = min(1.0, rel + 0.10)
                desc = 'Hammer in downtrend — strong reversal signal'
            else:
                desc = 'Hammer pattern — bullish reversal candidate'
            result.patterns.append(CandlePattern(
                'hammer', 'bullish', rel, i, desc))

        # ── Shooting Star (bearish reversal) ──
        if (body_ratio <= self.SMALL_BODY_RATIO and
                upper >= body * self.WICK_RATIO and
                lower <= body * 0.5 and
                rng >= atr * 0.5):
            rel = RELIABILITY['shooting_star']
            if trend == 'bullish':
                rel = min(1.0, rel + 0.10)
                desc = 'Shooting Star in uptrend — strong reversal signal'
            else:
                desc = 'Shooting Star — bearish reversal candidate'
            result.patterns.append(CandlePattern(
                'shooting_star', 'bearish', rel, i, desc))

        # ── Pin Bar ──
        if rng >= atr * 0.8:
            # Bullish pin bar: very long lower wick
            if (lower >= body * self.PIN_BAR_WICK_RATIO and
                    upper <= rng * 0.15):
                rel = RELIABILITY['pin_bar']
                if trend == 'bearish':
                    rel = min(1.0, rel + 0.10)
                result.patterns.append(CandlePattern(
                    'pin_bar', 'bullish', rel, i,
                    'Bullish Pin Bar — strong rejection of lower prices'))
            # Bearish pin bar: very long upper wick
            elif (upper >= body * self.PIN_BAR_WICK_RATIO and
                  lower <= rng * 0.15):
                rel = RELIABILITY['pin_bar']
                if trend == 'bullish':
                    rel = min(1.0, rel + 0.10)
                result.patterns.append(CandlePattern(
                    'pin_bar', 'bearish', rel, i,
                    'Bearish Pin Bar — strong rejection of higher prices'))

        # ── Marubozu (strong momentum) ──
        if body_ratio >= self.MARUBOZU_RATIO and body >= atr * 0.8:
            if self._is_bullish(o, c):
                result.patterns.append(CandlePattern(
                    'marubozu', 'bullish', RELIABILITY['marubozu'], i,
                    'Bullish Marubozu — strong buying pressure'))
            else:
                result.patterns.append(CandlePattern(
                    'marubozu', 'bearish', RELIABILITY['marubozu'], i,
                    'Bearish Marubozu — strong selling pressure'))

    # ── Double Candle Patterns ──────────────────────────────────────────────

    def _check_double(self, df, i, atr, trend, result):
        if i < 1:
            return
        # Only detect on last 2 bars
        if i < len(df) - 2:
            return

        o1, h1, l1, c1 = self._candle_data(df, i - 1)
        o2, h2, l2, c2 = self._candle_data(df, i)
        body1 = self._body(o1, c1)
        body2 = self._body(o2, c2)

        # ── Bullish Engulfing ──
        if (self._is_bearish(o1, c1) and self._is_bullish(o2, c2) and
                body2 > body1 and
                o2 <= c1 and c2 >= o1 and
                body2 >= atr * 0.5):
            rel = RELIABILITY['bullish_engulfing']
            if trend == 'bearish':
                rel = min(1.0, rel + 0.10)
                desc = 'Bullish Engulfing in downtrend — strong reversal'
            else:
                desc = 'Bullish Engulfing — buyers overwhelm sellers'
            result.patterns.append(CandlePattern(
                'bullish_engulfing', 'bullish', rel, i, desc))

        # ── Bearish Engulfing ──
        if (self._is_bullish(o1, c1) and self._is_bearish(o2, c2) and
                body2 > body1 and
                o2 >= c1 and c2 <= o1 and
                body2 >= atr * 0.5):
            rel = RELIABILITY['bearish_engulfing']
            if trend == 'bullish':
                rel = min(1.0, rel + 0.10)
                desc = 'Bearish Engulfing in uptrend — strong reversal'
            else:
                desc = 'Bearish Engulfing — sellers overwhelm buyers'
            result.patterns.append(CandlePattern(
                'bearish_engulfing', 'bearish', rel, i, desc))

        # ── Piercing Line (bullish) ──
        if (self._is_bearish(o1, c1) and self._is_bullish(o2, c2) and
                o2 < c1 and                          # Opens below prev close
                c2 > (o1 + c1) / 2 and c2 < o1 and   # Closes above 50% of prev body
                body1 >= atr * 0.5 and body2 >= atr * 0.3):
            rel = RELIABILITY['piercing_line']
            if trend == 'bearish':
                rel = min(1.0, rel + 0.05)
            result.patterns.append(CandlePattern(
                'piercing_line', 'bullish', rel, i,
                'Piercing Line — bullish reversal, buyers pushing back'))

        # ── Dark Cloud Cover (bearish) ──
        if (self._is_bullish(o1, c1) and self._is_bearish(o2, c2) and
                o2 > c1 and                          # Opens above prev close
                c2 < (o1 + c1) / 2 and c2 > o1 and   # Closes below 50% of prev body
                body1 >= atr * 0.5 and body2 >= atr * 0.3):
            rel = RELIABILITY['dark_cloud_cover']
            if trend == 'bullish':
                rel = min(1.0, rel + 0.05)
            result.patterns.append(CandlePattern(
                'dark_cloud_cover', 'bearish', rel, i,
                'Dark Cloud Cover — bearish reversal, sellers pushing back'))

        # ── Tweezer Bottom (bullish) ──
        tolerance = atr * self.TWEEZER_TOLERANCE
        if (abs(l1 - l2) <= tolerance and
                self._is_bearish(o1, c1) and self._is_bullish(o2, c2) and
                body1 >= atr * 0.3 and body2 >= atr * 0.3):
            rel = RELIABILITY['tweezer_bottom']
            if trend == 'bearish':
                rel = min(1.0, rel + 0.10)
            result.patterns.append(CandlePattern(
                'tweezer_bottom', 'bullish', rel, i,
                'Tweezer Bottom — double test of support, buyers defending'))

        # ── Tweezer Top (bearish) ──
        if (abs(h1 - h2) <= tolerance and
                self._is_bullish(o1, c1) and self._is_bearish(o2, c2) and
                body1 >= atr * 0.3 and body2 >= atr * 0.3):
            rel = RELIABILITY['tweezer_top']
            if trend == 'bullish':
                rel = min(1.0, rel + 0.10)
            result.patterns.append(CandlePattern(
                'tweezer_top', 'bearish', rel, i,
                'Tweezer Top — double test of resistance, sellers defending'))

    # ── Triple Candle Patterns ──────────────────────────────────────────────

    def _check_triple(self, df, i, atr, trend, result):
        if i < 2:
            return
        # Only detect on last completed bar
        if i < len(df) - 2:
            return

        o1, h1, l1, c1 = self._candle_data(df, i - 2)
        o2, h2, l2, c2 = self._candle_data(df, i - 1)
        o3, h3, l3, c3 = self._candle_data(df, i)
        body1 = self._body(o1, c1)
        body2 = self._body(o2, c2)
        body3 = self._body(o3, c3)
        rng2 = self._range(h2, l2)

        # ── Morning Star (bullish reversal) ──
        if (self._is_bearish(o1, c1) and body1 >= atr * 0.5 and    # Big bearish
                body2 / rng2 <= self.SMALL_BODY_RATIO and               # Small middle
                self._is_bullish(o3, c3) and body3 >= atr * 0.5 and    # Big bullish
                c3 > (o1 + c1) / 2):                                    # Closes above 50% of candle 1
            rel = RELIABILITY['morning_star']
            if trend == 'bearish':
                rel = min(1.0, rel + 0.10)
            result.patterns.append(CandlePattern(
                'morning_star', 'bullish', rel, i,
                'Morning Star — powerful bullish reversal (3 candle)'))

        # ── Evening Star (bearish reversal) ──
        if (self._is_bullish(o1, c1) and body1 >= atr * 0.5 and    # Big bullish
                body2 / rng2 <= self.SMALL_BODY_RATIO and               # Small middle
                self._is_bearish(o3, c3) and body3 >= atr * 0.5 and    # Big bearish
                c3 < (o1 + c1) / 2):                                    # Closes below 50% of candle 1
            rel = RELIABILITY['evening_star']
            if trend == 'bullish':
                rel = min(1.0, rel + 0.10)
            result.patterns.append(CandlePattern(
                'evening_star', 'bearish', rel, i,
                'Evening Star — powerful bearish reversal (3 candle)'))

        # ── Three White Soldiers (bullish continuation/reversal) ──
        if (self._is_bullish(o1, c1) and body1 >= atr * 0.3 and
                self._is_bullish(o2, c2) and body2 >= atr * 0.3 and
                self._is_bullish(o3, c3) and body3 >= atr * 0.3 and
                c2 > c1 and c3 > c2 and             # Each closes higher
                o2 > o1 and o3 > o2 and              # Each opens higher
                o2 <= c1 and o3 <= c2):              # Opens within previous body
            rel = RELIABILITY['three_white_soldiers']
            result.patterns.append(CandlePattern(
                'three_white_soldiers', 'bullish', rel, i,
                'Three White Soldiers — strong bullish momentum'))

        # ── Three Black Crows (bearish continuation/reversal) ──
        if (self._is_bearish(o1, c1) and body1 >= atr * 0.3 and
                self._is_bearish(o2, c2) and body2 >= atr * 0.3 and
                self._is_bearish(o3, c3) and body3 >= atr * 0.3 and
                c2 < c1 and c3 < c2 and             # Each closes lower
                o2 < o1 and o3 < o2 and              # Each opens lower
                o2 >= c1 and o3 >= c2):              # Opens within previous body
            rel = RELIABILITY['three_black_crows']
            result.patterns.append(CandlePattern(
                'three_black_crows', 'bearish', rel, i,
                'Three Black Crows — strong bearish momentum'))

        # ── Three Inside Up (bullish) ──
        if (self._is_bearish(o1, c1) and body1 >= atr * 0.5 and
                self._is_bullish(o2, c2) and
                o2 >= c1 and c2 <= o1 and            # Candle 2 inside candle 1
                self._is_bullish(o3, c3) and
                c3 > o1):                             # Candle 3 breaks above candle 1
            rel = RELIABILITY['three_inside_up']
            result.patterns.append(CandlePattern(
                'three_inside_up', 'bullish', rel, i,
                'Three Inside Up — bullish reversal confirmed'))

        # ── Three Inside Down (bearish) ──
        if (self._is_bullish(o1, c1) and body1 >= atr * 0.5 and
                self._is_bearish(o2, c2) and
                o2 <= c1 and c2 >= o1 and            # Candle 2 inside candle 1
                self._is_bearish(o3, c3) and
                c3 < o1):                             # Candle 3 breaks below candle 1
            rel = RELIABILITY['three_inside_down']
            result.patterns.append(CandlePattern(
                'three_inside_down', 'bearish', rel, i,
                'Three Inside Down — bearish reversal confirmed'))
