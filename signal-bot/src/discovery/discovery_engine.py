"""
Discovery Engine — the brain of the Strategy Discovery Bot.

Workflow:
  1. Download OHLCV data for the given pair across all timeframes
  2. For each timeframe:
     a. Compute ALL indicators once (reused by every strategy)
     b. Run every strategy + param combination
     c. Backtest each signal set
  3. Collect results, filter by win-rate threshold
  4. Generate report
"""

from __future__ import annotations
import time
import sys
import os
from typing import List, Optional

import pandas as pd
import numpy as np

try:
    import yfinance as yf
except ImportError:
    yf = None

from discovery.indicators import compute_all_indicators
from discovery.strategies import get_all_strategies, get_strategy_count
from discovery.fast_backtest import run_backtest, BacktestMetrics
from discovery.report import print_results, save_results, format_summary


# ── Yahoo Finance symbol map (same as main bot) ─────────────────────────────
YAHOO_MAP = {
    'EURUSD': 'EURUSD=X',   'GBPUSD': 'GBPUSD=X',   'USDJPY': 'USDJPY=X',
    'USDCHF': 'USDCHF=X',   'AUDUSD': 'AUDUSD=X',   'USDCAD': 'USDCAD=X',
    'NZDUSD': 'NZDUSD=X',   'XAUUSD': 'XAUUSD=X',   'EURJPY': 'EURJPY=X',
    'GBPJPY': 'GBPJPY=X',   'AUDJPY': 'AUDJPY=X',   'EURGBP': 'EURGBP=X',
    'BTCUSDT': 'BTC-USD',   'ETHUSDT': 'ETH-USD',   'SOLUSDT': 'SOL-USD',
    'XRPUSDT': 'XRP-USD',   'BNBUSDT': 'BNB-USD',   'DOGEUSDT': 'DOGE-USD',
    'ADAUSDT': 'ADA-USD',   'LINKUSDT': 'LINK-USD', 'DOTUSDT': 'DOT-USD',
}

# ── Timeframe → yfinance download config ─────────────────────────────────────
TF_CONFIG = {
    'M5':  {'interval': '5m',  'period': '60d',  'resample': None},
    'M15': {'interval': '15m', 'period': '60d',  'resample': None},
    'M30': {'interval': '30m', 'period': '60d',  'resample': None},
    'H1':  {'interval': '1h',  'period': '730d', 'resample': None},
    'H4':  {'interval': '1h',  'period': '730d', 'resample': '4h'},
    'D1':  {'interval': '1d',  'period': '10y',  'resample': None},
}

# ── SL/TP presets to test ────────────────────────────────────────────────────
# Tighter TP → higher win rate; wider TP → higher profit per win
SLTP_PRESETS = [
    # High win-rate presets (tight TP, wider SL)
    {'sl': 2.0, 'tp': 1.0, 'label': 'SL2.0/TP1.0'},   # 1:0.5 R:R
    {'sl': 2.0, 'tp': 1.5, 'label': 'SL2.0/TP1.5'},   # 1:0.75 R:R
    {'sl': 1.5, 'tp': 1.5, 'label': 'SL1.5/TP1.5'},   # 1:1 R:R
    {'sl': 2.0, 'tp': 2.0, 'label': 'SL2.0/TP2.0'},   # 1:1 R:R
    {'sl': 3.0, 'tp': 2.0, 'label': 'SL3.0/TP2.0'},   # 1:0.67 R:R
    # Balanced presets
    {'sl': 1.5, 'tp': 2.5, 'label': 'SL1.5/TP2.5'},   # 1:1.67 R:R
    {'sl': 2.0, 'tp': 3.0, 'label': 'SL2.0/TP3.0'},   # 1:1.5 R:R
    # High reward presets
    {'sl': 1.5, 'tp': 3.0, 'label': 'SL1.5/TP3.0'},   # 1:2 R:R
    {'sl': 1.0, 'tp': 3.0, 'label': 'SL1.0/TP3.0'},   # 1:3 R:R
]



# ── yfinance hard limits per interval ────────────────────────────────────────
TF_MAX_DAYS = {
    'M5':  60,    # 5m  interval: yfinance max 60 days
    'M15': 60,    # 15m interval: yfinance max 60 days
    'M30': 60,    # 30m interval: yfinance max 60 days
    'H1':  730,   # 1h  interval: yfinance max ~2 years
    'H4':  730,   # 1h→4h resample: same limit
    'D1':  36500, # 1d  interval: effectively unlimited
}


class DiscoveryEngine:
    """Run exhaustive strategy discovery on a single pair."""

    def __init__(self, pair: str, timeframes: list[str] | None = None,
                 min_win_rate: float = 60.0, min_trades: int = 5,
                 output_dir: str = '.', lookback_days: int = 0):
        self.pair = pair.upper()
        self.timeframes = timeframes or ['M15', 'M30', 'H1', 'H4', 'D1']
        self.min_win_rate = min_win_rate
        self.min_trades = min_trades
        self.output_dir = output_dir
        self.lookback_days = lookback_days  # 0 = use built-in defaults
        self.results: list[dict] = []

    # ── Public API ───────────────────────────────────────────────────────────

    def run(self) -> list[dict]:
        """Run full discovery. Returns list of result dicts."""
        strategies = get_all_strategies()
        total_strats = len(strategies)
        total_tfs = len(self.timeframes)
        total_sltp = len(SLTP_PRESETS)
        grand_total = total_strats * total_tfs * total_sltp

        lookback_label = f"{self.lookback_days} days" if self.lookback_days > 0 else "default (auto)"
        print(f"\n{'=' * 70}")
        print(f"  Strategy Discovery Bot")
        print(f"  Pair: {self.pair}")
        print(f"  Timeframes: {', '.join(self.timeframes)}")
        print(f"  Data lookback: {lookback_label}")
        print(f"  Strategies: {total_strats} x {total_tfs} TFs x {total_sltp} SL/TP = {grand_total} backtests")
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
            print(f"OK", end=' ', flush=True)

            print(f"| Running {total_strats * total_sltp} backtests...", flush=True)
            tf_start = time.time()

            for strat in strategies:
                # Generate signals once per strategy
                try:
                    signals = strat['func'](df_ind, **strat['params'])
                except (KeyError, TypeError) as e:
                    done += total_sltp
                    continue

                if signals.sum() == 0 and (signals == 0).all():
                    done += total_sltp
                    continue

                # Run backtest with each SL/TP preset
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

                    # Build compact params label for display
                    params_label = ', '.join(f'{k}={v}' for k, v in strat['params'].items()) if strat['params'] else ''

                    self.results.append({
                        'strategy': f"{strat['label']} {preset['label']}",
                        'strategy_name': strat['name'],
                        'params_label': params_label,
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
                    })

            tf_elapsed = time.time() - tf_start
            # Count winners so far for this TF
            tf_winners = sum(
                1 for r in self.results
                if r['timeframe'] == tf and r['win_rate'] >= self.min_win_rate
            )
            print(f"    [{tf}] Done in {tf_elapsed:.1f}s | "
                  f"{sum(1 for r in self.results if r['timeframe'] == tf)} valid results | "
                  f"{tf_winners} winners (>={self.min_win_rate}%)")

        elapsed = time.time() - start

        print(f"\n  Total time: {elapsed:.1f}s | {done} backtests | {len(self.results)} valid results")

        # Print & save
        print_results(self.results, self.min_win_rate)
        save_results(self.results, self.pair, self.output_dir)

        return self.results

    # ── Data loading ─────────────────────────────────────────────────────────

    def _load_data(self, timeframe: str) -> Optional[pd.DataFrame]:
        """Download OHLCV from Yahoo Finance."""
        if yf is None:
            print("ERROR: yfinance not installed")
            return None

        symbol = YAHOO_MAP.get(self.pair, self.pair)
        cfg = TF_CONFIG.get(timeframe)
        if cfg is None:
            return None

        # Build download kwargs — use lookback_days if set, else built-in period
        dl_kwargs: dict = dict(
            interval=cfg['interval'],
            progress=False,
            auto_adjust=True,
        )

        if self.lookback_days > 0:
            import datetime
            max_days = TF_MAX_DAYS.get(timeframe, self.lookback_days)
            effective = min(self.lookback_days, max_days)
            start_dt = datetime.date.today() - datetime.timedelta(days=effective)
            dl_kwargs['start'] = start_dt.strftime('%Y-%m-%d')
        else:
            dl_kwargs['period'] = cfg['period']

        try:
            df = yf.download(symbol, **dl_kwargs)
        except Exception as e:
            print(f"Download error: {e}")
            return None

        if df is None or df.empty:
            return None

        # Flatten multi-level columns from newer yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

        # Normalise column names
        df.columns = [c.lower().strip() for c in df.columns]

        # Ensure required columns exist
        for col in ['open', 'high', 'low', 'close']:
            if col not in df.columns:
                return None

        # Resample if needed (e.g., H1 → H4)
        if cfg['resample']:
            df = self._resample(df, cfg['resample'])

        # Drop NaN rows at start
        df = df.dropna(subset=['open', 'high', 'low', 'close'])

        return df

    @staticmethod
    def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
        """Resample OHLCV to a larger timeframe."""
        agg = {
            'open':  'first',
            'high':  'max',
            'low':   'min',
            'close': 'last',
        }
        if 'volume' in df.columns:
            agg['volume'] = 'sum'
        return df.resample(rule).agg(agg).dropna()
