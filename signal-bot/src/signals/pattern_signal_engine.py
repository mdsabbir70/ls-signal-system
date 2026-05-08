"""
Pattern Signal Engine — runs the 5 Trading Modes simultaneously.

For each mode × pair × timeframe:
  1. Fetch OHLCV data
  2. Compute indicators (RSI, EMA, ADX, ATR)
  3. Detect chart pattern (Double_Bottom, Rising_Wedge, etc.)
  4. Apply indicator filter (RSI / ADX / EMA_Trend / Alone)
  5. Check if last bar has a new pattern signal
  6. Cooldown check (skip if same bar already sent)
  7. Economic calendar gate (block 30 min before / skip 30 min after)
  8. Calculate SL/TP from ATR × preset multiplier
  9. Send Telegram with mode label + save to DB
"""

from __future__ import annotations
import re

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np
import pandas as pd

from utils.logger import setup_logger
from utils.pair_config import pip_size as _cfg_pip_size, price_decimals as _cfg_decimals
from data.economic_calendar import EconomicCalendar
from signals.trading_modes import TRADING_MODES, TF_BARS, TF_COOLDOWN_MINS

logger = setup_logger('pattern_engine')

# ── Cooldown tracker: {f"{mode_id}:{pair}:{tf}" → last signal bar timestamp} ─
_last_signal_bar: dict[str, datetime] = {}


class PatternSignalEngine:
    """Runs all 5 trading modes — detects chart patterns and sends signals."""

    def __init__(self, db, config):
        self.db       = db
        self.config   = config
        self.econ_cal = EconomicCalendar(db)
        self._notifier = None

    async def initialize(self):
        """Set up Telegram notifier."""
        try:
            from notifications.telegram_notifier import TelegramNotifier
            self._notifier = TelegramNotifier(self.config)
            logger.info("Pattern Signal Engine: Telegram notifier ready")
        except Exception as e:
            logger.warning(f"Pattern Engine: Telegram not available: {e}")

    async def run_cycle(self):
        """Run one detection cycle for all modes × pairs."""
        if not self.config.bot_active:
            return

        pairs = self.db.get_active_pairs()
        if not pairs:
            logger.warning("Pattern Engine: no active pairs")
            return

        # Fetch econ calendar once per cycle
        try:
            await self.econ_cal.fetch_events()
        except Exception as e:
            logger.warning(f"Pattern Engine: econ calendar fetch failed: {e}")

        logger.info(f"Pattern Engine: running {len(TRADING_MODES)} modes × {len(pairs)} pairs")

        for mode in TRADING_MODES:
            # Check per-mode active setting (DB key: mode_1_active, etc.)
            mode_key = f"mode_{mode['id']}_active"
            mode_enabled = str(self.config.get(mode_key, 'true')).lower() != 'false'
            if not mode_enabled:
                logger.debug(f"  {mode['name']}: disabled (mode_{mode['id']}_active=false)")
                continue

            tasks = [
                self._process_mode_pair(mode, pair, tf)
                for pair in pairs
                for tf in mode['timeframes']
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            sent  = sum(1 for r in results if r is True)
            errs  = sum(1 for r in results if isinstance(r, Exception))
            total = len(results)
            logger.info(
                f"  {mode['name']}: {sent}/{total} signals sent"
                + (f" ({errs} errors)" if errs else "")
            )
            if errs:
                for r in results:
                    if isinstance(r, Exception):
                        logger.debug(f"    error: {r}")

    async def _process_mode_pair(self, mode: dict, pair: str, tf: str) -> bool:
        """Run pattern detection for one mode/pair/timeframe combo."""
        try:
            cooldown_key = f"{mode['id']}:{pair}:{tf}"
            loop = asyncio.get_event_loop()

            # ── 1. Fetch OHLCV ─────────────────────────────────────────────
            df = await self._fetch_data(pair, tf)
            if df is None or len(df) < 60:
                return False

            # Trim to last 300 bars — enough for indicators (window≤50) and
            # patterns (lookback≤80).  Cuts O(n²) wedge detection by 94%.
            df = df.tail(300).copy()

            # ── 2. Compute indicators (CPU-heavy — run in thread) ──────────
            df = await loop.run_in_executor(None, _compute_indicators, df)

            # ── 3. Detect pattern (CPU-heavy — run in thread) ──────────────
            pattern_func = _get_pattern_func(mode['pattern'])
            if pattern_func is None:
                logger.error(f"Pattern '{mode['pattern']}' not found")
                return False

            signals = await loop.run_in_executor(None, pattern_func, df)

            # ── 4. Apply indicator filter ──────────────────────────────────
            signals = _apply_filter(df, signals, mode['filter'], mode['direction'])

            # ── 5. Check last bar(s) for active signal ─────────────────────
            # Look at last 5 bars to catch fresh signals
            signal_bar_idx = None
            signal_bar_ts  = None
            for lookback in [0, 1, 2, 3, 4]:
                idx = -(1 + lookback)
                if len(signals) >= abs(idx):
                    direction_val = 1 if mode['direction'] == 'BUY' else -1
                    if signals.iloc[idx] == direction_val:
                        signal_bar_idx = idx
                        signal_bar_ts  = df.index[idx]
                        break

            if signal_bar_idx is None:
                return False  # No pattern found in recent bars

            # ── 6. Cooldown check ──────────────────────────────────────────
            last_ts = _last_signal_bar.get(cooldown_key)
            cooldown_mins = TF_COOLDOWN_MINS.get(tf, 120)
            if last_ts is not None:
                # If the last sent signal was for the same bar, skip
                if hasattr(signal_bar_ts, 'to_pydatetime'):
                    signal_bar_ts_dt = signal_bar_ts.to_pydatetime()
                else:
                    signal_bar_ts_dt = signal_bar_ts
                if hasattr(signal_bar_ts_dt, 'tzinfo') and signal_bar_ts_dt.tzinfo is None:
                    signal_bar_ts_dt = signal_bar_ts_dt.replace(tzinfo=timezone.utc)

                if last_ts >= signal_bar_ts_dt:
                    return False  # Same bar already processed

                # Also enforce time-based cooldown
                elapsed = (datetime.now(timezone.utc) - last_ts).total_seconds() / 60
                if elapsed < cooldown_mins:
                    return False

            # ── 6b. DB-based dedup ─────────────────────────────────────────
            # Prevents duplicate signals across bot restarts and multiple instances.
            # In-memory cooldown (step 6) is lost on restart — DB check is the
            # reliable guard.
            if self.db.has_open_pattern_signal(pair, mode['name'], tf):
                return False

            # ── 7. Economic calendar gate ──────────────────────────────────
            try:
                econ_gate = self.econ_cal.check_gate(pair, minutes_before=30, minutes_after=30)
                if econ_gate.get('action') == 'BLOCK':
                    logger.info(
                        f"[{mode['name']}] {pair} {tf}: ECON BLOCKED — {econ_gate.get('reason', '')}"
                    )
                    return False
            except Exception as e:
                logger.warning(f"[{mode['name']}] {pair} {tf}: econ gate error: {e}")

            # ── 8. Calculate ATR-based SL/TP ───────────────────────────────
            entry = float(df['close'].iloc[-1])
            atr   = _get_atr(df)
            if atr is None or atr <= 0:
                logger.warning(f"[{mode['name']}] {pair} {tf}: ATR not available")
                return False

            sl, tp = _calc_sl_tp(entry, mode['direction'], atr,
                                  mode['sl_mult'], mode['tp_mult'])

            pip_size = _pip_size(pair)
            sl_pips  = round(abs(entry - sl) / pip_size, 1)
            tp_pips  = round(abs(entry - tp) / pip_size, 1)
            rr_ratio = round(tp_pips / sl_pips, 2) if sl_pips > 0 else 0.0

            # Entry Zone: ±ATR×0.3 around entry price
            zone_dist       = atr * 0.3
            entry_zone_low  = round(entry - zone_dist, _price_decimals(pair))
            entry_zone_high = round(entry + zone_dist, _price_decimals(pair))
            # Max Entry: upper bound for BUY, lower bound for SELL
            max_entry = entry_zone_high if mode['direction'] == 'BUY' else entry_zone_low

            # Valid Until: 2 candles from now in BDT
            _BDT = timezone(timedelta(hours=6))
            tf_mins      = _TF_MINS.get(tf, 60)
            now          = datetime.now(timezone.utc)
            valid_until  = now + timedelta(minutes=tf_mins * 2)
            valid_until_str = valid_until.astimezone(_BDT).strftime('%d %b, %I:%M %p')

            # ── 9. Build signal dict ───────────────────────────────────────
            # ── Pattern quality score ───────────────────────────────────
            import json as _json
            _wr, _pf = 65.0, 1.5
            try:
                _m = re.search(r'WR\s+([\d.]+)%', mode.get('stats', ''))
                if _m: _wr = float(_m.group(1))
                _m = re.search(r'PF\s+([\d.]+)', mode.get('stats', ''))
                if _m: _pf = float(_m.group(1))
            except Exception:
                pass

            _s_base    = 30                                  # Pattern detected
            _s_filter  = 20                                  # Filter confirmed
            _s_wr      = min(25, (_wr - 50) * 1.0)          # WR 50%=0, 75%=25
            _s_rr      = min(15, rr_ratio * 10)              # R:R 1.5 → 15
            _s_pf      = min(10, min(_pf, 10) * 1.0)        # PF capped at 10
            _pattern_score = round(min(100, _s_base + _s_filter + _s_wr + _s_rr + _s_pf), 1)

            if _pattern_score >= 80:   _quality_label = 'Strong'
            elif _pattern_score >= 65: _quality_label = 'Good'
            elif _pattern_score >= 50: _quality_label = 'Fair'
            else:                      _quality_label = 'Weak'

            _score_json = _json.dumps({
                'pattern_base': _s_base,
                'filter_confirmed': _s_filter,
                'win_rate_bonus': round(_s_wr, 1),
                'risk_reward_bonus': round(_s_rr, 1),
                'profit_factor_bonus': round(_s_pf, 1),
                'backtest_wr': _wr,
                'backtest_pf': _pf,
            })
            _reasoning = (
                f"{mode['pattern']} pattern detected on {tf}, "
                f"confirmed by {mode['filter']} filter. "
                f"Backtest: WR {_wr}%, PF {_pf}. "
                f"R:R = 1:{rr_ratio:.2f}, SL={sl_pips:.1f}p TP={tp_pips:.1f}p"
            )

            sig_id   = (
                f"LST-M{mode['id']}-{pair}-{tf}-"
                f"{now.strftime('%Y%m%d-%H%M%S')}"
            )

            signal = {
                'signal_id':         sig_id,
                'pair':              pair,
                'direction':         mode['direction'],
                'mode':              mode['name'],
                'mode_label':        mode['label'],
                'mode_stats':        mode['stats'],
                'pattern':           mode['pattern'],
                'filter_name':       mode['filter'],
                'strategy':          f"{mode['pattern']}+{mode['filter']}",
                'entry_price':       round(entry, _price_decimals(pair)),
                'entry_zone_low':    entry_zone_low,
                'entry_zone_high':   entry_zone_high,
                'max_entry':         max_entry,
                'valid_until_str':   valid_until_str,
                'stop_loss':         round(sl, _price_decimals(pair)),
                'take_profit':       round(tp, _price_decimals(pair)),
                'sl_pips':           sl_pips,
                'tp_pips':           tp_pips,
                'risk_reward_ratio': rr_ratio,
                'timeframe':         tf,
                'confluence_score':  _pattern_score,
                'quality_label':     _quality_label,
                'score_breakdown':   _score_json,
                'reasoning':         _reasoning,
                'suggested_lot':     0.01,  # Default — adjusted by position sizer
                'risk_amount':       0.0,
            }

            # ── 10. Position sizing ────────────────────────────────────────
            try:
                from risk.position_sizer import PositionSizer
                sizer  = PositionSizer()
                result = sizer.calculate(
                    pair=pair,
                    account_balance=self.config.account_balance,
                    risk_pct=self.config.risk_per_trade_pct,
                    sl_pips=sl_pips,
                )
                signal['suggested_lot'] = result['lot_size']
                signal['risk_amount']   = result['risk_amount']
            except Exception as e:
                logger.warning(f"[{mode['name']}] Position sizer error: {e}")

            # ── 10b. Validate signal before DB insert ──────────────────
            if entry <= 0 or sl <= 0 or tp <= 0:
                logger.warning(f"[{mode['name']}] {pair} {tf}: SKIPPED — invalid prices entry={entry} sl={sl} tp={tp}")
                return False
            if sl_pips <= 0 or tp_pips <= 0:
                logger.warning(f"[{mode['name']}] {pair} {tf}: SKIPPED — zero pips sl={sl_pips} tp={tp_pips}")
                return False

            # ── 11. Save to DB ─────────────────────────────────────────────
            try:
                self.db.save_signal(signal)
            except Exception as e:
                logger.warning(f"[{mode['name']}] DB save failed: {e}")

            # ── 12. Send Telegram ──────────────────────────────────────────
            if self._notifier and self.config.telegram_enabled:
                try:
                    await self._notifier.send_pattern_signal(signal)
                except Exception as e:
                    logger.error(f"[{mode['name']}] Telegram send failed: {e}")

            # ── 13. Update cooldown ────────────────────────────────────────
            if hasattr(signal_bar_ts, 'to_pydatetime'):
                ts_dt = signal_bar_ts.to_pydatetime()
            else:
                ts_dt = signal_bar_ts
            if hasattr(ts_dt, 'tzinfo') and ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=timezone.utc)
            _last_signal_bar[cooldown_key] = ts_dt

            logger.info(
                f"PATTERN SIGNAL: [{mode['label']}] {pair} {tf} {mode['direction']} "
                f"@ {entry} SL={sl} TP={tp} "
                f"(SL={sl_pips:.0f}p TP={tp_pips:.0f}p R:R=1:{rr_ratio})"
            )
            return True

        except Exception as e:
            logger.error(
                f"[{mode.get('name', '?')}] {pair} {tf}: error: {e}",
                exc_info=True,
            )
            return False

    async def _fetch_data(self, pair: str, tf: str) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data.
        Priority: market_data_cache (Binance/TwelveData) → PriceFetcher (Yahoo)
        Cache is refreshed if older than 30 min (short TFs) or 60 min (H4+).
        """
        bars = TF_BARS.get(tf, 200)
        loop = asyncio.get_event_loop()

        # ── 1. Try market_data_cache (reliable: Binance for crypto, TwelveData for forex)
        try:
            df = await loop.run_in_executor(None, _fetch_via_cache, pair, tf)
            if df is not None and len(df) >= 50:
                return df.tail(bars)
        except Exception as e:
            logger.debug(f"Cache fetch error {pair} {tf}: {e}")

        # ── 2. Fallback: PriceFetcher (Yahoo Finance)
        try:
            from data.price_fetcher import PriceFetcher
            fetcher = PriceFetcher()
            df = await fetcher.get_ohlcv(pair, tf, bars=bars)
            if df is not None and len(df) >= 50:
                return df
        except Exception as e:
            logger.debug(f"PriceFetcher fallback error {pair} {tf}: {e}")

        return None


# ── Indicator computation ─────────────────────────────────────────────────────

def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute RSI, EMA, ADX, ATR needed for pattern filters."""
    try:
        import ta
        close = df['close'].astype(float)
        high  = df['high'].astype(float)
        low   = df['low'].astype(float)

        df = df.copy()

        # RSI 14
        df['rsi_14'] = ta.momentum.RSIIndicator(close, window=14).rsi()

        # EMA 20, 50
        df['ema_20'] = ta.trend.EMAIndicator(close, window=20).ema_indicator()
        df['ema_50'] = ta.trend.EMAIndicator(close, window=50).ema_indicator()

        # ADX 14
        adx = ta.trend.ADXIndicator(high, low, close, window=14)
        df['adx_14'] = adx.adx()

        # ATR 14
        df['atr_14'] = ta.volatility.AverageTrueRange(
            high, low, close, window=14
        ).average_true_range()

        # MACD histogram (for completeness)
        macd = ta.trend.MACD(close, window_fast=12, window_slow=26, window_sign=9)
        df['macd_hist'] = macd.macd_diff()

    except ImportError:
        logger.warning("ta library not available — filters may not work")
    except Exception as e:
        logger.warning(f"Indicator compute error: {e}")

    return df


def _get_atr(df: pd.DataFrame) -> Optional[float]:
    """Get latest ATR value."""
    if 'atr_14' in df.columns:
        val = df['atr_14'].iloc[-1]
        if not np.isnan(val) and val > 0:
            return float(val)
    return None


# ── Pattern detection ─────────────────────────────────────────────────────────

def _get_pattern_func(pattern_name: str):
    """Return pattern detection function by name."""
    try:
        from patterns.chart_detector import get_all_chart_patterns
        patterns = get_all_chart_patterns()
        for p in patterns:
            if p['name'] == pattern_name:
                return p['func']
    except Exception as e:
        logger.error(f"Pattern lookup failed: {e}")

    try:
        from patterns.candlestick_detector import get_all_candlestick_patterns
        patterns = get_all_candlestick_patterns()
        for p in patterns:
            if p['name'] == pattern_name:
                return p['func']
    except Exception:
        pass

    return None


# ── Indicator filters ─────────────────────────────────────────────────────────

def _apply_filter(df: pd.DataFrame, signals: pd.Series,
                  filter_name: str, direction: str) -> pd.Series:
    """Apply indicator filter to raw pattern signals."""
    is_buy = (direction == 'BUY')

    if filter_name == 'Alone':
        return signals  # No filter — use raw pattern signal

    if filter_name == 'RSI':
        col = 'rsi_14'
        if col not in df.columns:
            return signals
        rsi = df[col].values
        out = signals.copy().values.astype(float)
        for i in range(len(out)):
            if out[i] == 1 and rsi[i] > 60:
                out[i] = 0
            elif out[i] == -1 and rsi[i] < 40:
                out[i] = 0
        return pd.Series(out, index=df.index, dtype=int)

    if filter_name == 'EMA_Trend':
        f_col, s_col = 'ema_20', 'ema_50'
        if f_col not in df.columns or s_col not in df.columns:
            return signals
        ema_f = df[f_col].values
        ema_s = df[s_col].values
        out = signals.copy().values.astype(float)
        for i in range(len(out)):
            if out[i] == 1 and ema_f[i] < ema_s[i]:
                out[i] = 0
            elif out[i] == -1 and ema_f[i] > ema_s[i]:
                out[i] = 0
        return pd.Series(out, index=df.index, dtype=int)

    if filter_name == 'ADX':
        col = 'adx_14'
        if col not in df.columns:
            return signals
        adx = df[col].values
        out = signals.copy().values.astype(float)
        for i in range(len(out)):
            if out[i] != 0 and adx[i] < 20:
                out[i] = 0
        return pd.Series(out, index=df.index, dtype=int)

    if filter_name == 'MACD':
        col = 'macd_hist'
        if col not in df.columns:
            return signals
        hist = df[col].values
        out = signals.copy().values.astype(float)
        for i in range(len(out)):
            if out[i] == 1 and hist[i] < 0:
                out[i] = 0
            elif out[i] == -1 and hist[i] > 0:
                out[i] = 0
        return pd.Series(out, index=df.index, dtype=int)

    return signals  # Unknown filter — pass through


# ── SL/TP and pip helpers ─────────────────────────────────────────────────────

def _calc_sl_tp(entry: float, direction: str,
                atr: float, sl_mult: float, tp_mult: float):
    """Calculate SL and TP from ATR multipliers."""
    sl_dist = atr * sl_mult
    tp_dist = atr * tp_mult

    if direction == 'BUY':
        sl = entry - sl_dist
        tp = entry + tp_dist
    else:  # SELL
        sl = entry + sl_dist
        tp = entry - tp_dist

    return sl, tp


def _pip_size(pair: str) -> float:
    """Return pip size — delegates to centralized pair_config."""
    return _cfg_pip_size(pair)
def _price_decimals(pair: str) -> int:
    """Return decimal places — delegates to centralized pair_config."""
    return _cfg_decimals(pair)
# ── Data fetching via market_data_cache (Binance + TwelveData) ───────────────

# Per-TF max cache age before we force a fresh download.
_CACHE_MAX_AGE_MINS = {
    'M5':   6,    # 1 bar = 5 min  + 1 min buffer
    'M15':  16,   # 1 bar = 15 min + 1 min buffer
    'M30':  31,   # 1 bar = 30 min + 1 min buffer
    'H1':   61,   # 1 bar = 60 min + 1 min buffer
    'H4':  241,   # 1 bar = 240 min + 1 min buffer
    'D1': 1441,   # 1 bar = 1440 min + 1 min buffer
}

# Download locks — prevents multiple modes from downloading the same pair+TF
# simultaneously (avoids TwelveData rate limit bursts when 21 modes run together)
import threading as _threading
_download_locks: dict[str, _threading.Lock] = {}
_download_locks_meta = _threading.Lock()

def _get_download_lock(pair: str, tf: str) -> _threading.Lock:
    key = f"{pair}:{tf}"
    with _download_locks_meta:
        if key not in _download_locks:
            _download_locks[key] = _threading.Lock()
        return _download_locks[key]

# TF → minutes (for Valid Until calculation)
_TF_MINS = {'M5': 5, 'M15': 15, 'M30': 30, 'H1': 60, 'H4': 240, 'D1': 1440}


def _fetch_via_cache(pair: str, tf: str) -> Optional[pd.DataFrame]:
    """
    Fetch data using market_data_cache:
      - Crypto → Binance (CCXT), free + unlimited
      - Forex  → Twelve Data API, 800 req/day free
      - Fallback → yfinance
    Force-downloads if cached CSV is older than _CACHE_MAX_AGE_MINS.
    """
    import time as _time
    from pathlib import Path
    from data.market_data_cache import (
        _csv_path, load_cached, download_and_save,
        CCXT_MAP, TWELVE_MAP,
    )

    max_age_mins = _CACHE_MAX_AGE_MINS.get(tf, 60)
    path: Path = _csv_path(pair, tf)

    need_download = True
    if path.exists():
        age_mins = (_time.time() - path.stat().st_mtime) / 60
        if age_mins < max_age_mins:
            need_download = False

    if need_download:
        # Acquire per-(pair,tf) lock — only one mode downloads at a time.
        # Other modes wait, then find the fresh CSV and skip their own download.
        lock = _get_download_lock(pair, tf)
        with lock:
            # Re-check after acquiring lock (another mode may have downloaded)
            if path.exists():
                age_mins = (_time.time() - path.stat().st_mtime) / 60
                if age_mins < max_age_mins:
                    return load_cached(pair, tf)
            ok = download_and_save(pair, tf)
            if not ok:
                return load_cached(pair, tf)

    return load_cached(pair, tf)
