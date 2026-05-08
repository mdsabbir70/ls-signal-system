"""
Market Regime Detector
Classifies current market as: TRENDING_UP, TRENDING_DOWN, RANGING,
HIGH_VOLATILITY, or LOW_VOLATILITY.

Used by the signal generator to filter out unsuitable market conditions.
Crypto pairs use scaled thresholds since crypto is naturally more volatile.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from indicators.indicator_engine import IndicatorResult
from utils.logger import setup_logger

logger = setup_logger('market_regime')


# Crypto pairs have USDT suffix — they need higher volatility thresholds
CRYPTO_SUFFIXES = ('USDT', 'USDC', 'BTC', 'ETH', 'BNB')


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
      ADX > 25        -> Strong trend
      ADX 20-25       -> Moderate trend
      ADX < 20        -> Ranging / weak trend
      ATR% > 0.5%     -> High volatility (H1 Forex)
      ATR% < 0.1%     -> Low volatility
      BB Width > 0.01 -> Expanded (trending/volatile)
      BB Width < 0.003 -> Compressed (ranging, breakout imminent)

    Crypto pairs use 3x higher ATR% thresholds since crypto markets
    are naturally more volatile than forex.
    """

    ADX_STRONG_TREND  = 25.0
    ADX_MODERATE      = 20.0
    ADX_WEAK_RANGE    = 15.0   # Below this = very weak, reduce confidence
    ATR_PCT_HIGH_VOL  = 0.5    # % of price (H1 baseline, forex)
    ATR_PCT_LOW_VOL   = 0.1
    BB_WIDTH_EXPANDED = 0.010
    BB_WIDTH_SQUEEZE  = 0.003

    # Crypto pairs have higher natural volatility — scale thresholds up
    CRYPTO_VOL_MULTIPLIER = 3.0

    # Volatility threshold scaling per timeframe (H1 = 1.0 baseline)
    TF_VOL_SCALE = {
        'M5': 0.15, 'M15': 0.30, 'M30': 0.50,
        'H1': 1.0,  'H4': 1.8,  'D1': 3.0, 'W1': 5.0,
    }

    @staticmethod
    def _is_crypto(pair: str) -> bool:
        """Check if pair is a crypto pair."""
        return any(pair.upper().endswith(suffix) for suffix in CRYPTO_SUFFIXES)

    def detect(
        self,
        ltf: IndicatorResult,        # H1 (primary)
        mtf: IndicatorResult = None, # H4
        htf: IndicatorResult = None, # D1
        timeframe: str = 'H1',       # Primary timeframe for threshold scaling
        pair: str = '',              # Pair symbol for crypto detection
    ) -> RegimeResult:
        """
        Detect regime from multi-timeframe indicator data.
        LTF is primary; MTF/HTF add confirmation.
        """
        is_crypto = self._is_crypto(pair)
        trend_strength  = self._assess_trend_strength(ltf, mtf)
        volatility_state = self._assess_volatility(ltf, timeframe, is_crypto)
        momentum_state   = self._assess_momentum(ltf)
        htf_trend        = htf.trend_direction if htf else 'UNKNOWN'

        # -- Determine regime ------------------------------------------------
        if volatility_state == 'HIGH':
            regime = 'HIGH_VOLATILITY'
            if is_crypto:
                # Crypto is naturally volatile — still tradeable if trending
                if trend_strength in ('STRONG', 'MODERATE') and momentum_state != 'NEUTRAL':
                    tradeable = True
                    reason = (f"High volatility crypto (ATR={ltf.atr_pct:.2f}%) "
                             f"but trending — tradeable with caution")
                else:
                    tradeable = False
                    reason = (f"High volatility crypto (ATR={ltf.atr_pct:.2f}%) "
                             f"and no clear trend — too risky")
            else:
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
                # Trend strength but neutral momentum — still tradeable, reduced confidence
                regime = 'RANGING'
                tradeable = True
                reason = f"ADX={ltf.adx:.1f} shows trend but direction unclear — range-trading ok"

        elif trend_strength == 'WEAK' and ltf.adx is not None and ltf.adx >= self.ADX_WEAK_RANGE:
            # ADX 15-20: weak trend but not dead — tradeable with lower confidence
            regime = 'RANGING'
            if momentum_state != 'NEUTRAL':
                tradeable = True
                reason = f"Weak trend (ADX={ltf.adx:.1f}) with {momentum_state.lower()} bias — cautious trading"
            else:
                tradeable = False
                reason = f"Weak trend (ADX={ltf.adx:.1f}) and no direction — wait for breakout"

        else:
            regime = 'RANGING'
            tradeable = False
            reason = f"Low ADX ({(ltf.adx or 0):.1f} < {self.ADX_WEAK_RANGE}) — dead market"

        # HTF alignment check: if HTF contradicts LTF trend, reduce confidence but don't hard-block
        htf_conflict = (
            regime == 'TRENDING_UP'   and htf_trend == 'DOWN' or
            regime == 'TRENDING_DOWN' and htf_trend == 'UP'
        )
        if htf_conflict:
            # Don't hard-block — the scorer already penalizes HTF misalignment
            # Just note it in reason and reduce confidence
            reason += f" [HTF={htf_trend} conflicts — lower confidence]"
            logger.debug(f"HTF conflict: LTF={regime} but HTF={htf_trend}")

        confidence = self._calc_confidence(ltf, trend_strength, volatility_state, htf_conflict)

        return RegimeResult(
            regime=regime,
            confidence=confidence,
            tradeable=tradeable,
            reason=reason,
            trend_strength=trend_strength,
            volatility_state=volatility_state,
            momentum_state=momentum_state,
        )

    # -- Internal assessment methods ----------------------------------------

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

    def _assess_volatility(self, ltf: IndicatorResult, timeframe: str = 'H1',
                           is_crypto: bool = False) -> str:
        """Classify volatility: HIGH | NORMAL | LOW. Scaled by timeframe and asset type."""
        if ltf.atr_pct is None:
            return 'NORMAL'
        scale = self.TF_VOL_SCALE.get(timeframe, 1.0)

        # Crypto pairs get higher thresholds — crypto IS volatile
        crypto_mult = self.CRYPTO_VOL_MULTIPLIER if is_crypto else 1.0

        high_thresh = self.ATR_PCT_HIGH_VOL * scale * crypto_mult
        low_thresh  = self.ATR_PCT_LOW_VOL * scale * crypto_mult

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
        htf_conflict: bool = False,
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
            elif ltf.adx >= 15:
                score -= 5
            else:
                score -= 10

        # Trend strength
        strength_scores = {'STRONG': 15, 'MODERATE': 10, 'WEAK': 0, 'NONE': -10}
        score += strength_scores.get(trend_strength, 0)

        # Volatility penalty
        if volatility_state != 'NORMAL':
            score -= 10

        # HTF conflict penalty
        if htf_conflict:
            score -= 10

        return max(0.0, min(100.0, round(score, 1)))
