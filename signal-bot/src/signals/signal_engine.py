"""
Signal Engine — Main orchestrator
Runs the full signal generation pipeline for all active pairs.

Pipeline per pair per cycle:
  1. Fetch OHLCV data (H1, H4, D1)
  2. Calculate indicators on each timeframe
  3. Detect market regime
  4. Check cool-off / daily limits / trading hours
  5. Evaluate both BUY and SELL sides
  6. Score each side via confluence scorer
  7. If score ≥ threshold → generate signal
  8. Calculate ATR-based SL/TP + run stop hunt detector
  9. Calculate lot size
 10. Save signal to DB + send Telegram notification
"""

from __future__ import annotations
import asyncio
import json
from datetime import datetime, timezone, date

from data.price_fetcher import PriceFetcher
from data.economic_calendar import EconomicCalendar
from indicators.indicator_engine import IndicatorEngine
from indicators.market_regime import MarketRegimeDetector
from indicators.liquidity_analyzer import LiquidityAnalyzer
from indicators.candlestick_patterns import CandlestickDetector
from indicators.session_manager import SessionManager
from indicators.correlation_analyzer import CorrelationAnalyzer
from indicators.sentiment_analyzer import SentimentAnalyzer
from signals.confluence_scorer import ConfluenceScorer
from risk.position_sizer import PositionSizer
from risk.stop_hunt_detector import StopHuntDetector
from utils.logger import setup_logger

logger = setup_logger('signal_engine')


class SignalEngine:
    """Orchestrates the full signal generation pipeline."""

    def __init__(self, db, config):
        self.db      = db
        self.config  = config
        self.fetcher  = PriceFetcher()
        self.ind_eng  = IndicatorEngine()
        self.regime_d = MarketRegimeDetector()
        self.liq_analyzer = LiquidityAnalyzer()
        self.candle_d = CandlestickDetector()
        self.econ_cal = EconomicCalendar(db)
        self.session_mgr = SessionManager()
        self.corr_analyzer = CorrelationAnalyzer()
        self.sentiment_analyzer = SentimentAnalyzer(db)
        self.scorer   = ConfluenceScorer()
        self.sizer    = PositionSizer()
        self.hunt_d   = StopHuntDetector()

        self._notifier  = None   # Injected after init
        self._news_feed = None   # Injected after init
        self._ai_analyzer = None
        self._trade_brain = None

    async def initialize(self):
        """Set up optional components (Telegram, news, AI)."""
        try:
            from notifications.telegram_notifier import TelegramNotifier
            self._notifier = TelegramNotifier(self.config)
            logger.info("Telegram notifier initialized")
        except Exception as e:
            logger.warning(f"Telegram not available: {e}")

        try:
            from data.news_fetcher import NewsFetcher
            self._news_feed = NewsFetcher(self.db)
            logger.info("News fetcher initialized")
        except Exception as e:
            logger.warning(f"News fetcher not available: {e}")

        try:
            from ai.news_analyzer import NewsAnalyzer
            self._ai_analyzer = NewsAnalyzer(self.config)
            logger.info("AI news analyzer initialized")
        except Exception as e:
            logger.warning(f"AI analyzer not available: {e}")

        try:
            from ai.trade_brain import TradeBrain
            self._trade_brain = TradeBrain(self.config)
            logger.info("AI Trade Brain initialized")
        except Exception as e:
            logger.warning(f"AI Trade Brain not available: {e}")

    async def run_cycle(self):
        """Run one full cycle for all active pairs."""
        pairs = self.db.get_active_pairs()
        if not pairs:
            logger.warning("No active pairs configured")
            return

        # Check global limits first
        today_count = self.db.get_today_signal_count()
        if today_count >= self.config.max_daily_signals:
            logger.info(f"Daily signal limit reached ({today_count}/{self.config.max_daily_signals})")
            return

        open_count = self.db.get_open_signal_count()
        if open_count >= self.config.max_open_positions:
            logger.info(f"Max open positions reached ({open_count}/{self.config.max_open_positions})")
            return

        # Check cool-off
        if self._in_cooloff():
            return

        # Fetch latest news sentiment (once per cycle, shared across pairs)
        news_data = await self._fetch_news_data()

        # Fetch economic calendar events (cached 30 min)
        await self.econ_cal.fetch_events()
        upcoming = self.econ_cal.get_upcoming(hours=4, high_only=True)
        if upcoming:
            logger.info(f"Upcoming high-impact events: {len(upcoming)} in next 4h")

        # Recalculate live correlations once per cycle
        if self.corr_analyzer._price_cache:
            self.corr_analyzer.calculate_live_correlations()

        logger.info(f"Running cycle for {len(pairs)} pairs | today={today_count} open={open_count}")

        tasks = [self._process_pair(pair, news_data) for pair in pairs]
        # Note: sentiment is fetched per-pair inside _process_pair since it varies by pair type
        results = await asyncio.gather(*tasks, return_exceptions=True)

        signals_generated = sum(1 for r in results if r is True)
        logger.info(f"Cycle complete. Signals generated: {signals_generated}/{len(pairs)}")

    async def _process_pair(self, pair: str, news_data: dict) -> bool:
        """Run full pipeline for one pair. Returns True if signal generated."""
        try:
            # 1. Fetch OHLCV
            df_h1 = await self.fetcher.get_ohlcv(pair, 'H1', bars=300)
            df_h4 = await self.fetcher.get_ohlcv(pair, 'H4', bars=200)
            df_d1 = await self.fetcher.get_ohlcv(pair, 'D1', bars=200)

            if df_h1 is None or len(df_h1) < 50:
                logger.warning(f"{pair}: insufficient H1 data")
                return False

            # 2. Calculate indicators
            ltf = self.ind_eng.calculate(df_h1, 'H1')
            mtf = self.ind_eng.calculate(df_h4, 'H4') if df_h4 is not None else None
            htf = self.ind_eng.calculate(df_d1, 'D1') if df_d1 is not None else None

            # 3. Detect market regime
            regime = self.regime_d.detect(ltf, mtf, htf, timeframe=self.config.primary_timeframe)

            if not regime.tradeable:
                logger.debug(f"{pair}: regime not tradeable — {regime.reason}")
                return False

            # 3b. Liquidity / Smart Money analysis
            liquidity = self.liq_analyzer.analyze(
                df=df_h1, pair=pair, atr=ltf.atr or 0.001,
                htf_df=df_h4,
            )

            # 3c. Candlestick pattern detection
            trend_dir = ltf.trend_direction.lower() if ltf.trend_direction else 'sideways'
            candle_result = self.candle_d.detect(
                df=df_h1, atr=ltf.atr or 0.001, trend=trend_dir, lookback=5,
            )
            if candle_result.patterns:
                logger.debug(f"{pair}: Candlestick patterns detected ({len(candle_result.patterns)})")

            # 3d. Economic calendar gate check
            econ_gate = self.econ_cal.check_gate(pair, minutes_before=30, minutes_after=15)
            if econ_gate['action'] == 'BLOCK':
                logger.info(f"{pair}: ECON GATE BLOCKED — {econ_gate['reason']}")
                return False

            if econ_gate['action'] == 'CAUTION':
                logger.info(f"{pair}: ECON CAUTION — {econ_gate['reason']}")

            # 3e. Session context (kill zones, overlaps, quality)
            session_ctx = self.session_mgr.get_context(pair)
            # Keep legacy session_info for backward compat in signal dict
            session_info = session_ctx.to_dict()

            # Weekend gap protection — block forex signals
            if session_ctx.is_weekend_gap_risk:
                logger.info(f"{pair}: Weekend gap risk — skipping")
                return False

            # 3f. Economic event bias
            econ_bias = self.econ_cal.get_event_bias(pair)

            # 3g. Update correlation price cache
            if df_h1 is not None and 'close' in df_h1.columns:
                self.corr_analyzer.update_prices(pair, df_h1['close'].tolist())

            # 4. Get news sentiment for this pair
            pair_sentiment = news_data.get(pair, {})
            sentiment    = pair_sentiment.get('sentiment', 'neutral')
            ai_confidence = pair_sentiment.get('ai_confidence', 0.0)

            # 4b. Market sentiment (Fear & Greed / VIX / performance)
            sentiment_result = None
            try:
                sentiment_result = await self.sentiment_analyzer.get_sentiment(pair, 'BUY')
                if sentiment_result and sentiment_result.score_modifier != 0:
                    logger.debug(
                        f"{pair}: Sentiment {sentiment_result.overall_sentiment} "
                        f"(mod={sentiment_result.score_modifier:+.1f}, risk={sentiment_result.risk_adjustment})"
                    )

                # Risk adjustment: if sentiment says 'avoid', skip pair
                if sentiment_result and sentiment_result.risk_adjustment == 'avoid':
                    logger.info(f"{pair}: Sentiment risk=AVOID — skipping")
                    return False
            except Exception as e:
                logger.warning(f"{pair}: Sentiment fetch error (proceeding without): {e}")

            # 5. Evaluate BUY and SELL
            best_signal = None
            best_score  = 0.0

            # Get open signals for correlation check
            open_signals = self.db.get_open_signals_summary()

            for direction in ('BUY', 'SELL'):
                # Update sentiment for this direction
                if sentiment_result and direction == 'SELL':
                    try:
                        sentiment_result = await self.sentiment_analyzer.get_sentiment(pair, 'SELL')
                    except Exception:
                        pass
                # Correlation check
                corr_result = self.corr_analyzer.check_signal(
                    pair, direction, open_signals,
                )

                score, breakdown, quality = self.scorer.score(
                    direction=direction,
                    ltf=ltf,
                    mtf=mtf or ltf,
                    htf=htf or ltf,
                    regime=regime,
                    news_sentiment=sentiment,
                    ai_confidence=ai_confidence,
                    trading_mode=self.config.trading_mode,
                    liquidity=liquidity,
                    candles=candle_result,
                    session=session_ctx,
                    correlation=corr_result,
                    sentiment=sentiment_result,
                )

                # Correlation hard block
                if corr_result.action == 'BLOCK':
                    logger.info(f"{pair}: CORR BLOCKED {direction} — {corr_result.reason}")
                    continue

                if score >= self.config.min_confluence_score and score > best_score:
                    best_score  = score
                    best_signal = {
                        'direction': direction,
                        'score':     score,
                        'breakdown': breakdown,
                        'quality':   quality,
                        'correlation': corr_result,
                        'sentiment': sentiment_result,
                    }

            if not best_signal:
                logger.debug(f"{pair}: no qualifying signal (best score below {self.config.min_confluence_score})")
                return False

            # 5b. News gate (technical_news_filter mode only)
            if self.config.trading_mode == 'technical_news_filter':
                gate = self._news_gate_check(pair, best_signal['direction'], news_data)
                if gate == 'BLOCK':
                    logger.info(
                        f"{pair}: NEWS GATE BLOCKED — opposing sentiment for "
                        f"{best_signal['direction']} (score was {best_signal['score']:.1f})"
                    )
                    self.db.log('info', 'news_gate', f"BLOCKED {pair} {best_signal['direction']} — opposing news", {
                        'pair': pair, 'direction': best_signal['direction'],
                        'score': best_signal['score'], 'gate': 'BLOCK',
                    })
                    return False
                elif gate == 'HOLD':
                    logger.info(
                        f"{pair}: NEWS GATE HOLD — high-impact news window, "
                        f"skipping {best_signal['direction']} (score was {best_signal['score']:.1f})"
                    )
                    self.db.log('info', 'news_gate', f"HOLD {pair} {best_signal['direction']} — high-impact news window", {
                        'pair': pair, 'direction': best_signal['direction'],
                        'score': best_signal['score'], 'gate': 'HOLD',
                    })
                    return False
                elif gate == 'BOOST':
                    logger.info(
                        f"{pair}: NEWS GATE BOOST — news confirms {best_signal['direction']} "
                        f"(score {best_signal['score']:.1f})"
                    )
                else:
                    logger.info(f"{pair}: NEWS GATE ALLOW — neutral news, proceeding")

            # 5c. AI Trade Brain analysis (full context)
            ai_verdict = None
            if self._trade_brain and self.config.trading_mode in ('hybrid', 'ai'):
                try:
                    brain_context = {
                        'pair': pair,
                        'direction': best_signal['direction'],
                        'score': best_signal['score'],
                        'score_breakdown': best_signal['breakdown'].to_dict(),
                        'indicators': ltf.to_dict() if ltf else {},
                        'candlestick': candle_result.summary(best_signal['direction']) if candle_result.patterns else 'None',
                        'liquidity': liquidity.summary(best_signal['direction']) if liquidity else 'N/A',
                        'session': session_ctx.to_dict(),
                        'correlation': best_signal.get('correlation', {}).to_dict() if best_signal.get('correlation') else {},
                        'econ_gate': econ_gate['action'],
                        'econ_bias': econ_bias,
                        'regime': regime.regime,
                        'htf_trend': htf.trend_direction if htf else 'UNKNOWN',
                        'mtf_trend': mtf.trend_direction if mtf else 'UNKNOWN',
                        'news_sentiment': sentiment,
                        'news_reasoning': pair_sentiment.get('reasoning', ''),
                        'sentiment': best_signal.get('sentiment', {}).to_dict() if best_signal.get('sentiment') else {},
                    }
                    ai_verdict = await self._trade_brain.analyze_trade(brain_context)

                    # Apply AI score modifier
                    if ai_verdict and ai_verdict.score_modifier != 0:
                        old_score = best_signal['score']
                        best_signal['score'] = max(0, min(100, old_score + ai_verdict.score_modifier))
                        best_signal['breakdown'].session_modifier += 0  # Keep existing
                        logger.info(
                            f"{pair}: AI Brain {ai_verdict.verdict} "
                            f"(conf={ai_verdict.confidence:.0f}, mod={ai_verdict.score_modifier:+.1f}) "
                            f"score {old_score:.1f} → {best_signal['score']:.1f}"
                        )

                        # If AI reduced score below threshold, skip
                        if best_signal['score'] < self.config.min_confluence_score:
                            logger.info(f"{pair}: AI Brain dropped score below threshold — skipping")
                            return False
                except Exception as e:
                    logger.warning(f"{pair}: AI Brain error (proceeding without): {e}")

            # 6. Calculate SL/TP (ATR-based)
            direction = best_signal['direction']
            entry = ltf.close

            if ltf.atr is None:
                logger.warning(f"{pair}: ATR not available — skipping")
                return False

            sl, tp = self.ind_eng.calc_sl_tp(entry, direction, ltf.atr)

            # 7. Stop hunt detector
            hunt_result = self.hunt_d.check(
                pair=pair,
                direction=direction,
                stop_loss=sl,
                take_profit=tp,
                swing_highs=[ltf.nearest_resistance] if ltf.nearest_resistance else [],
                swing_lows =[ltf.nearest_support]    if ltf.nearest_support    else [],
                atr=ltf.atr,
            )
            sl = hunt_result['adjusted_sl']
            tp = hunt_result['adjusted_tp']

            # 8. Calculate pip distances and R:R
            sl_pips = self.ind_eng.calc_pip_distance(entry, sl, pair)
            tp_pips = self.ind_eng.calc_pip_distance(entry, tp, pair)
            rr_ratio = round(tp_pips / sl_pips, 2) if sl_pips > 0 else 0

            # 9. Position sizing
            size_result = self.sizer.calculate(
                pair=pair,
                account_balance=self.config.account_balance,
                risk_pct=self.config.risk_per_trade_pct,
                sl_pips=sl_pips,
            )

            # 10. Build signal record
            signal_id = self._generate_signal_id()
            signal = {
                'signal_id':          signal_id,
                'pair':               pair,
                'direction':          direction,
                'mode':               self.config.trading_mode,
                'strategy':           f"Confluence-{best_signal['quality']}",
                'entry_price':        round(entry, 5),
                'stop_loss':          sl,
                'take_profit':        tp,
                'suggested_lot':      size_result['lot_size'],
                'risk_amount':        size_result['risk_amount'],
                'sl_pips':            sl_pips,
                'tp_pips':            tp_pips,
                'risk_reward_ratio':  rr_ratio,
                'confluence_score':   best_signal['score'],
                'quality_label':      best_signal['quality'],
                'score_breakdown':    best_signal['breakdown'].to_dict(),
                'timeframe':          self.config.primary_timeframe,
                'htf_trend':          htf.trend_direction if htf else 'UNKNOWN',
                'mtf_trend':          mtf.trend_direction if mtf else 'UNKNOWN',
                'ltf_signal':         ltf.trend_direction,
                'market_regime':      regime.regime,
                'news_sentiment':     sentiment,
                'ai_confidence':      ai_confidence,
                'liquidity_summary':  liquidity.summary(direction),
                'candlestick_summary': candle_result.summary(direction) if candle_result.patterns else '',
                'session_info':       session_info,
                'session_quality':    session_ctx.session_quality,
                'kill_zone':          session_ctx.kill_zone_name if session_ctx.in_kill_zone else '',
                'correlation':        best_signal.get('correlation', {}).to_dict() if best_signal.get('correlation') else {},
                'econ_gate':          econ_gate['action'],
                'econ_bias':          econ_bias,
                'ai_verdict':         ai_verdict.to_dict() if ai_verdict else {},
                'sentiment_data':     best_signal.get('sentiment', {}).to_dict() if best_signal.get('sentiment') else {},
                'reasoning':          self._build_reasoning(
                    best_signal, regime, ltf, hunt_result, liquidity,
                    candle_result, econ_gate, econ_bias, session_ctx,
                    ai_verdict, best_signal.get('sentiment'),
                ),
                'indicator_snapshot': ltf.to_dict(),
            }

            # 11. Save to DB
            signal_db_id = self.db.save_signal(signal)
            logger.info(
                f"SIGNAL GENERATED: {signal_id} {pair} {direction} "
                f"@ {entry} SL={sl} TP={tp} Score={best_signal['score']:.1f} ({best_signal['quality']})"
            )
            self.db.log('info', 'signal_engine', f"Signal generated: {signal_id}", signal)

            # 12. Send Telegram notification
            if self._notifier and self.config.telegram_enabled:
                await self._notifier.send_signal(signal)

            return True

        except Exception as e:
            logger.error(f"Error processing {pair}: {e}", exc_info=True)
            return False

    async def _fetch_news_data(self) -> dict:
        """
        Fetch and analyze latest news.
        Returns dict: {pair: {sentiment, ai_confidence}}
        """
        if not self._news_feed:
            return {}

        if self.config.trading_mode == 'technical':
            return {}   # Skip news in pure technical mode (technical_news_filter still needs news)

        try:
            news_items = await self._news_feed.fetch_latest(hours=2)
            if not news_items:
                return {}

            # Analyze with AI if available
            if self._ai_analyzer and self.config.trading_mode in ('ai', 'hybrid'):
                analysis = await self._ai_analyzer.analyze_batch(news_items)
                return analysis

            # Simple rule-based sentiment if no AI
            return self._simple_sentiment(news_items)

        except Exception as e:
            logger.error(f"News fetch error: {e}")
            return {}

    @staticmethod
    def _simple_sentiment(news_items: list) -> dict:
        """Basic keyword-based sentiment (fallback when AI not available)."""
        bullish_kw = ['rally', 'surge', 'jump', 'gain', 'bullish', 'hawkish', 'strong',
                       'rise', 'up', 'higher', 'beat', 'exceed', 'positive', 'optimis']
        bearish_kw = ['drop', 'fall', 'crash', 'plunge', 'bearish', 'dovish', 'weak',
                       'decline', 'down', 'lower', 'miss', 'disappoint', 'negative', 'pessimis']

        pair_scores = {}  # {pair: {bull: 0, bear: 0}}

        for item in news_items:
            text = (item.get('title', '') + ' ' + item.get('summary', '')).lower()
            bull = sum(1 for kw in bullish_kw if kw in text)
            bear = sum(1 for kw in bearish_kw if kw in text)

            currencies = item.get('affected_currencies', [])
            for cur in currencies:
                # Map currency to common pairs
                pairs = []
                if cur == 'USD':
                    pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']
                elif cur == 'EUR':
                    pairs = ['EURUSD']
                elif cur == 'GBP':
                    pairs = ['GBPUSD']
                elif cur == 'JPY':
                    pairs = ['USDJPY']
                elif cur == 'XAU':
                    pairs = ['XAUUSD']
                elif cur == 'AUD':
                    pairs = ['AUDUSD']
                elif cur == 'CAD':
                    pairs = ['USDCAD']

                for p in pairs:
                    if p not in pair_scores:
                        pair_scores[p] = {'bull': 0, 'bear': 0}
                    pair_scores[p]['bull'] += bull
                    pair_scores[p]['bear'] += bear

        result = {}
        for pair, scores in pair_scores.items():
            if scores['bull'] > scores['bear'] + 2:
                sentiment = 'bullish'
            elif scores['bear'] > scores['bull'] + 2:
                sentiment = 'bearish'
            else:
                sentiment = 'neutral'
            result[pair] = {
                'sentiment': sentiment,
                'ai_confidence': 0.0,
            }
        return result

    def _news_gate_check(self, pair: str, direction: str, news_data: dict) -> str:
        """
        News gate for technical_news_filter mode.
        Called AFTER technical scoring passes threshold.

        Returns:
            'BLOCK' — opposing sentiment with confidence → skip signal
            'HOLD'  — high-impact news within avoid window → skip signal
            'ALLOW' — neutral/weak news → execute signal
            'BOOST' — confirming sentiment → execute signal
        """
        is_buy = direction == 'BUY'

        # 1. Check high-impact news window (HOLD)
        if self.config.news_filter_enabled:
            try:
                avoid_mins = self.config.news_avoid_minutes
                row = self.db.execute_one(
                    """SELECT COUNT(*) as cnt FROM news_archive
                       WHERE impact_level = 'high'
                       AND published_at >= DATE_SUB(NOW(), INTERVAL :p0 MINUTE)
                       AND (affected_currencies LIKE :p1 OR affected_currencies LIKE :p2)""",
                    (avoid_mins, f'%{pair[:3]}%', f'%{pair[3:]}%')
                )
                if row and row['cnt'] > 0:
                    return 'HOLD'
            except Exception as e:
                logger.warning(f"News gate high-impact check failed: {e}")

        # 2. Check sentiment from news_data (from AI or rule-based)
        pair_news = news_data.get(pair, {})
        sentiment = pair_news.get('sentiment', 'neutral')
        ai_conf = pair_news.get('ai_confidence', 0.0)

        # Opposing sentiment with reasonable confidence → BLOCK
        if is_buy and sentiment == 'bearish':
            if ai_conf >= 60:
                return 'BLOCK'
            return 'ALLOW'  # Weak opposing — allow anyway
        if not is_buy and sentiment == 'bullish':
            if ai_conf >= 60:
                return 'BLOCK'
            return 'ALLOW'

        # Confirming sentiment → BOOST
        if is_buy and sentiment == 'bullish':
            return 'BOOST'
        if not is_buy and sentiment == 'bearish':
            return 'BOOST'

        # Neutral or no data → ALLOW
        return 'ALLOW'

    def _in_cooloff(self) -> bool:
        """Check if bot is in cool-off period."""
        if not self.config.cooloff_enabled:
            return False
        try:
            row = self.db.execute_one(
                """SELECT resume_at FROM cooloff_log
                   WHERE is_active = TRUE AND resume_at > NOW()
                   ORDER BY created_at DESC LIMIT 1"""
            )
            if row:
                logger.info(f"Bot in cool-off until {row['resume_at']}")
                return True
        except Exception as e:
            logger.error(f"Cool-off check failed: {e}")
        return False

    @staticmethod
    def _generate_signal_id() -> str:
        """Generate unique signal ID: LST20260505-001 format."""
        now = datetime.now(timezone.utc)
        date_str = now.strftime('%Y%m%d')
        # Simple sequential ID — in production use DB sequence or UUID
        return f"LST{date_str}-{now.strftime('%H%M%S')}"

    @staticmethod
    def _build_reasoning(signal_data: dict, regime, ltf, hunt_result: dict,
                         liquidity=None, candles=None, econ_gate=None,
                         econ_bias=None, session_ctx=None,
                         ai_verdict=None, sentiment=None) -> str:
        """Build human-readable reasoning string for the signal."""
        bd = signal_data['breakdown']
        sess_mod = f" | Sess: {bd.session_modifier:+.1f}" if bd.session_modifier else ""
        corr_mod = f" | Corr: {bd.correlation_modifier:+.1f}" if bd.correlation_modifier else ""
        sent_mod = f" | Sent: {bd.sentiment_modifier:+.1f}" if hasattr(bd, 'sentiment_modifier') and bd.sentiment_modifier else ""
        lines = [
            f"Direction: {signal_data['direction']} | Score: {signal_data['score']:.1f}/100 ({signal_data['quality']})",
            f"Regime: {regime.regime} ({regime.reason})",
            f"Technical: {bd.technical_total:.0f}/30 | "
            f"MTF: {bd.mtf_total:.0f}/15 | "
            f"News: {bd.news_total:.0f}/15 | "
            f"Liquidity: {bd.liquidity_total:.0f}/20 | "
            f"Conditions: {bd.conditions_total:.0f}/20{sess_mod}{corr_mod}{sent_mod}",
            f"LTF RSI: {ltf.rsi:.1f}" if ltf.rsi else "LTF RSI: N/A",
            f"LTF ADX: {ltf.adx:.1f}" if ltf.adx else "LTF ADX: N/A",
        ]
        # Candlestick patterns
        if candles and candles.patterns:
            lines.append(f"Candlestick: {candles.summary(signal_data['direction'])}")
        # SMC / Liquidity
        if liquidity:
            smc_summary = liquidity.summary(signal_data['direction'])
            if smc_summary and smc_summary != "No SMC confluence":
                lines.append(f"SMC: {smc_summary}")
        # Economic calendar
        if econ_gate and econ_gate.get('action') == 'CAUTION':
            lines.append(f"Econ: {econ_gate['reason']}")
        if econ_bias and econ_bias.get('bias') != 'neutral':
            lines.append(f"Econ Bias: {econ_bias['bias']} — {econ_bias.get('reason', '')}")
        # Session context
        if session_ctx:
            lines.append(f"Session: {session_ctx.summary}")
        # Correlation
        corr = signal_data.get('correlation')
        if corr and corr.reason and corr.action != 'ALLOW':
            lines.append(f"Correlation: {corr.reason}")
        # AI Trade Brain
        if ai_verdict and ai_verdict.reasoning:
            lines.append(f"AI Brain: {ai_verdict.verdict} ({ai_verdict.confidence:.0f}%) — {ai_verdict.reasoning}")
            if ai_verdict.key_factors:
                lines.append(f"Key Factors: {', '.join(ai_verdict.key_factors)}")
        # Sentiment
        if sentiment and sentiment.summary:
            lines.append(f"Sentiment: {sentiment.overall_sentiment.upper()} — {sentiment.summary}")
        if hunt_result['warnings']:
            lines.append("Stop hunt warnings: " + "; ".join(hunt_result['warnings']))
        return "\n".join(lines)
