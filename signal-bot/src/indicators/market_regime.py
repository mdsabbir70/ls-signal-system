"""
Market Regime Detector
Classifies current market as: TRENDING_UP, TRENDING_DOWN, RANGING,
HIGH_VOLATILITY, or LOW_VOLATILITY.

Used by the signal generator to filter out unsuitable market conditions.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from indicators.indicator_engine import IndicatorResult
from utils.logger import setup_logger

logger = setup_logger('market_regime')


@dataclass
class RegimeResult:
    regime: str            # TRENDING_UP | TRENDING_DOWN | RANGING | HIGH_VOL | LOW_VOL
    confidence: float      # 0-100
    tradeable: bool        # Is this regime suitable for trading?
    reason: str            # Human-readable explanation

    # Sub-components
    trend_strength: str    # STRONG | MODERATE | WEAK | NONE
    volatility_state: str  # NORMAL | HIGH | LOW
    momentum_state: str    # BULLISH | BEARISH | NEUTRAL


class MarketRegimeDetector:
    """
    Classifies market regime using ADX, ATR, EMAs, and Bollinger Width.

    Thresholds (tuned for Forex H1/H4):
      ADX > 25        → Strong trend
      ADX 20-25       → Moderate trend
      ADX < 20        → Ranging / weak trend
      ATR% > 0.5%     → High volatility (H1 Forex)
      ATR% < 0.1%     → Low volatility
      BB Width > 0.01 → Expanded (trending/volatile)
      BB Width < 0.003 → Compressed (ranging, breakout imminent)
    """

    ADX_STRONG_TREND  = 25.0
    ADX_MODERATE      = 20.0
    ATR_PCT_HIGH_VOL  = 0.5    # % of price (H1 baseline)
    ATR_PCT_LOW_VOL   = 0.1
    BB_WIDTH_EXPANDED = 0.010
    BB_WIDTH_SQUEEZE  = 0.003

    # Volatility threshold scaling per timeframe (H1 = 1.0 baseline)
    # Lower TFs have smaller ATR% so thresholds scale down proportionally
    TF_VOL_SCALE = {
        'M5': 0.15, 'M15': 0.30, 'M30': 0.50,
        'H1': 1.0,  'H4': 1.8,  'D1': 3.0, 'W1': 5.0,
    }

    def detect(
        self,
        ltf: IndicatorResult,        # H1 (primary)
        mtf: IndicatorResult = None, # H4
        htf: IndicatorResult = None, # D1
        timeframe: str = 'H1',       # Primary timeframe for threshold scaling
    ) -> RegimeResult:
        """
        Detect regime from multi-timeframe indicator data.
        LTF is primary; MTF/HTF add confirmation.
        """
        trend_strength  = self._assess_trend_strength(ltf, mtf)
        volatility_state = self._assess_volatility(ltf, timeframe)
        momentum_state   = self._assess_momentum(ltf)
        htf_trend        = htf.trend_direction if htf else 'UNKNOWN'

        # ── Determine regime ──────────────────────────────────────────────
        if volatility_state == 'HIGH':
            regime = 'HIGH_VOLATILITY'
            tradeable = False
            reason = f"High volatility (ATR={ltf.atr_pct:.2f}% of price) — risk too high"

        elif volatility_state == 'LOW':
            regime = 'LOW_VOLATILITY'
            tradeable = False
            reason = f"Low volatility (ATR={ltf.atr_pct:.2f}%) — not enough momentum"

        elif trend_strength in ('STRONG', 'MODERATE'):
            if momentum_state == 'BULLISH':
                regime = 'TRENDING_UP'
                tradeable = True
                reason = f"Strong uptrend (ADX={ltf.adx:.1f}, EMA={ltf.trend_direction})"
            elif momentum_state == 'BEARISH':
                regime = 'TRENDING_DOWN'
                tradeable = True
                reason = f"Strong downtrend (ADX={ltf.adx:.1f}, EMA={ltf.trend_direction})"
            else:
                regime = 'RANGING'
                tradeable = False
                reason = "Trend strength detected but direction unclear — ranging"

        else:
            regime = 'RANGING'
            tradeable = False
            reason = f"Low ADX ({ltf.adx:.1f} < {self.ADX_MODERATE}) — ranging market"

        # HTF alignment check: if HTF contradicts LTF trend → reduce tradeable confidence
        htf_conflict = (
            regime == 'TRENDING_UP'   and htf_trend == 'DOWN' or
            regime == 'TRENDING_DOWN' and htf_trend == 'UP'
        )
        if htf_conflict:
            tradeable = False
            reason += f" (blocked: HTF trend={htf_trend} conflicts)"

        confidence = self._calc_confidence(ltf, trend_strength, volatility_state)

        return RegimeResult(
            regime=regime,
            confidence=confidence,
            tradeable=tradeable,
            reason=reason,
            trend_strength=trend_strength,
            volatility_state=volatility_state,
            momentum_state=momentum_state,
        )

    # ── Internal assessment methods ────────────────────────────────────────

    def _assess_trend_strength(
        self,
        ltf: IndicatorResult,
        mtf: Optional[IndicatorResult],
    ) -> str:
        """Classify trend strength: STRONG | MODERATE | WEAK | NONE."""
        adx = ltf.adx

        if adx is None:
            return 'NONE'

        # MTF confirmation adds to strength
        mtf_confirms = (
            mtf is not None and
            mtf.trend_direction == ltf.trend_direction and
            ltf.trend_direction != 'SIDEWAYS'
        )

        if adx >= self.ADX_STRONG_TREND:
            return 'STRONG' if mtf_confirms else 'MODERATE'
        elif adx >= self.ADX_MODERATE:
            return 'MODERATE' if mtf_confirms else 'WEAK'
        else:
            return 'WEAK'

    def _assess_volatility(self, ltf: IndicatorResult, timeframe: str = 'H1') -> str:
        """Classify volatility: HIGH | NORMAL | LOW. Scaled by timeframe."""
        if ltf.atr_pct is None:
            return 'NORMAL'
        scale = self.TF_VOL_SCALE.get(timeframe, 1.0)
        high_thresh = self.ATR_PCT_HIGH_VOL * scale
        low_thresh  = self.ATR_PCT_LOW_VOL * scale
        if ltf.atr_pct > high_thresh:
            return 'HIGH'
        if ltf.atr_pct < low_thresh:
            return 'LOW'
        return 'NORMAL'

    @staticmethod
    def _assess_momentum(ltf: IndicatorResult) -> str:
        """Classify momentum direction: BULLISH | BEARISH | NEUTRAL."""
        signals_bull = 0
        signals_bear = 0

        # EMA alignment
        if ltf.trend_direction == 'UP':
            signals_bull += 2
        elif ltf.trend_direction == 'DOWN':
            signals_bear += 2

        # MACD
        if ltf.macd is not None and ltf.macd_signal is not None:
            if ltf.macd > ltf.macd_signal:
                signals_bull += 1
            else:
                signals_bear += 1

        # DI+/DI-
        if ltf.dmi_pos is not None and ltf.dmi_neg is not None:
            if ltf.dmi_pos > ltf.dmi_neg:
                signals_bull += 1
            else:
                signals_bear += 1

        if signals_bull > signals_bear:
            return 'BULLISH'
        elif signals_bear > signals_bull:
            return 'BEARISH'
        return 'NEUTRAL'

    @staticmethod
    def _calc_confidence(
        ltf: IndicatorResult,
        trend_strength: str,
        volatility_state: str,
    ) -> float:
        """Calculate regime detection confidence 0-100."""
        score = 50.0

        # ADX contribution
        if ltf.adx is not None:
            if ltf.adx >= 30:
                score += 20
            elif ltf.adx >= 25:
                score += 15
            elif ltf.adx >= 20:
                score += 5
            else:
                score -= 10

        # Trend strength
        strength_scores = {'STRONG': 15, 'MODERATE': 10, 'WEAK': 0, 'NONE': -10}
        score += strength_scores.get(trend_strength, 0)

        # Volatility penalty
        if volatility_state != 'NORMAL':
            score -= 10

        return max(0.0, min(100.0, round(score, 1)))
