"""
Fast Backtesting Engine for Strategy Discovery.

Simulates trades from a signal series with ATR-based SL/TP.
Optimised for speed: runs one loop over bars (unavoidable for SL/TP checks)
but avoids per-bar indicator recalculation.

Returns a BacktestMetrics dataclass with all standard performance stats.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List
import math

import numpy as np
import pandas as pd


# ── Max hold bars per timeframe ──────────────────────────────────────────────
MAX_HOLD = {
    'M5': 144, 'M15': 96, 'M30': 72,
    'H1': 72,  'H4': 36,  'D1': 15, 'W1': 10,
}

# ── Pip size helper ──────────────────────────────────────────────────────────
def _pip_size(pair: str) -> float:
    p = pair.upper()
    if p.endswith('USDT'):
        return 0.01      # crypto simplified
    if 'JPY' in p:
        return 0.01
    if 'XAU' in p:
        return 0.1
    return 0.0001


@dataclass
class Trade:
    direction: int          # 1 = LONG, -1 = SHORT
    entry_price: float
    entry_idx: int
    sl: float
    tp: float
    exit_price: float = 0.0
    exit_idx: int = 0
    pips: float = 0.0
    bars_held: int = 0
    exit_reason: str = ''   # sl | tp | signal | max_hold


@dataclass
class BacktestMetrics:
    strategy: str = ''
    timeframe: str = ''
    pair: str = ''
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_pips: float = 0.0
    avg_pips: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pips: float = 0.0
    sharpe: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    avg_hold_bars: float = 0.0
    trades: List[Trade] = field(default_factory=list)


def run_backtest(
    df: pd.DataFrame,
    signals: pd.Series,
    pair: str,
    timeframe: str = 'H1',
    sl_atr_mult: float = 1.5,
    tp_atr_mult: float = 2.5,
    atr_col: str = 'atr_14',
) -> BacktestMetrics:
    """
    Run a single backtest.

    Parameters
    ----------
    df        : OHLCV DataFrame with indicator columns (must include atr_col)
    signals   : Series aligned to df index — 1=BUY, -1=SELL, 0=none
    pair      : e.g. 'EURUSD'
    timeframe : for max-hold lookup
    sl_atr_mult, tp_atr_mult : ATR multipliers
    atr_col   : which ATR column to use for SL/TP

    Returns
    -------
    BacktestMetrics with all stats filled in.
    """
    pip = _pip_size(pair)
    max_bars = MAX_HOLD.get(timeframe, 72)

    # Convert to numpy for speed
    opens  = df['open'].values.astype(float)
    highs  = df['high'].values.astype(float)
    lows   = df['low'].values.astype(float)
    closes = df['close'].values.astype(float)
    atrs   = df[atr_col].values.astype(float) if atr_col in df.columns else np.full(len(df), np.nan)
    sigs   = signals.values.astype(int)
    n      = len(df)

    trades: list[Trade] = []
    position = 0        # 0=flat, 1=long, -1=short
    current: Trade | None = None

    def _close_trade(trade: Trade, price: float, idx: int, reason: str):
        trade.exit_price = price
        trade.exit_idx = idx
        trade.bars_held = idx - trade.entry_idx
        trade.exit_reason = reason
        if trade.direction == 1:
            raw_pips = (price - trade.entry_price) / pip
        else:
            raw_pips = (trade.entry_price - price) / pip
        # Cap at ±5000 pips — catches bad yfinance data / price scale issues
        trade.pips = max(-5000.0, min(5000.0, raw_pips))
        trades.append(trade)

    for i in range(1, n):
        # ── Check SL/TP on current position ──────────────────────────────
        if current is not None:
            if current.direction == 1:  # LONG
                if lows[i] <= current.sl:
                    _close_trade(current, current.sl, i, 'sl')
                    current = None
                    position = 0
                elif highs[i] >= current.tp:
                    _close_trade(current, current.tp, i, 'tp')
                    current = None
                    position = 0
            else:  # SHORT
                if highs[i] >= current.sl:
                    _close_trade(current, current.sl, i, 'sl')
                    current = None
                    position = 0
                elif lows[i] <= current.tp:
                    _close_trade(current, current.tp, i, 'tp')
                    current = None
                    position = 0

        # ── Check max hold ───────────────────────────────────────────────
        if current is not None and (i - current.entry_idx) >= max_bars:
            _close_trade(current, closes[i], i, 'max_hold')
            current = None
            position = 0

        # ── Check signal (from previous bar) ─────────────────────────────
        sig = sigs[i - 1]  # signal generated on bar i-1, enter on bar i
        if sig == 0:
            continue

        # Close opposite position
        if current is not None and current.direction != sig:
            _close_trade(current, opens[i], i, 'signal')
            current = None
            position = 0

        # Enter new position
        if position == 0:
            entry = opens[i]
            atr = atrs[i - 1]
            if np.isnan(atr) or atr <= 0:
                continue
            # Sanity: ATR must be < 20% of entry price (catches bad yfinance data)
            if entry > 0 and atr / entry > 0.20:
                continue
            if sig == 1:
                sl = entry - sl_atr_mult * atr
                tp = entry + tp_atr_mult * atr
            else:
                sl = entry + sl_atr_mult * atr
                tp = entry - tp_atr_mult * atr
            current = Trade(
                direction=sig, entry_price=entry, entry_idx=i, sl=sl, tp=tp,
            )
            position = sig

    # Close any open trade at end
    if current is not None:
        _close_trade(current, closes[-1], n - 1, 'end')

    # ── Compute metrics ──────────────────────────────────────────────────────
    return _compute_metrics(trades, pip)


def _compute_metrics(trades: list[Trade], pip: float) -> BacktestMetrics:
    m = BacktestMetrics()
    m.total_trades = len(trades)
    if not trades:
        return m

    pips_list = [t.pips for t in trades]
    m.wins   = sum(1 for p in pips_list if p > 0)
    m.losses = sum(1 for p in pips_list if p <= 0)
    m.win_rate    = round(m.wins / m.total_trades * 100, 1) if m.total_trades else 0
    m.total_pips  = round(sum(pips_list), 1)
    m.avg_pips    = round(m.total_pips / m.total_trades, 1)
    m.best_trade  = round(max(pips_list), 1)
    m.worst_trade = round(min(pips_list), 1)
    m.avg_hold_bars = round(sum(t.bars_held for t in trades) / m.total_trades, 1)
    m.trades = trades

    # Profit factor
    gross_profit = sum(p for p in pips_list if p > 0)
    gross_loss   = abs(sum(p for p in pips_list if p <= 0))
    m.profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 999.0

    # Max drawdown (pip-based)
    equity = 0.0
    peak   = 0.0
    max_dd = 0.0
    for p in pips_list:
        equity += p
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
    m.max_drawdown_pips = round(max_dd, 1)

    # Sharpe ratio (annualised, simplified)
    if len(pips_list) >= 2:
        arr = np.array(pips_list)
        avg = arr.mean()
        std = arr.std(ddof=1)
        if std > 0:
            m.sharpe = round(avg / std * math.sqrt(min(len(pips_list), 252)), 2)

    return m
