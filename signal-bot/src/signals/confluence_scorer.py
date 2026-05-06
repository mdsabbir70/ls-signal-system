"""
Confluence Scorer
Combines signals from all sources into a single 0-100 score.
Only signals with score ≥ min_confluence_score (default 80) are used.

Scoring breakdown (100 points total):
  Technical Analysis    — 30 points
    EMA alignment       :   8
    MACD cross          :   6
    RSI condition       :   5
    ADX trend strength  :   5
    Candlestick pattern :   6

  Multi-Timeframe       — 15 points
    HTF (D1) trend      :   8
    MTF (H4) trend      :   7

  News/Sentiment        — 15 points
    News sentiment      :   8
    AI confidence       :   7

  Liquidity / SMC       — 20 points
    Order Block         :   6
    Fair Value Gap      :   5
    Market Structure    :   5
    Liquidity Sweep     :   4

  Market Conditions     — 20 points
    Market regime       :  10
    ATR/volatility      :   5
    Stochastic          :   5
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from indicators.indicator_engine import IndicatorResult
from indicators.market_regime import RegimeResult
from indicators.liquidity_analyzer import LiquidityResult
from indicators.candlestick_patterns import CandlestickResult
from indicators.session_manager import SessionContext
from indicators.correlation_analyzer import CorrelationResult
from indicators.sentiment_analyzer import SentimentResult
from utils.logger import setup_logger

logger = setup_logger('confluence')


@dataclass
class ScoreBreakdown:
    # Technical (30)
    ema_alignment:    float = 0.0
    macd_cross:       float = 0.0
    rsi_condition:    float = 0.0
    adx_strength:     float = 0.0
    candlestick:      float = 0.0
    # Multi-TF (15)
    htf_trend:        float = 0.0
    mtf_trend:        float = 0.0
    # News/Sentiment (15)
    news_sentiment:   float = 0.0
    ai_confidence:    float = 0.0
    # Liquidity/SMC (20)
    order_block:      float = 0.0
    fvg:              float = 0.0
    market_structure: float = 0.0
    liquidity_sweep:  float = 0.0
    # Market Conditions (20)
    market_regime:    float = 0.0
    volatility:       float = 0.0
    stochastic:       float = 0.0
    # Post-scoring modifiers (not part of base 100)
    session_modifier:     float = 0.0   # -5 to +5
    correlation_modifier: float = 0.0   # -5 to +3
    sentiment_modifier:   float = 0.0   # -5 to +5

    @property
    def total(self) -> float:
        base = sum([
            self.ema_alignment, self.macd_cross, self.rsi_condition, self.adx_strength,
            self.candlestick,
            self.htf_trend, self.mtf_trend,
            self.news_sentiment, self.ai_confidence,
            self.order_block, self.fvg, self.market_structure, self.liquidity_sweep,
            self.market_regime, self.volatility, self.stochastic,
        ])
        return base + self.session_modifier + self.correlation_modifier + self.sentiment_modifier

    @property
    def technical_total(self) -> float:
        return self.ema_alignment + self.macd_cross + self.rsi_condition + self.adx_strength + self.candlestick

    @property
    def mtf_total(self) -> float:
        return self.htf_trend + self.mtf_trend

    @property
    def news_total(self) -> float:
        return self.news_sentiment + self.ai_confidence

    @property
    def liquidity_total(self) -> float:
        return self.order_block + self.fvg + self.market_structure + self.liquidity_sweep

    @property
    def conditions_total(self) -> float:
        return self.market_regime + self.volatility + self.stochastic

    def to_dict(self) -> dict:
        return {
            'technical':     round(self.technical_total, 1),
            'multi_tf':      round(self.mtf_total, 1),
            'news':          round(self.news_total, 1),
            'liquidity':     round(self.liquidity_total, 1),
            'conditions':    round(self.conditions_total, 1),
            'total':         round(self.total, 1),
            'detail': {
                'ema_alignment':    self.ema_alignment,
                'macd_cross':       self.macd_cross,
                'rsi_condition':    self.rsi_condition,
                'adx_strength':     self.adx_strength,
                'candlestick':      self.candlestick,
                'htf_trend':        self.htf_trend,
                'mtf_trend':        self.mtf_trend,
                'news_sentiment':   self.news_sentiment,
                'ai_confidence':    self.ai_confidence,
                'order_block':      self.order_block,
                'fvg':              self.fvg,
                'market_structure': self.market_structure,
                'liquidity_sweep':  self.liquidity_sweep,
                'market_regime':    self.market_regime,
                'volatility':       self.volatility,
                'stochastic':       self.stochastic,
                'session_modifier':     self.session_modifier,
                'correlation_modifier': self.correlation_modifier,
                'sentiment_modifier':   self.sentiment_modifier,
            }
        }


def _quality_label(score: float) -> str:
    """Convert numeric score to signal quality label."""
    if score >= 92:
        return 'A+'
    elif score >= 85:
        return 'A'
    elif score >= 78:
        return 'B'
    elif score >= 70:
        return 'C'
    return 'D'


class ConfluenceScorer:
    """Calculates the confluence score for a potential trade signal."""

    def score(
        self,
        direction: str,           # 'BUY' or 'SELL'
        ltf: IndicatorResult,     # H1 indicators
        mtf: IndicatorResult,     # H4 indicators
        htf: IndicatorResult,     # D1 indicators
        regime: RegimeResult,
        news_sentiment: str = 'neutral',     # 'bullish' | 'bearish' | 'neutral'
        ai_confidence: float = 0.0,          # 0-100 from Claude
        trading_mode: str = 'hybrid',        # technical | news | hybrid | ai
        liquidity: LiquidityResult = None,   # SMC/Liquidity analysis
        candles: CandlestickResult = None,   # Candlestick patterns
        session: SessionContext = None,      # Session-aware context
        correlation: CorrelationResult = None,  # Correlation check
        sentiment: SentimentResult = None,    # Market sentiment
    ) -> tuple[float, ScoreBreakdown, str]:
        """
        Calculate confluence score.
        Returns (score_0_to_100, breakdown, quality_label)
        """
        bd = ScoreBreakdown()
        is_buy = direction == 'BUY'

        # ── Technical (30 points) ─────────────────────────────────────────

        # EMA alignment (10 pts)
        bd.ema_alignment = self._score_ema(ltf, is_buy)

        # MACD cross (8 pts)
        bd.macd_cross = self._score_macd(ltf, is_buy)

        # RSI condition (6 pts)
        bd.rsi_condition = self._score_rsi(ltf, is_buy)

        # ADX trend strength (5 pts)
        bd.adx_strength = self._score_adx(ltf)

        # Candlestick patterns (6 pts)
        bd.candlestick = self._score_candlestick(candles, is_buy)

        # ── Multi-Timeframe (15 points) ───────────────────────────────────

        # HTF (D1) trend (8 pts)
        if htf:
            bd.htf_trend = self._score_tf_alignment(htf, is_buy, weight=8)

        # MTF (H4) trend (7 pts)
        if mtf:
            bd.mtf_trend = self._score_tf_alignment(mtf, is_buy, weight=7)

        # ── News/Sentiment (15 points) — only if news/hybrid/ai mode ─────

        if trading_mode in ('news', 'hybrid', 'ai'):
            # News sentiment (8 pts)
            bd.news_sentiment = self._score_news(news_sentiment, is_buy)

            # AI confidence (7 pts)
            bd.ai_confidence = self._score_ai(ai_confidence, is_buy, news_sentiment)

        elif trading_mode in ('technical', 'technical_news_filter'):
            # Redistribute 15 news points: +5 tech, +5 liquidity, +5 conditions
            bd.ema_alignment = min(bd.ema_alignment + 3, 11)
            bd.macd_cross    = min(bd.macd_cross + 2, 8)
            bd.order_block   = min(bd.order_block + 5, 11)
            bd.market_regime = min(bd.market_regime + 5, 15)

        # ── Liquidity / SMC (20 points) ───────────────────────────────────

        if liquidity:
            # Order Block alignment (6 pts)
            bd.order_block += self._score_order_block(liquidity, is_buy)

            # Fair Value Gap (5 pts)
            bd.fvg = self._score_fvg(liquidity, is_buy)

            # Market Structure — BOS/CHoCH (5 pts)
            bd.market_structure = self._score_structure(liquidity, is_buy)

            # Liquidity Sweep (4 pts)
            bd.liquidity_sweep = self._score_liquidity_sweep(liquidity, is_buy)

        # ── Market Conditions (20 points) ────────────────────────────────

        # Market regime (10 pts)
        bd.market_regime += self._score_regime(regime, is_buy)

        # Volatility (5 pts)
        bd.volatility = self._score_volatility(ltf)

        # Stochastic (5 pts)
        bd.stochastic = self._score_stochastic(ltf, is_buy)

        # ── Session Modifier (-5 to +5) ──────────────────────────────────
        if session:
            bd.session_modifier = session.score_modifier

        # ── Correlation Modifier (-5 to +3) ──────────────────────────────
        if correlation:
            raw_corr = correlation.confirmation_boost - correlation.overexposure_penalty
            bd.correlation_modifier = max(-5.0, min(3.0, raw_corr))

        # ── Sentiment Modifier (-5 to +5) ────────────────────────────────
        if sentiment:
            bd.sentiment_modifier = sentiment.score_modifier

        # ── Final score ───────────────────────────────────────────────────
        raw_score = bd.total
        clamped   = max(0.0, min(100.0, raw_score))
        label     = _quality_label(clamped)

        session_str = f" sess={bd.session_modifier:+.1f}" if session else ""
        corr_str = f" corr={bd.correlation_modifier:+.1f}" if correlation else ""
        sent_str = f" sent={bd.sentiment_modifier:+.1f}" if sentiment else ""
        logger.debug(
            f"{direction} score={clamped:.1f} ({label}) | "
            f"tech={bd.technical_total:.0f} mtf={bd.mtf_total:.0f} "
            f"news={bd.news_total:.0f} liq={bd.liquidity_total:.0f} "
            f"cond={bd.conditions_total:.0f}{session_str}{corr_str}{sent_str}"
        )

        return round(clamped, 2), bd, label

    # ── Scoring sub-methods ────────────────────────────────────────────────

    @staticmethod
    def _score_ema(r: IndicatorResult, is_buy: bool) -> float:
        """EMA alignment score 0-8."""
        if r.ema20 is None or r.ema50 is None:
            return 0.0

        if is_buy:
            if r.close > r.ema20 > r.ema50:
                base = 5.0
                if r.ema200 and r.close > r.ema200:
                    base += 3.0
                return base
            elif r.close > r.ema20:
                return 3.0
        else:
            if r.close < r.ema20 < r.ema50:
                base = 5.0
                if r.ema200 and r.close < r.ema200:
                    base += 3.0
                return base
            elif r.close < r.ema20:
                return 3.0
        return 0.0

    @staticmethod
    def _score_macd(r: IndicatorResult, is_buy: bool) -> float:
        """MACD score 0-6."""
        if r.macd is None or r.macd_signal is None:
            return 0.0

        if is_buy:
            if r.macd_bullish_cross:
                return 6.0
            elif r.macd > r.macd_signal:
                return 4.0
        else:
            if r.macd_bearish_cross:
                return 6.0
            elif r.macd < r.macd_signal:
                return 4.0
        return 0.0

    @staticmethod
    def _score_rsi(r: IndicatorResult, is_buy: bool) -> float:
        """RSI score 0-5."""
        if r.rsi is None:
            return 0.0

        if is_buy:
            if 40 <= r.rsi <= 60:
                return 5.0
            elif 30 <= r.rsi < 40:
                return 3.5
            elif r.rsi < 30:
                return 2.5
            elif 60 < r.rsi <= 70:
                return 1.5
            else:
                return 0.0
        else:
            if 40 <= r.rsi <= 60:
                return 5.0
            elif 60 < r.rsi <= 70:
                return 3.5
            elif r.rsi > 70:
                return 2.5
            elif 30 <= r.rsi < 40:
                return 1.5
            else:
                return 0.0

    @staticmethod
    def _score_adx(r: IndicatorResult) -> float:
        """ADX trend strength score 0-5."""
        if r.adx is None:
            return 0.0
        if r.adx >= 35:
            return 5.0
        elif r.adx >= 25:
            return 3.5
        elif r.adx >= 20:
            return 1.5
        return 0.0

    @staticmethod
    def _score_candlestick(candles: CandlestickResult, is_buy: bool) -> float:
        """Candlestick pattern score 0-6."""
        if candles is None or not candles.patterns:
            return 0.0

        # Get the strongest pattern in the trade direction
        target = candles.strongest_bullish if is_buy else candles.strongest_bearish
        if target is None:
            # Opposing patterns present = negative signal
            opposing = candles.strongest_bearish if is_buy else candles.strongest_bullish
            if opposing and opposing.reliability >= 0.6:
                return 0.0
            return 0.0

        # Base score from reliability (0-1 mapped to 0-4)
        base = target.reliability * 4.0

        # Bonus for bias alignment (pattern consensus matches direction)
        if (is_buy and candles.signal_bias == 'bullish') or \
           (not is_buy and candles.signal_bias == 'bearish'):
            base += 1.0

        # Bonus for high confidence (multiple confirming patterns)
        if candles.confidence >= 0.7:
            base += 1.0
        elif candles.confidence >= 0.4:
            base += 0.5

        return min(6.0, round(base, 1))

    @staticmethod
    def _score_tf_alignment(r: IndicatorResult, is_buy: bool, weight: int = 10) -> float:
        """Timeframe alignment score."""
        if r.trend_direction == ('UP' if is_buy else 'DOWN'):
            return float(weight)
        elif r.trend_direction == 'SIDEWAYS':
            return float(weight) * 0.3    # Partial credit
        return 0.0

    @staticmethod
    def _score_news(sentiment: str, is_buy: bool) -> float:
        """News sentiment score 0-8."""
        if is_buy:
            return {'bullish': 8.0, 'neutral': 3.0, 'bearish': 0.0}.get(sentiment, 3.0)
        else:
            return {'bearish': 8.0, 'neutral': 3.0, 'bullish': 0.0}.get(sentiment, 3.0)

    @staticmethod
    def _score_ai(ai_confidence: float, is_buy: bool, sentiment: str) -> float:
        """AI confidence score 0-7."""
        if ai_confidence <= 0:
            return 0.0
        direction_confirmed = (
            (is_buy  and sentiment == 'bullish') or
            (not is_buy and sentiment == 'bearish')
        )
        if not direction_confirmed:
            return 0.0
        return min(7.0, ai_confidence / 14.3)  # 100% confidence → 7 pts

    # ── Liquidity / SMC scoring ───────────────────────────────────────────

    @staticmethod
    def _score_order_block(liq: LiquidityResult, is_buy: bool) -> float:
        """Order Block alignment score 0-6."""
        if liq.at_order_block == 'none':
            return 0.0

        if is_buy and liq.at_order_block == 'bullish':
            return round(6.0 * max(0.5, liq.ob_strength), 1)
        elif not is_buy and liq.at_order_block == 'bearish':
            return round(6.0 * max(0.5, liq.ob_strength), 1)
        # At opposing OB → penalty (don't enter against institutional flow)
        return 0.0

    @staticmethod
    def _score_fvg(liq: LiquidityResult, is_buy: bool) -> float:
        """Fair Value Gap score 0-5."""
        if liq.at_fvg == 'none':
            return 0.0

        # Bullish FVG below price = support (good for BUY)
        # Bearish FVG above price = resistance (good for SELL)
        if is_buy and liq.at_fvg == 'bullish':
            return round(5.0 * max(0.5, liq.fvg_strength), 1)
        elif not is_buy and liq.at_fvg == 'bearish':
            return round(5.0 * max(0.5, liq.fvg_strength), 1)
        return 0.0

    @staticmethod
    def _score_structure(liq: LiquidityResult, is_buy: bool) -> float:
        """Market structure (BOS/CHoCH) score 0-5."""
        if liq.latest_break == 'none':
            # Use structure trend as fallback
            if is_buy and liq.structure_trend == 'bullish':
                return 3.0
            elif not is_buy and liq.structure_trend == 'bearish':
                return 3.0
            return 0.0

        # CHoCH = stronger signal (reversal confirmation)
        if is_buy:
            if liq.latest_break == 'CHoCH_bullish':
                return 5.0
            elif liq.latest_break == 'BOS_bullish':
                return 4.0
        else:
            if liq.latest_break == 'CHoCH_bearish':
                return 5.0
            elif liq.latest_break == 'BOS_bearish':
                return 4.0
        return 0.0

    @staticmethod
    def _score_liquidity_sweep(liq: LiquidityResult, is_buy: bool) -> float:
        """Liquidity sweep score 0-4."""
        score = 0.0

        # SSL swept = smart money grabbed sell-side stops → bullish
        if is_buy and liq.ssl_swept:
            score += 4.0
        # BSL swept = smart money grabbed buy-side stops → bearish
        elif not is_buy and liq.bsl_swept:
            score += 4.0

        # Premium/discount zone bonus
        if is_buy and liq.zone == 'discount':
            score = max(score, 2.0)  # Buying in discount = smart
        elif not is_buy and liq.zone == 'premium':
            score = max(score, 2.0)  # Selling in premium = smart

        return min(4.0, score)

    @staticmethod
    def _score_regime(regime: RegimeResult, is_buy: bool) -> float:
        """Market regime score 0-10."""
        if not regime.tradeable:
            return 0.0
        if regime.regime == 'TRENDING_UP' and is_buy:
            return 10.0
        if regime.regime == 'TRENDING_DOWN' and not is_buy:
            return 10.0
        return 3.0  # Partial — regime exists but wrong direction

    @staticmethod
    def _score_volatility(r: IndicatorResult) -> float:
        """Volatility score 0-5 (medium volatility = best)."""
        if r.atr_pct is None:
            return 3.0  # Unknown — give middle score
        if 0.1 <= r.atr_pct <= 0.5:
            return 5.0   # Ideal range
        elif 0.5 < r.atr_pct <= 0.8:
            return 3.0   # Slightly high
        elif r.atr_pct > 0.8:
            return 0.0   # Too volatile
        else:
            return 1.0   # Too quiet

    @staticmethod
    def _score_stochastic(r: IndicatorResult, is_buy: bool) -> float:
        """Stochastic oscillator score 0-5."""
        if r.stoch_k is None or r.stoch_d is None:
            return 0.0

        if is_buy:
            if r.stoch_k < 20 and r.stoch_k > r.stoch_d:
                return 5.0   # Oversold + bullish cross
            elif r.stoch_k < 50:
                return 3.0
        else:
            if r.stoch_k > 80 and r.stoch_k < r.stoch_d:
                return 5.0   # Overbought + bearish cross
            elif r.stoch_k > 50:
                return 3.0
        return 0.0
