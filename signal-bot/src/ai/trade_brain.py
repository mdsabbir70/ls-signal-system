"""
AI Trade Brain — Claude-Powered Full-Context Analyzer

Unlike the basic NewsAnalyzer (headlines only), TradeBrain receives
the COMPLETE market picture and reasons like a professional trader:

  Context it receives:
    - Technical indicators (RSI, MACD, EMA, ADX, Stochastic, ATR)
    - Candlestick patterns detected (Engulfing, Pin Bar, etc.)
    - Liquidity / SMC analysis (OB, FVG, structure, sweeps)
    - Session context (kill zones, overlaps, session quality)
    - Economic calendar (upcoming events, recent event bias)
    - Correlation data (open positions, overexposure risk)
    - Market regime (trending/ranging/volatile)
    - Multi-timeframe alignment (H1, H4, D1)
    - Recent news sentiment
    - Current confluence score breakdown

  What it returns:
    - AI verdict: STRONG_BUY | BUY | NEUTRAL | SELL | STRONG_SELL
    - Confidence: 0-100
    - Professional reasoning (2-3 sentences)
    - Risk assessment: LOW | MEDIUM | HIGH
    - SL/TP adjustment suggestion
    - Score modifier: -7 to +7 (applied to final confluence)

  Cost optimization:
    - Only called AFTER a signal passes minimum confluence threshold
    - Cached per pair+direction for 15 minutes
    - Uses Claude Haiku (fast + cheap)
    - Single API call with structured prompt
    - Max 600 tokens response

Usage:
    brain = TradeBrain(config)
    verdict = await brain.analyze_trade(context_dict)
"""

from __future__ import annotations
import asyncio
import json
import time
from dataclasses import dataclass
from typing import Optional

import anthropic

from utils.logger import setup_logger

logger = setup_logger('trade_brain')


@dataclass
class AIVerdict:
    """Result from AI Trade Brain analysis."""
    verdict: str = 'NEUTRAL'        # STRONG_BUY | BUY | NEUTRAL | SELL | STRONG_SELL
    confidence: float = 0.0          # 0-100
    reasoning: str = ''              # Professional trade reasoning
    risk_level: str = 'MEDIUM'       # LOW | MEDIUM | HIGH
    score_modifier: float = 0.0      # -7 to +7
    sl_adjustment: str = 'none'      # 'widen' | 'tighten' | 'none'
    tp_adjustment: str = 'none'      # 'extend' | 'reduce' | 'none'
    key_factors: list = None         # Top 3 factors driving the verdict
    market_context: str = ''         # One-line market context

    def __post_init__(self):
        if self.key_factors is None:
            self.key_factors = []

    def to_dict(self) -> dict:
        return {
            'verdict': self.verdict,
            'confidence': self.confidence,
            'reasoning': self.reasoning,
            'risk_level': self.risk_level,
            'score_modifier': self.score_modifier,
            'sl_adjustment': self.sl_adjustment,
            'tp_adjustment': self.tp_adjustment,
            'key_factors': self.key_factors,
            'market_context': self.market_context,
        }


class TradeBrain:
    """Claude-powered full-context trade analyzer."""

    CACHE_TTL = 900  # 15 minutes

    def __init__(self, config):
        self.config = config
        self._client: Optional[anthropic.Anthropic] = None
        self._cache: dict = {}
        self._init_client()

    def _init_client(self):
        """Initialize Claude client."""
        api_key = self.config.ANTHROPIC_API_KEY
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set — AI Brain disabled")
            return
        try:
            self._client = anthropic.Anthropic(api_key=api_key)
            logger.info(f"AI Trade Brain initialized (model: {self.config.claude_model})")
        except Exception as e:
            logger.error(f"Failed to init Trade Brain: {e}")

    async def analyze_trade(self, context: dict) -> AIVerdict:
        """
        Analyze a potential trade with full market context.

        Args:
            context: {
                'pair': str,
                'direction': str,
                'score': float,
                'score_breakdown': dict,
                'indicators': dict,
                'candlestick': str,
                'liquidity': str,
                'session': dict,
                'correlation': dict,
                'econ_gate': str,
                'econ_bias': dict,
                'regime': str,
                'htf_trend': str,
                'mtf_trend': str,
                'news_sentiment': str,
                'news_reasoning': str,
            }
        """
        if not self._client:
            return AIVerdict()

        pair = context.get('pair', '')
        direction = context.get('direction', '')
        cache_key = f"{pair}_{direction}_{int(time.time() // self.CACHE_TTL)}"

        cached = self._cache.get(cache_key)
        if cached:
            logger.debug(f"AI Brain cache hit: {pair} {direction}")
            return cached

        loop = asyncio.get_event_loop()
        verdict = await loop.run_in_executor(
            None, self._call_claude, context
        )

        if verdict:
            self._cache[cache_key] = verdict
            logger.info(
                f"AI Brain: {pair} {direction} → {verdict.verdict} "
                f"(conf={verdict.confidence:.0f}, mod={verdict.score_modifier:+.1f})"
            )

        return verdict or AIVerdict()

    def _call_claude(self, ctx: dict) -> Optional[AIVerdict]:
        """Build prompt, call Claude, parse response."""
        prompt = self._build_prompt(ctx)

        try:
            message = self._client.messages.create(
                model=self.config.claude_model,
                max_tokens=600,
                messages=[{"role": "user", "content": prompt}],
            )

            content = message.content[0].text.strip()
            return self._parse_response(content, ctx)

        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            return None
        except Exception as e:
            logger.error(f"AI Brain failed: {e}")
            return None

    @staticmethod
    def _build_prompt(ctx: dict) -> str:
        """Build comprehensive trading context prompt."""
        pair = ctx.get('pair', 'UNKNOWN')
        direction = ctx.get('direction', 'UNKNOWN')
        score = ctx.get('score', 0)
        bd = ctx.get('score_breakdown', {})
        ind = ctx.get('indicators', {})
        regime = ctx.get('regime', 'UNKNOWN')
        htf = ctx.get('htf_trend', 'UNKNOWN')
        mtf = ctx.get('mtf_trend', 'UNKNOWN')

        # Format indicators
        rsi = ind.get('rsi', 'N/A')
        macd = ind.get('macd', 'N/A')
        macd_sig = ind.get('macd_signal', 'N/A')
        adx = ind.get('adx', 'N/A')
        ema20 = ind.get('ema20', 'N/A')
        ema50 = ind.get('ema50', 'N/A')
        ema200 = ind.get('ema200', 'N/A')
        atr_pct = ind.get('atr_pct', 'N/A')
        stoch_k = ind.get('stoch_k', 'N/A')
        stoch_d = ind.get('stoch_d', 'N/A')
        close = ind.get('close', 'N/A')

        # Score breakdown
        tech = bd.get('technical', 0)
        mtf_score = bd.get('multi_tf', 0)
        news_score = bd.get('news', 0)
        liq_score = bd.get('liquidity', 0)
        cond_score = bd.get('conditions', 0)

        # Session context
        sess = ctx.get('session', {})
        sess_quality = sess.get('session_quality', 'unknown')
        kill_zone = sess.get('kill_zone', '')
        in_overlap = sess.get('in_overlap', False)

        # Other context
        candles = ctx.get('candlestick', 'None detected')
        liquidity = ctx.get('liquidity', 'N/A')
        econ_gate = ctx.get('econ_gate', 'CLEAR')
        econ_bias = ctx.get('econ_bias', {})
        econ_bias_str = econ_bias.get('bias', 'neutral') if isinstance(econ_bias, dict) else 'neutral'
        econ_reason = econ_bias.get('reason', '') if isinstance(econ_bias, dict) else ''
        news_sent = ctx.get('news_sentiment', 'neutral')
        news_reason = ctx.get('news_reasoning', '')
        corr = ctx.get('correlation', {})
        corr_action = corr.get('action', 'ALLOW') if isinstance(corr, dict) else 'ALLOW'
        corr_reason = corr.get('reason', '') if isinstance(corr, dict) else ''

        return f"""You are a professional Forex/Crypto trader with 15 years of experience. Analyze this potential trade setup and give your verdict.

PAIR: {pair}
PROPOSED DIRECTION: {direction}
CURRENT SCORE: {score:.1f}/100

══ TECHNICAL INDICATORS (H1) ══
Price: {close}
EMA20: {ema20} | EMA50: {ema50} | EMA200: {ema200}
RSI(14): {rsi}
MACD: {macd} | Signal: {macd_sig}
ADX: {adx}
Stochastic K: {stoch_k} | D: {stoch_d}
ATR%: {atr_pct}

══ SCORE BREAKDOWN ══
Technical: {tech}/30 | MTF: {mtf_score}/15 | News: {news_score}/15 | Liquidity: {liq_score}/20 | Conditions: {cond_score}/20

══ MARKET STRUCTURE ══
Regime: {regime}
D1 Trend: {htf} | H4 Trend: {mtf}

══ CANDLESTICK PATTERNS ══
{candles}

══ SMART MONEY / LIQUIDITY ══
{liquidity}

══ SESSION CONTEXT ══
Quality: {sess_quality} | Kill Zone: {kill_zone or 'None'} | Overlap: {'Yes' if in_overlap else 'No'}

══ ECONOMIC CALENDAR ══
Gate: {econ_gate} | Bias: {econ_bias_str} {('— ' + econ_reason) if econ_reason else ''}

══ NEWS SENTIMENT ══
{news_sent.upper()}{(': ' + news_reason) if news_reason else ''}

══ CORRELATION ══
{corr_action}: {corr_reason}

Based on ALL the above context, respond in valid JSON ONLY:
{{
  "verdict": "STRONG_BUY|BUY|NEUTRAL|SELL|STRONG_SELL",
  "confidence": 0-100,
  "reasoning": "2-3 sentence professional analysis explaining WHY",
  "risk_level": "LOW|MEDIUM|HIGH",
  "score_modifier": -7 to +7,
  "sl_adjustment": "widen|tighten|none",
  "tp_adjustment": "extend|reduce|none",
  "key_factors": ["factor1", "factor2", "factor3"],
  "market_context": "one-line market summary"
}}

RULES:
- If direction is BUY but your analysis says sell, verdict=NEUTRAL or SELL, score_modifier negative
- If all factors align with the direction, verdict=STRONG_BUY/STRONG_SELL, score_modifier +5 to +7
- Be conservative — only give STRONG verdict when 4+ factors confirm
- score_modifier affects the final confluence score directly
- Consider the SESSION — poor session quality should reduce confidence
- Consider CORRELATION risk — overexposure should reduce confidence
- If economic event is imminent (CAUTION/BLOCK), reduce confidence"""

    @staticmethod
    def _parse_response(content: str, ctx: dict) -> Optional[AIVerdict]:
        """Parse Claude's JSON response into AIVerdict."""
        try:
            # Extract JSON
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()

            data = json.loads(content)

            direction = ctx.get('direction', 'BUY')

            # Validate and clamp values
            verdict = data.get('verdict', 'NEUTRAL')
            if verdict not in ('STRONG_BUY', 'BUY', 'NEUTRAL', 'SELL', 'STRONG_SELL'):
                verdict = 'NEUTRAL'

            confidence = max(0.0, min(100.0, float(data.get('confidence', 50))))
            score_mod = max(-7.0, min(7.0, float(data.get('score_modifier', 0))))

            # If AI verdict contradicts proposed direction, ensure negative modifier
            is_buy = direction == 'BUY'
            if is_buy and verdict in ('SELL', 'STRONG_SELL'):
                score_mod = min(score_mod, -3.0)
            elif not is_buy and verdict in ('BUY', 'STRONG_BUY'):
                score_mod = min(score_mod, -3.0)

            risk = data.get('risk_level', 'MEDIUM')
            if risk not in ('LOW', 'MEDIUM', 'HIGH'):
                risk = 'MEDIUM'

            sl_adj = data.get('sl_adjustment', 'none')
            if sl_adj not in ('widen', 'tighten', 'none'):
                sl_adj = 'none'

            tp_adj = data.get('tp_adjustment', 'none')
            if tp_adj not in ('extend', 'reduce', 'none'):
                tp_adj = 'none'

            factors = data.get('key_factors', [])
            if not isinstance(factors, list):
                factors = []
            factors = [str(f)[:80] for f in factors[:3]]

            return AIVerdict(
                verdict=verdict,
                confidence=confidence,
                reasoning=str(data.get('reasoning', ''))[:500],
                risk_level=risk,
                score_modifier=round(score_mod, 1),
                sl_adjustment=sl_adj,
                tp_adjustment=tp_adj,
                key_factors=factors,
                market_context=str(data.get('market_context', ''))[:150],
            )

        except json.JSONDecodeError as e:
            logger.error(f"AI Brain returned invalid JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"AI Brain parse error: {e}")
            return None
