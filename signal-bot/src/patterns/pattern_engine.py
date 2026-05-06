"""
Pattern Analysis Engine — discovers profitable chart pattern + indicator combinations.

Workflow:
  1. Download OHLCV data (reuse from discovery engine)
  2. Compute indicators
  3. For each pattern × indicator filter × SL/TP preset:
     a. Detect pattern signals
     b. Apply indicator filter
     c. Backtest
  4. Collect and report results
"""

from __future__ import annotations
import time
from typing import Optional

import pandas as pd
import numpy as np

try:
    import yfinance as yf
except ImportError:
    yf = None

from discovery.indicators import compute_all_indicators
from discovery.fast_backtest import run_backtest
from patterns.pattern_strategies import get_all_pattern_strategies, get_pattern_count
from data.market_data_cache import load_or_download

# ── Reuse from discovery engine ──────────────────────────────────────────────
YAHOO_MAP = {
    'EURUSD': 'EURUSD=X',   'GBPUSD': 'GBPUSD=X',   'USDJPY': 'USDJPY=X',
    'USDCHF': 'USDCHF=X',   'AUDUSD': 'AUDUSD=X',   'USDCAD': 'USDCAD=X',
    'NZDUSD': 'NZDUSD=X',   'XAUUSD': 'XAUUSD=X',   'EURJPY': 'EURJPY=X',
    'GBPJPY': 'GBPJPY=X',   'AUDJPY': 'AUDJPY=X',   'EURGBP': 'EURGBP=X',
    'BTCUSDT': 'BTC-USD',   'ETHUSDT': 'ETH-USD',   'SOLUSDT': 'SOL-USD',
    'XRPUSDT': 'XRP-USD',   'BNBUSDT': 'BNB-USD',   'DOGEUSDT': 'DOGE-USD',
    'ADAUSDT': 'ADA-USD',   'LINKUSDT': 'LINK-USD', 'DOTUSDT': 'DOT-USD',
}

TF_CONFIG = {
    'M5':  {'interval': '5m',  'period': '60d',  'resample': None},
    'M15': {'interval': '15m', 'period': '60d',  'resample': None},
    'M30': {'interval': '30m', 'period': '60d',  'resample': None},
    'H1':  {'interval': '1h',  'period': '730d', 'resample': None},
    'H4':  {'interval': '1h',  'period': '730d', 'resample': '4h'},
    'D1':  {'interval': '1d',  'period': '10y',  'resample': None},
}

TF_MAX_DAYS = {
    'M5': 60, 'M15': 60, 'M30': 60, 'H1': 730, 'H4': 730, 'D1': 36500,
}

SLTP_PRESETS = [
    {'sl': 2.0, 'tp': 1.0, 'label': 'SL2.0/TP1.0'},
    {'sl': 2.0, 'tp': 1.5, 'label': 'SL2.0/TP1.5'},
    {'sl': 1.5, 'tp': 1.5, 'label': 'SL1.5/TP1.5'},
    {'sl': 2.0, 'tp': 2.0, 'label': 'SL2.0/TP2.0'},
    {'sl': 3.0, 'tp': 2.0, 'label': 'SL3.0/TP2.0'},
    {'sl': 1.5, 'tp': 2.5, 'label': 'SL1.5/TP2.5'},
    {'sl': 2.0, 'tp': 3.0, 'label': 'SL2.0/TP3.0'},
    {'sl': 1.5, 'tp': 3.0, 'label': 'SL1.5/TP3.0'},
    {'sl': 1.0, 'tp': 3.0, 'label': 'SL1.0/TP3.0'},
]


class PatternEngine:
    """Run exhaustive pattern analysis on a single pair."""

    def __init__(self, pair: str, timeframes: list[str] | None = None,
                 min_win_rate: float = 60.0, min_trades: int = 5,
                 output_dir: str = '.', lookback_days: int = 0):
        self.pair = pair.upper()
        self.timeframes = timeframes or ['H1', 'H4', 'D1']
        self.min_win_rate = min_win_rate
        self.min_trades = min_trades
        self.output_dir = output_dir
        self.lookback_days = lookback_days
        self.results: list[dict] = []

    def run(self) -> list[dict]:
        strategies = get_all_pattern_strategies()
        total_strats = len(strategies)
        total_tfs = len(self.timeframes)
        total_sltp = len(SLTP_PRESETS)
        grand_total = total_strats * total_tfs * total_sltp
        pattern_count = get_pattern_count()

        print(f"\n{'=' * 70}")
        print(f"  Pattern Analysis Engine")
        print(f"  Pair: {self.pair}")
        print(f"  Timeframes: {', '.join(self.timeframes)}")
        print(f"  Patterns: {pattern_count} x 6 filters x {total_sltp} SL/TP x {total_tfs} TFs = {grand_total} backtests")
        print(f"  Min win rate: {self.min_win_rate}% | Min trades: {self.min_trades}")
        print(f"{'=' * 70}\n")

        start = time.time()
        done = 0

        for tf in self.timeframes:
            print(f"  [{tf}] Downloading data...", end=' ', flush=True)
            df = self._load_data(tf)
            if df is None or len(df) < 100:
                print(f"SKIP (only {len(df) if df is not None else 0} bars)")
                done += total_strats * total_sltp
                continue
            print(f"{len(df)} bars", end=' ', flush=True)

            print(f"| Computing indicators...", end=' ', flush=True)
            try:
                df_ind = compute_all_indicators(df)
            except Exception as e:
                print(f"ERROR: {e}")
                done += total_strats * total_sltp
                continue
            print(f"OK", flush=True)

            print(f"    Running {total_strats * total_sltp} backtests...", flush=True)
            tf_start = time.time()

            for strat in strategies:
                # Generate pattern signals
                try:
                    raw_signals = strat['pattern_func'](df_ind)
                except Exception:
                    done += total_sltp
                    continue

                if raw_signals.sum() == 0 and (raw_signals == 0).all():
                    done += total_sltp
                    continue

                # Apply indicator filter
                if strat['filter_func'] is not None:
                    try:
                        signals = strat['filter_func'](df_ind, raw_signals)
                    except Exception:
                        done += total_sltp
                        continue
                else:
                    signals = raw_signals

                if signals.sum() == 0 and (signals == 0).all():
                    done += total_sltp
                    continue

                # Backtest with each SL/TP
                for preset in SLTP_PRESETS:
                    try:
                        metrics = run_backtest(
                            df_ind, signals,
                            pair=self.pair, timeframe=tf,
                            sl_atr_mult=preset['sl'],
                            tp_atr_mult=preset['tp'],
                        )
                    except Exception:
                        done += 1
                        continue

                    done += 1

                    if metrics.total_trades < self.min_trades:
                        continue

                    self.results.append({
                        'strategy': f"{strat['label']} {preset['label']}",
                        'strategy_name': strat['pattern_name'],
                        'filter_name': strat['filter_name'],
                        'params_label': strat['filter_name'] if strat['filter_name'] != 'Alone' else '',
                        'category': strat['category'],
                        'timeframe': tf,
                        'pair': self.pair,
                        'sl_tp': preset['label'],
                        'total_trades': metrics.total_trades,
                        'wins': metrics.wins,
                        'losses': metrics.losses,
                        'win_rate': metrics.win_rate,
                        'total_pips': metrics.total_pips,
                        'avg_pips': metrics.avg_pips,
                        'profit_factor': metrics.profit_factor,
                        'sharpe': metrics.sharpe,
                        'max_dd': metrics.max_drawdown_pips,
                        'best_trade': metrics.best_trade,
                        'worst_trade': metrics.worst_trade,
                        'avg_hold_bars': metrics.avg_hold_bars,
                        'description': strat.get('description', ''),
                    })

            tf_elapsed = time.time() - tf_start
            tf_winners = sum(
                1 for r in self.results
                if r['timeframe'] == tf and r['win_rate'] >= self.min_win_rate
            )
            print(f"    [{tf}] Done in {tf_elapsed:.1f}s | "
                  f"{sum(1 for r in self.results if r['timeframe'] == tf)} valid | "
                  f"{tf_winners} winners (>={self.min_win_rate}%)")

        elapsed = time.time() - start
        print(f"\n  Total: {elapsed:.1f}s | {done} backtests | {len(self.results)} valid results")

        return self.results

    # ── Data loading (uses local cache with CCXT/yfinance fallback) ─────────

    def _load_data(self, timeframe: str) -> Optional[pd.DataFrame]:
        """Load data from cache (CCXT for crypto, yfinance for forex)."""
        effective_days = self.lookback_days if self.lookback_days > 0 else 0
        df = load_or_download(self.pair, timeframe, lookback_days=effective_days)
        return df
