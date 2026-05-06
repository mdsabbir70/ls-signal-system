"""
Market Data Cache — Downloads OHLCV data and saves locally as CSV.

Sources:
  - Crypto: CCXT (Binance) — free, unlimited, no API key
  - Forex:  Twelve Data API — reliable, free tier 800 req/day
  - Fallback: yfinance

Usage:
  python -m data.market_data_cache          # download all pairs, all TFs
  python -m data.market_data_cache EURUSD   # download specific pair
"""

from __future__ import annotations
import os
import time
import datetime
import logging
from pathlib import Path

import pandas as pd
import numpy as np

logger = logging.getLogger('data_cache')

# ── Configuration ────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parent.parent.parent / 'cached_data'

# Twelve Data API key (set via env var or hardcoded here)
TWELVE_DATA_API_KEY = os.environ.get('TWELVE_DATA_API_KEY', '0e0895b8bb7a4c9bbfb98d295ca82554')

FOREX_PAIRS = [
    'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'AUDUSD',
    'USDCAD', 'NZDUSD', 'EURJPY', 'GBPJPY', 'AUDJPY',
    'EURGBP', 'XAUUSD',
]

CRYPTO_PAIRS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'BNBUSDT',
    'DOGEUSDT', 'ADAUSDT', 'LINKUSDT', 'DOTUSDT', 'PEPEUSDT',
]

ALL_PAIRS = FOREX_PAIRS + CRYPTO_PAIRS

YAHOO_MAP = {
    'EURUSD': 'EURUSD=X', 'GBPUSD': 'GBPUSD=X', 'USDJPY': 'USDJPY=X',
    'USDCHF': 'USDCHF=X', 'AUDUSD': 'AUDUSD=X', 'USDCAD': 'USDCAD=X',
    'NZDUSD': 'NZDUSD=X', 'XAUUSD': 'XAUUSD=X', 'EURJPY': 'EURJPY=X',
    'GBPJPY': 'GBPJPY=X', 'AUDJPY': 'AUDJPY=X', 'EURGBP': 'EURGBP=X',
    'BTCUSDT': 'BTC-USD', 'ETHUSDT': 'ETH-USD', 'SOLUSDT': 'SOL-USD',
    'XRPUSDT': 'XRP-USD', 'BNBUSDT': 'BNB-USD', 'DOGEUSDT': 'DOGE-USD',
    'ADAUSDT': 'ADA-USD', 'LINKUSDT': 'LINK-USD', 'DOTUSDT': 'DOT-USD',
    'PEPEUSDT': 'PEPE24478-USD',
}

# Twelve Data symbol mapping (forex pairs)
TWELVE_MAP = {
    'EURUSD': 'EUR/USD', 'GBPUSD': 'GBP/USD', 'USDJPY': 'USD/JPY',
    'USDCHF': 'USD/CHF', 'AUDUSD': 'AUD/USD', 'USDCAD': 'USD/CAD',
    'NZDUSD': 'NZD/USD', 'XAUUSD': 'XAU/USD', 'EURJPY': 'EUR/JPY',
    'GBPJPY': 'GBP/JPY', 'AUDJPY': 'AUD/JPY', 'EURGBP': 'EUR/GBP',
}

# Twelve Data interval mapping
TWELVE_TF_MAP = {
    'M5':  {'interval': '5min',  'outputsize': 5000},
    'M15': {'interval': '15min', 'outputsize': 5000},
    'M30': {'interval': '30min', 'outputsize': 5000},
    'H1':  {'interval': '1h',    'outputsize': 5000},
    'H4':  {'interval': '4h',    'outputsize': 5000},
    'D1':  {'interval': '1day',  'outputsize': 5000},
}

# CCXT Binance symbol mapping
CCXT_MAP = {
    'BTCUSDT': 'BTC/USDT', 'ETHUSDT': 'ETH/USDT', 'SOLUSDT': 'SOL/USDT',
    'XRPUSDT': 'XRP/USDT', 'BNBUSDT': 'BNB/USDT', 'DOGEUSDT': 'DOGE/USDT',
    'ADAUSDT': 'ADA/USDT', 'LINKUSDT': 'LINK/USDT', 'DOTUSDT': 'DOT/USDT',
    'PEPEUSDT': 'PEPE/USDT',
}

# Timeframe configs
TF_CONFIG = {
    'M5':  {'yf_interval': '5m',  'yf_period': '60d',  'ccxt_tf': '5m',  'ccxt_days': 55,   'resample': None},
    'M15': {'yf_interval': '15m', 'yf_period': '60d',  'ccxt_tf': '15m', 'ccxt_days': 55,   'resample': None},
    'M30': {'yf_interval': '30m', 'yf_period': '60d',  'ccxt_tf': '30m', 'ccxt_days': 55,   'resample': None},
    'H1':  {'yf_interval': '1h',  'yf_period': '730d', 'ccxt_tf': '1h',  'ccxt_days': 700,  'resample': None},
    'H4':  {'yf_interval': '1h',  'yf_period': '730d', 'ccxt_tf': '4h',  'ccxt_days': 700,  'resample': '4h'},
    'D1':  {'yf_interval': '1d',  'yf_period': '10y',  'ccxt_tf': '1d',  'ccxt_days': 3650, 'resample': None},
}

DEFAULT_TIMEFRAMES = ['M15', 'M30', 'H1', 'H4', 'D1']


# ═══════════════════════════════════════════════════════════════════════════════
#  CCXT Downloader (Crypto)
# ═══════════════════════════════════════════════════════════════════════════════

def _download_ccxt(pair: str, timeframe: str) -> pd.DataFrame | None:
    """Download OHLCV from Binance via CCXT."""
    try:
        import ccxt
    except ImportError:
        logger.warning("ccxt not installed")
        return None

    symbol = CCXT_MAP.get(pair)
    if not symbol:
        return None

    cfg = TF_CONFIG.get(timeframe)
    if not cfg:
        return None

    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        tf = cfg['ccxt_tf']
        since_ms = int((datetime.datetime.now() - datetime.timedelta(days=cfg['ccxt_days'])).timestamp() * 1000)

        all_ohlcv = []
        limit = 1000

        while True:
            ohlcv = exchange.fetch_ohlcv(symbol, tf, since=since_ms, limit=limit)
            if not ohlcv:
                break
            all_ohlcv.extend(ohlcv)
            since_ms = ohlcv[-1][0] + 1
            if len(ohlcv) < limit:
                break
            time.sleep(0.1)

        if not all_ohlcv:
            return None

        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.set_index('datetime')
        df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        df = df[~df.index.duplicated(keep='first')]
        df = df.sort_index()

        # H4 resample if needed (ccxt has native 4h, but just in case)
        if cfg.get('resample') and cfg['ccxt_tf'] != cfg['resample']:
            df = _resample(df, cfg['resample'])

        return df

    except Exception as e:
        logger.error(f"CCXT error {pair} {timeframe}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Twelve Data Downloader (Forex)
# ═══════════════════════════════════════════════════════════════════════════════

def _download_twelvedata(pair: str, timeframe: str) -> pd.DataFrame | None:
    """Download OHLCV from Twelve Data API (forex pairs)."""
    import urllib.request
    import json

    symbol = TWELVE_MAP.get(pair)
    if not symbol:
        return None

    cfg = TWELVE_TF_MAP.get(timeframe)
    if not cfg:
        return None

    if not TWELVE_DATA_API_KEY:
        logger.warning("TWELVE_DATA_API_KEY not set")
        return None

    try:
        url = (
            f"https://api.twelvedata.com/time_series"
            f"?symbol={symbol}"
            f"&interval={cfg['interval']}"
            f"&outputsize={cfg['outputsize']}"
            f"&apikey={TWELVE_DATA_API_KEY}"
            f"&order=ASC"
        )
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())

        if data.get('status') == 'error' or 'values' not in data:
            logger.warning(f"Twelve Data error for {pair} {timeframe}: {data.get('message','unknown')}")
            return None

        values = data['values']
        if not values:
            return None

        rows = []
        for v in values:
            rows.append({
                'datetime': pd.to_datetime(v['datetime']),
                'open':  float(v['open']),
                'high':  float(v['high']),
                'low':   float(v['low']),
                'close': float(v['close']),
                'volume': float(v.get('volume', 0)),
            })

        df = pd.DataFrame(rows).set_index('datetime')
        df = df[~df.index.duplicated(keep='first')].sort_index()
        df = df.dropna(subset=['open', 'high', 'low', 'close'])

        logger.info(f"TwelveData OK: {pair} {timeframe} — {len(df)} bars")
        return df

    except Exception as e:
        logger.error(f"Twelve Data error {pair} {timeframe}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  yfinance Downloader (Forex + fallback)
# ═══════════════════════════════════════════════════════════════════════════════

def _download_yfinance(pair: str, timeframe: str, retries: int = 3) -> pd.DataFrame | None:
    """Download OHLCV from yfinance with retry."""
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed")
        return None

    symbol = YAHOO_MAP.get(pair, pair)
    cfg = TF_CONFIG.get(timeframe)
    if not cfg:
        return None

    for attempt in range(retries):
        try:
            df = yf.download(
                symbol,
                interval=cfg['yf_interval'],
                period=cfg['yf_period'],
                progress=False,
                auto_adjust=True,
            )

            if df is None or df.empty:
                if attempt < retries - 1:
                    time.sleep(3 * (attempt + 1))
                    continue
                return None

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

            df.columns = [c.lower().strip() for c in df.columns]

            for col in ['open', 'high', 'low', 'close']:
                if col not in df.columns:
                    return None

            if cfg.get('resample'):
                df = _resample(df, cfg['resample'])

            df = df.dropna(subset=['open', 'high', 'low', 'close'])
            return df

        except Exception as e:
            logger.warning(f"yfinance attempt {attempt+1}/{retries} failed for {pair} {timeframe}: {e}")
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1))

    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
    if 'volume' in df.columns:
        agg['volume'] = 'sum'
    return df.resample(rule).agg(agg).dropna()


def _csv_path(pair: str, timeframe: str) -> Path:
    return DATA_DIR / f"{pair}_{timeframe}.csv"


# ═══════════════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════════════

def download_and_save(pair: str, timeframe: str) -> bool:
    """Download data for a pair/TF and save to CSV. Returns True on success."""
    pair = pair.upper()
    is_crypto = pair in CCXT_MAP
    is_forex  = pair in TWELVE_MAP

    df = None

    # Crypto: use CCXT (Binance)
    if is_crypto:
        df = _download_ccxt(pair, timeframe)

    # Forex: use Twelve Data (primary)
    if df is None or len(df) < 50:
        if is_forex:
            df = _download_twelvedata(pair, timeframe)
            time.sleep(8)  # Twelve Data free: max 8 req/min → wait 8s

    # Fallback: yfinance
    if df is None or len(df) < 50:
        df = _download_yfinance(pair, timeframe)
        if df is not None and len(df) > 50:
            logger.info(f"yfinance OK: {pair} {timeframe} — {len(df)} bars")

    if df is None or len(df) < 50:
        logger.warning(f"FAILED: {pair} {timeframe} — no data from any source")
        return False

    # Save
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _csv_path(pair, timeframe)
    df.to_csv(path)
    logger.info(f"Saved: {path.name} ({len(df)} bars, {df.index[0]} → {df.index[-1]})")
    return True


def load_cached(pair: str, timeframe: str, lookback_days: int = 0) -> pd.DataFrame | None:
    """Load data from local CSV cache. Returns None if not found."""
    pair = pair.upper()
    path = _csv_path(pair, timeframe)

    if not path.exists():
        return None

    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        df.columns = [c.lower().strip() for c in df.columns]

        for col in ['open', 'high', 'low', 'close']:
            if col not in df.columns:
                return None

        df = df.dropna(subset=['open', 'high', 'low', 'close'])

        # Apply lookback filter
        if lookback_days > 0:
            cutoff = pd.Timestamp.now() - pd.Timedelta(days=lookback_days)
            df = df[df.index >= cutoff]

        if len(df) < 50:
            return None

        return df

    except Exception as e:
        logger.error(f"Error loading {path}: {e}")
        return None


def load_or_download(pair: str, timeframe: str, lookback_days: int = 0) -> pd.DataFrame | None:
    """Load from cache, or download if missing/stale. Best function to use."""
    pair = pair.upper()
    path = _csv_path(pair, timeframe)

    # Check if cache is fresh (less than 2 hours old)
    if path.exists():
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        if age_hours < 2.0:
            df = load_cached(pair, timeframe, lookback_days)
            if df is not None:
                return df

    # Download fresh data
    success = download_and_save(pair, timeframe)
    if success:
        return load_cached(pair, timeframe, lookback_days)

    # Fallback: use stale cache if exists
    if path.exists():
        logger.warning(f"Using stale cache for {pair} {timeframe}")
        return load_cached(pair, timeframe, lookback_days)

    return None


def download_all(pairs: list[str] | None = None, timeframes: list[str] | None = None):
    """Download all pairs × timeframes and save to cache."""
    pairs = pairs or ALL_PAIRS
    timeframes = timeframes or DEFAULT_TIMEFRAMES

    total = len(pairs) * len(timeframes)
    success = 0
    failed = 0

    print(f"\n{'=' * 60}")
    print(f"  Market Data Cache — Downloading {total} files")
    print(f"  Pairs: {len(pairs)} | Timeframes: {', '.join(timeframes)}")
    print(f"  Save to: {DATA_DIR}")
    print(f"{'=' * 60}\n")

    start = time.time()

    for pair in pairs:
        for tf in timeframes:
            ok = download_and_save(pair, tf)
            if ok:
                success += 1
            else:
                failed += 1

    elapsed = time.time() - start
    print(f"\n  Done in {elapsed:.0f}s — {success} OK, {failed} failed\n")
    return success, failed


def get_cache_info() -> list[dict]:
    """Return info about all cached files."""
    if not DATA_DIR.exists():
        return []

    info = []
    for f in sorted(DATA_DIR.glob('*.csv')):
        parts = f.stem.split('_')
        if len(parts) >= 2:
            pair = parts[0]
            tf = parts[1]
        else:
            pair, tf = f.stem, '?'

        try:
            size_kb = f.stat().st_size / 1024
            age_hours = (time.time() - f.stat().st_mtime) / 3600
            df = pd.read_csv(f, index_col=0, parse_dates=True)
            bars = len(df)
            start = str(df.index[0])[:19]
            end = str(df.index[-1])[:19]
        except Exception:
            size_kb = 0
            age_hours = 0
            bars = 0
            start = end = '?'

        info.append({
            'pair': pair, 'tf': tf, 'bars': bars,
            'size_kb': round(size_kb, 1),
            'age_hours': round(age_hours, 1),
            'start': start, 'end': end,
        })

    return info


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    if len(sys.argv) > 1:
        pair = sys.argv[1].upper()
        tfs = sys.argv[2].split(',') if len(sys.argv) > 2 else DEFAULT_TIMEFRAMES
        download_all([pair], tfs)
    else:
        download_all()
