"""
Backtesting Engine — Historical Signal Validation

Runs the full confluence scoring pipeline against historical data to
validate signal quality and strategy parameters.

Walk-forward simulation:
  1. Load historical OHLCV bars (D1/H4/H1)
  2. For each H1 bar (sliding window), calculate all indicators
  3. Run confluence scorer on both BUY and SELL
  4. If score ≥ threshold → simulate signal
  5. Track if price hits TP or SL first (or times out)
  6. Calculate win rate, profit factor, drawdown, Sharpe, etc.

Usage:
    bt = Backtester(db)
    result = await bt.run(
        pair='EURUSD', timeframe='H1',
        start_date='2024-01-01', end_date='2025-12-31',
        min_score=80, sl_atr_mult=1.5, tp_atr_mult=2.0,
    )
"""

from __future__ import annotations
import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional

import pandas as pd
import numpy as np

from indicators.indicator_engine import IndicatorEngine
from indicators.market_regime import MarketRegimeDetector
from indicators.liquidity_analyzer import LiquidityAnalyzer
from indicators.candlestick_patterns import CandlestickDetector
from signals.confluence_scorer import ConfluenceScorer
from utils.logger import setup_logger

logger = setup_logger('backtester')


# ═════════════════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class BacktestTrade:
    """A single simulated trade."""
    bar_index: int
    open_time: str
    pair: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    score: float
    quality: str
    result: str = ''         # 'TP' | 'SL' | 'TIMEOUT'
    close_price: float = 0.0
    close_time: str = ''
    pips: float = 0.0
    bars_held: int = 0

    def to_dict(self) -> dict:
        return {
            'time': self.open_time,
            'dir': self.direction,
            'entry': self.entry_price,
            'sl': self.stop_loss,
            'tp': self.take_profit,
            'score': self.score,
            'quality': self.quality,
            'result': self.result,
            'close': self.close_price,
            'close_time': self.close_time,
            'pips': self.pips,
            'bars': self.bars_held,
        }


@dataclass
class BacktestResult:
    """Full backtest run result."""
    backtest_id: str
    pair: str
    timeframe: str
    start_date: str
    end_date: str
    total_bars: int = 0
    total_signals: int = 0
    wins: int = 0
    losses: int = 0
    timeouts: int = 0
    win_rate: float = 0.0
    net_pips: float = 0.0
    gross_profit_pips: float = 0.0
    gross_loss_pips: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pips: float = 0.0
    avg_win_pips: float = 0.0
    avg_loss_pips: float = 0.0
    avg_rr: float = 0.0
    sharpe_ratio: float = 0.0
    expectancy: float = 0.0
    best_trade_pips: float = 0.0
    worst_trade_pips: float = 0.0
    avg_bars_held: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    trades: List[BacktestTrade] = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    score_distribution: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            'backtest_id': self.backtest_id,
            'pair': self.pair,
            'timeframe': self.timeframe,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'total_bars': self.total_bars,
            'total_signals': self.total_signals,
            'wins': self.wins,
            'losses': self.losses,
            'timeouts': self.timeouts,
            'win_rate': round(self.win_rate, 2),
            'net_pips': round(self.net_pips, 1),
            'profit_factor': round(self.profit_factor, 2),
            'max_drawdown_pips': round(self.max_drawdown_pips, 1),
            'avg_win_pips': round(self.avg_win_pips, 1),
            'avg_loss_pips': round(self.avg_loss_pips, 1),
            'avg_rr': round(self.avg_rr, 2),
            'sharpe_ratio': round(self.sharpe_ratio, 3),
            'expectancy': round(self.expectancy, 2),
            'best_trade_pips': round(self.best_trade_pips, 1),
            'worst_trade_pips': round(self.worst_trade_pips, 1),
            'avg_bars_held': round(self.avg_bars_held, 1),
            'max_consecutive_wins': self.max_consecutive_wins,
            'max_consecutive_losses': self.max_consecutive_losses,
            'score_distribution': self.score_distribution,
            'settings': self.settings,
        }


# ═════════════════════════════════════════════════════════════════════════════
#  BACKTESTER
# ═════════════════════════════════════════════════════════════════════════════

class Backtester:
    """Runs walk-forward backtests on historical data."""

    LOOKBACK = 200       # Bars needed before first signal
    COOLDOWN_BARS = 3    # Minimum bars between signals

    # Max bars to hold a trade (scaled per timeframe)
    MAX_HOLD_MAP = {
        'M5': 144,   # 144 * 5min = 12 hours
        'M15': 96,   # 96 * 15min = 24 hours
        'M30': 72,   # 72 * 30min = 36 hours
        'H1': 72,    # 72 * 1h = 3 days
        'H4': 36,    # 36 * 4h = 6 days
        'D1': 15,    # 15 days
    }

    # MTF/HTF mapping per primary timeframe
    TF_HIERARCHY = {
        'M5':  {'mtf': 'H1',  'htf': 'H4'},
        'M15': {'mtf': 'H1',  'htf': 'H4'},
        'M30': {'mtf': 'H4',  'htf': 'D1'},
        'H1':  {'mtf': 'H4',  'htf': 'D1'},
        'H4':  {'mtf': 'D1',  'htf': 'W1'},
        'D1':  {'mtf': 'W1',  'htf': 'W1'},
    }

    def __init__(self, db):
        self.db = db
        self.ind_eng = IndicatorEngine()
        self.regime_d = MarketRegimeDetector()
        self.liq_analyzer = LiquidityAnalyzer()
        self.candle_d = CandlestickDetector()
        self.scorer = ConfluenceScorer()

    async def run(
        self,
        pair: str,
        timeframe: str = 'H1',
        start_date: str = '2024-01-01',
        end_date: str = '2026-05-01',
        min_score: float = 80.0,
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 2.0,
        trading_mode: str = 'technical',
    ) -> BacktestResult:
        """
        Run a backtest.

        Args:
            pair: Trading pair (e.g. 'EURUSD')
            timeframe: Primary timeframe ('H1')
            start_date: Backtest start (YYYY-MM-DD)
            end_date: Backtest end (YYYY-MM-DD)
            min_score: Minimum confluence score to trigger signal
            sl_atr_mult: ATR multiplier for stop loss
            tp_atr_mult: ATR multiplier for take profit
            trading_mode: 'technical' | 'hybrid'
        """
        bt_id = f"BT-{pair}-{uuid.uuid4().hex[:8]}"
        logger.info(f"Starting backtest {bt_id}: {pair} {timeframe} {start_date} to {end_date}")

        # 1. Load historical data
        loop = asyncio.get_event_loop()
        df_primary = await loop.run_in_executor(
            None, self._load_data, pair, timeframe, start_date, end_date,
        )
        if df_primary is None or len(df_primary) < self.LOOKBACK + 50:
            logger.error(f"Insufficient data for {pair} {timeframe}")
            return BacktestResult(backtest_id=bt_id, pair=pair, timeframe=timeframe,
                                  start_date=start_date, end_date=end_date)

        # Load HTF data for multi-timeframe
        tf_map = self.TF_HIERARCHY.get(timeframe, {'mtf': 'H4', 'htf': 'D1'})
        mtf_tf = tf_map['mtf']
        htf_tf = tf_map['htf']
        df_htf = await loop.run_in_executor(None, self._load_data, pair, htf_tf, start_date, end_date)
        df_mtf = await loop.run_in_executor(None, self._load_data, pair, mtf_tf, start_date, end_date)

        # 2. Walk-forward simulation
        trades = self._simulate(
            df_primary, df_mtf, df_htf, pair, min_score,
            sl_atr_mult, tp_atr_mult, trading_mode, timeframe,
        )

        # 3. Calculate metrics
        result = self._calc_metrics(
            trades, bt_id, pair, timeframe, start_date, end_date,
            len(df_primary),
        )
        result.settings = {
            'min_score': min_score,
            'sl_atr_mult': sl_atr_mult,
            'tp_atr_mult': tp_atr_mult,
            'trading_mode': trading_mode,
        }

        # 4. Save to DB
        await loop.run_in_executor(None, self._save_result, result)

        logger.info(
            f"Backtest {bt_id} complete: {result.total_signals} signals, "
            f"WR={result.win_rate:.1f}%, PF={result.profit_factor:.2f}, "
            f"Net={result.net_pips:+.0f} pips"
        )
        return result

    # ── Data Loading ──────────────────────────────────────────────────────

    def _load_data(self, pair: str, timeframe: str,
                   start: str, end: str) -> Optional[pd.DataFrame]:
        """Load historical OHLCV data from DB."""
        try:
            rows = self.db.execute(
                """SELECT open_time, open_price, high_price, low_price,
                          close_price, volume
                   FROM historical_prices
                   WHERE pair = :p0 AND timeframe = :p1
                     AND open_time >= :p2 AND open_time <= :p3
                   ORDER BY open_time ASC""",
                (pair, timeframe, start, end)
            )
            if not rows:
                return None

            df = pd.DataFrame(rows)
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.reset_index(drop=True)
            return df
        except Exception as e:
            logger.error(f"Data load error: {e}")
            return None

    # ── Walk-Forward Simulation ───────────────────────────────────────────

    def _simulate(
        self,
        df: pd.DataFrame,
        df_mtf: Optional[pd.DataFrame],
        df_htf: Optional[pd.DataFrame],
        pair: str,
        min_score: float,
        sl_mult: float,
        tp_mult: float,
        trading_mode: str,
        timeframe: str = 'H1',
    ) -> List[BacktestTrade]:
        """Run walk-forward simulation over the primary timeframe."""
        trades = []
        in_trade = False
        cooldown = 0
        current_trade: Optional[BacktestTrade] = None
        max_hold = self.MAX_HOLD_MAP.get(timeframe, 72)

        # Score tracking for diagnostics
        score_samples = []
        regime_blocked = 0
        bars_evaluated = 0

        total_bars = len(df)
        log_interval = max(1, total_bars // 10)

        for i in range(self.LOOKBACK, total_bars):
            if i % log_interval == 0:
                pct = (i / total_bars) * 100
                logger.debug(f"Backtest progress: {pct:.0f}% ({i}/{total_bars})")

            # If in a trade, check TP/SL
            if in_trade and current_trade:
                bar = df.iloc[i]
                current_trade.bars_held += 1

                hit = self._check_trade_outcome(current_trade, bar)

                if hit or current_trade.bars_held >= max_hold:
                    if not hit:
                        # Timeout — close at current price
                        current_trade.result = 'TIMEOUT'
                        current_trade.close_price = float(bar['close'])
                        current_trade.pips = self._calc_pips(
                            current_trade.entry_price,
                            current_trade.close_price,
                            current_trade.direction, pair,
                        )

                    current_trade.close_time = str(bar['timestamp'])
                    trades.append(current_trade)
                    in_trade = False
                    current_trade = None
                    cooldown = self.COOLDOWN_BARS
                continue

            # Cooldown between trades
            if cooldown > 0:
                cooldown -= 1
                continue

            # Calculate indicators on sliding window
            window = df.iloc[max(0, i - self.LOOKBACK):i + 1].copy()
            if len(window) < 50:
                continue

            try:
                ltf = self.ind_eng.calculate(window, timeframe)
            except Exception:
                continue

            if ltf.atr is None or ltf.atr == 0:
                continue

            # Market regime
            bars_evaluated += 1
            try:
                regime = self.regime_d.detect(ltf, None, None, timeframe=timeframe)
                if not regime.tradeable:
                    regime_blocked += 1
                    continue
            except Exception:
                continue

            # Candlestick patterns
            try:
                trend_dir = ltf.trend_direction.lower() if ltf.trend_direction else 'sideways'
                candle_result = self.candle_d.detect(window, atr=ltf.atr, trend=trend_dir, lookback=5)
            except Exception:
                candle_result = None

            # Liquidity analysis
            try:
                liquidity = self.liq_analyzer.analyze(df=window, pair=pair, atr=ltf.atr)
            except Exception:
                liquidity = None

            # HTF/MTF indicators from higher timeframe data if available
            mtf_ind = None
            htf_ind = None
            tf_map = self.TF_HIERARCHY.get(timeframe, {'mtf': 'H4', 'htf': 'D1'})
            if df_mtf is not None and len(df_mtf) > 50:
                # Find MTF bars up to current primary bar time
                ts = df.iloc[i]['timestamp']
                mtf_slice = df_mtf[df_mtf['timestamp'] <= ts].tail(100)
                if len(mtf_slice) >= 50:
                    try:
                        mtf_ind = self.ind_eng.calculate(mtf_slice.copy(), tf_map['mtf'])
                    except Exception:
                        pass
            if df_htf is not None and len(df_htf) > 50:
                ts = df.iloc[i]['timestamp']
                htf_slice = df_htf[df_htf['timestamp'] <= ts].tail(100)
                if len(htf_slice) >= 50:
                    try:
                        htf_ind = self.ind_eng.calculate(htf_slice.copy(), tf_map['htf'])
                    except Exception:
                        pass

            # Score both directions
            for direction in ('BUY', 'SELL'):
                try:
                    score, breakdown, quality = self.scorer.score(
                        direction=direction,
                        ltf=ltf,
                        mtf=mtf_ind or ltf,
                        htf=htf_ind or ltf,
                        regime=regime,
                        news_sentiment='neutral',
                        ai_confidence=0.0,
                        trading_mode=trading_mode,
                        liquidity=liquidity,
                        candles=candle_result,
                        session=None,
                        correlation=None,
                        sentiment=None,
                    )
                except Exception:
                    continue

                score_samples.append(score)

                if score >= min_score:
                    entry = float(df.iloc[i]['close'])
                    atr = ltf.atr

                    if direction == 'BUY':
                        sl = entry - (atr * sl_mult)
                        tp = entry + (atr * tp_mult)
                    else:
                        sl = entry + (atr * sl_mult)
                        tp = entry - (atr * tp_mult)

                    current_trade = BacktestTrade(
                        bar_index=i,
                        open_time=str(df.iloc[i]['timestamp']),
                        pair=pair,
                        direction=direction,
                        entry_price=entry,
                        stop_loss=round(sl, 5),
                        take_profit=round(tp, 5),
                        score=score,
                        quality=quality,
                    )
                    in_trade = True
                    break  # Take the first qualifying direction

        # Close any remaining trade
        if in_trade and current_trade:
            last_bar = df.iloc[-1]
            current_trade.result = 'TIMEOUT'
            current_trade.close_price = float(last_bar['close'])
            current_trade.close_time = str(last_bar['timestamp'])
            current_trade.pips = self._calc_pips(
                current_trade.entry_price, current_trade.close_price,
                current_trade.direction, pair,
            )
            trades.append(current_trade)

        # Diagnostic summary
        if score_samples:
            avg_score = sum(score_samples) / len(score_samples)
            max_score = max(score_samples)
            above_70 = sum(1 for s in score_samples if s >= 70)
            above_75 = sum(1 for s in score_samples if s >= 75)
            above_80 = sum(1 for s in score_samples if s >= 80)
            logger.info(
                f"Backtest diagnostics: {total_bars} bars, {bars_evaluated} evaluated, "
                f"{regime_blocked} regime-blocked ({regime_blocked*100//max(bars_evaluated,1)}%), "
                f"{len(score_samples)} scored | avg={avg_score:.1f} max={max_score:.1f} | "
                f">=70: {above_70}, >=75: {above_75}, >=80: {above_80} | "
                f"min_score={min_score} → {len(trades)} trades"
            )
        else:
            logger.info(
                f"Backtest diagnostics: {total_bars} bars, {bars_evaluated} evaluated, "
                f"{regime_blocked} regime-blocked — NO scores generated"
            )

        return trades

    @staticmethod
    def _check_trade_outcome(trade: BacktestTrade, bar) -> bool:
        """Check if TP or SL was hit on this bar. Returns True if trade closed."""
        high = float(bar['high'])
        low = float(bar['low'])

        if trade.direction == 'BUY':
            # Check SL first (more conservative)
            if low <= trade.stop_loss:
                trade.result = 'SL'
                trade.close_price = trade.stop_loss
                trade.pips = -(trade.entry_price - trade.stop_loss)
                return True
            if high >= trade.take_profit:
                trade.result = 'TP'
                trade.close_price = trade.take_profit
                trade.pips = trade.take_profit - trade.entry_price
                return True
        else:  # SELL
            if high >= trade.stop_loss:
                trade.result = 'SL'
                trade.close_price = trade.stop_loss
                trade.pips = -(trade.stop_loss - trade.entry_price)
                return True
            if low <= trade.take_profit:
                trade.result = 'TP'
                trade.close_price = trade.take_profit
                trade.pips = trade.entry_price - trade.take_profit
                return True

        return False

    @staticmethod
    def _calc_pips(entry: float, close: float, direction: str, pair: str) -> float:
        """Calculate pip distance accounting for pair type."""
        diff = close - entry if direction == 'BUY' else entry - close

        # Crypto pairs
        if pair.endswith('USDT'):
            if entry >= 1000:
                return diff          # BTC/BNB: $1 = 1 pip
            elif entry >= 1:
                return diff * 100    # ETH/SOL: $0.01 = 1 pip
            else:
                return diff * 10000  # DOGE/PEPE: $0.0001 = 1 pip

        # JPY pairs
        if 'JPY' in pair:
            return diff * 100

        # Standard forex
        return diff * 10000

    # ── Metrics Calculation ───────────────────────────────────────────────

    @staticmethod
    def _calc_metrics(
        trades: List[BacktestTrade],
        bt_id: str, pair: str, tf: str,
        start: str, end: str, total_bars: int,
    ) -> BacktestResult:
        """Calculate performance metrics from trade list."""
        result = BacktestResult(
            backtest_id=bt_id, pair=pair, timeframe=tf,
            start_date=start, end_date=end,
            total_bars=total_bars,
            total_signals=len(trades),
            trades=trades,
        )

        if not trades:
            return result

        wins = [t for t in trades if t.result == 'TP']
        losses = [t for t in trades if t.result == 'SL']
        timeouts = [t for t in trades if t.result == 'TIMEOUT']

        result.wins = len(wins)
        result.losses = len(losses)
        result.timeouts = len(timeouts)
        result.win_rate = (len(wins) / len(trades) * 100) if trades else 0

        # Pips
        all_pips = [t.pips for t in trades]
        win_pips = [t.pips for t in wins]
        loss_pips = [abs(t.pips) for t in losses]

        result.net_pips = sum(all_pips)
        result.gross_profit_pips = sum(win_pips) if win_pips else 0
        result.gross_loss_pips = sum(loss_pips) if loss_pips else 0
        result.profit_factor = (
            result.gross_profit_pips / result.gross_loss_pips
            if result.gross_loss_pips > 0 else 999.0
        )

        result.avg_win_pips = np.mean(win_pips) if win_pips else 0
        result.avg_loss_pips = np.mean(loss_pips) if loss_pips else 0
        result.avg_rr = (
            result.avg_win_pips / result.avg_loss_pips
            if result.avg_loss_pips > 0 else 0
        )

        result.best_trade_pips = max(all_pips) if all_pips else 0
        result.worst_trade_pips = min(all_pips) if all_pips else 0

        # Bars held
        bars_held = [t.bars_held for t in trades]
        result.avg_bars_held = np.mean(bars_held) if bars_held else 0

        # Max drawdown
        equity_curve = np.cumsum(all_pips)
        if len(equity_curve) > 0:
            peak = np.maximum.accumulate(equity_curve)
            drawdowns = equity_curve - peak
            result.max_drawdown_pips = abs(np.min(drawdowns)) if len(drawdowns) > 0 else 0

        # Sharpe ratio (annualized, assuming ~250 trading days)
        if len(all_pips) > 1:
            returns = np.array(all_pips)
            mean_r = np.mean(returns)
            std_r = np.std(returns)
            if std_r > 0:
                # Rough annualization: signals per year / total signals * 250
                result.sharpe_ratio = (mean_r / std_r) * np.sqrt(min(250, len(trades)))

        # Expectancy (average expected pips per trade)
        if trades:
            wr = result.win_rate / 100
            result.expectancy = (wr * result.avg_win_pips) - ((1 - wr) * result.avg_loss_pips)

        # Consecutive wins/losses
        result.max_consecutive_wins = Backtester._max_consecutive(trades, 'TP')
        result.max_consecutive_losses = Backtester._max_consecutive(trades, 'SL')

        # Score distribution
        score_bins = {'80-84': 0, '85-89': 0, '90-94': 0, '95-100': 0}
        for t in trades:
            if t.score >= 95:
                score_bins['95-100'] += 1
            elif t.score >= 90:
                score_bins['90-94'] += 1
            elif t.score >= 85:
                score_bins['85-89'] += 1
            else:
                score_bins['80-84'] += 1
        result.score_distribution = score_bins

        return result

    @staticmethod
    def _max_consecutive(trades: List[BacktestTrade], result_type: str) -> int:
        """Count maximum consecutive wins or losses."""
        max_streak = 0
        current = 0
        for t in trades:
            if t.result == result_type:
                current += 1
                max_streak = max(max_streak, current)
            else:
                current = 0
        return max_streak

    # ── DB Save ───────────────────────────────────────────────────────────

    def _save_result(self, result: BacktestResult):
        """Save backtest result to database."""
        try:
            trades_json = json.dumps([t.to_dict() for t in result.trades[:500]])
            settings_json = json.dumps(result.settings)

            self.db.execute_write(
                """INSERT INTO backtest_results
                   (backtest_id, strategy_name, pair, timeframe,
                    start_date, end_date, total_signals, wins, losses,
                    win_rate, net_pips, net_pnl, profit_factor,
                    max_drawdown, avg_rr, sharpe_ratio,
                    settings_json, trades_json)
                   VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8,:p9,:p10,:p11,:p12,:p13,:p14,:p15,:p16,:p17)""",
                (
                    result.backtest_id,
                    f"Confluence-{result.settings.get('min_score', 80)}",
                    result.pair,
                    result.timeframe,
                    result.start_date,
                    result.end_date,
                    result.total_signals,
                    result.wins,
                    result.losses,
                    result.win_rate,
                    result.net_pips,
                    0.0,   # net_pnl placeholder
                    result.profit_factor,
                    result.max_drawdown_pips,
                    result.avg_rr,
                    result.sharpe_ratio,
                    settings_json,
                    trades_json,
                )
            )
            logger.info(f"Backtest {result.backtest_id} saved to DB")
        except Exception as e:
            logger.error(f"Failed to save backtest: {e}")
