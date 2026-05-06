"""
Forex Price Data Fetcher
Fetches OHLCV candle data from free/public sources.

Primary:  Alpha Vantage (free tier: 25 req/day)
Fallback: Yahoo Finance via yfinance (no key needed)
MT5:      MetaTrader5 Python library (Windows only, optional)

Returns pandas DataFrame with columns: open, high, low, close, volume
Index: DatetimeIndex (UTC)
"""

from __future__ import annotations
import os
import time
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd
import requests

from utils.logger import setup_logger

logger = setup_logger('price_fetcher')

# Timeframe → Alpha Vantage interval mapping
AV_INTERVAL_MAP = {
    'M1':  '1min',
    'M5':  '5min',
    'M15': '15min',
    'M30': '30min',
    'H1':  '60min',
    'H4':  None,      # AV doesn't have 4h directly — fetch 1h and resample
    'D1':  'daily',
}

# Yahoo Finance symbol mapping (add .=X suffix for Forex)
YAHOO_SYMBOL_MAP = {
    # Forex majors & minors
    'EURUSD': 'EURUSD=X',
    'GBPUSD': 'GBPUSD=X',
    'USDJPY': 'USDJPY=X',
    'USDCHF': 'USDCHF=X',
    'AUDUSD': 'AUDUSD=X',
    'USDCAD': 'USDCAD=X',
    'NZDUSD': 'NZDUSD=X',
    'XAUUSD': 'XAUUSD=X',  # Spot gold (fallback: GC=F futures)
    'EURJPY': 'EURJPY=X',
    'GBPJPY': 'GBPJPY=X',
    'AUDJPY': 'AUDJPY=X',
    'EURGBP': 'EURGBP=X',
    # Crypto
    'BTCUSDT': 'BTC-USD',
    'ETHUSDT': 'ETH-USD',
    'SOLUSDT': 'SOL-USD',
    'XRPUSDT': 'XRP-USD',
    'TONUSDT': 'TON11419-USD',
    'DOGEUSDT': 'DOGE-USD',
    'BNBUSDT': 'BNB-USD',
    'PEPEUSDT': 'PEPE24478-USD',
    'ADAUSDT': 'ADA-USD',
    'HYPEUSDT': 'HYPE32196-USD',
    'LINKUSDT': 'LINK-USD',
    'SUIUSDT': 'SUI20947-USD',
    'DOTUSDT': 'DOT-USD',
}

# Yahoo Finance interval mapping
YAHOO_INTERVAL_MAP = {
    'M1':  '1m',
    'M5':  '5m',
    'M15': '15m',
    'M30': '30m',
    'H1':  '1h',
    'H4':  '1h',   # Resample to 4h
    'D1':  '1d',
}

YAHOO_PERIOD_MAP = {
    'M1':  '7d',
    'M5':  '60d',
    'M15': '60d',
    'M30': '60d',
    'H1':  '730d',
    'H4':  '730d',
    'D1':  '5y',
}


class PriceFetcher:
    """Fetches OHLCV data for Forex pairs."""

    def __init__(self):
        self.av_api_key = os.getenv('ALPHA_VANTAGE_API_KEY', '')
        self._cache: dict = {}          # {(pair, tf): (df, fetched_at)}
        self._cache_ttl = {
            'H1': 300,    # 5 min
            'H4': 900,    # 15 min
            'D1': 3600,   # 1 hour
        }

    async def get_ohlcv(
        self,
        pair: str,
        timeframe: str,
        bars: int = 200,
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data for pair/timeframe.
        Uses cache to avoid redundant API calls.
        """
        cache_key = (pair, timeframe)
        cached = self._cache.get(cache_key)
        ttl = self._cache_ttl.get(timeframe, 300)

        if cached:
            df, fetched_at = cached
            if (time.time() - fetched_at) < ttl:
                return df.tail(bars)

        # Fetch fresh data
        df = await self._fetch(pair, timeframe)

        if df is not None and len(df) >= 20:
            self._cache[cache_key] = (df, time.time())
            logger.info(f"Fetched {len(df)} bars for {pair} {timeframe}")
            return df.tail(bars)

        logger.warning(f"Failed to fetch data for {pair} {timeframe}")
        return None

    async def _fetch(self, pair: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Fetch data — try Yahoo Finance first (no key needed), AV as backup."""
        # Run blocking fetches in thread pool
        loop = asyncio.get_event_loop()

        df = await loop.run_in_executor(None, self._fetch_yahoo, pair, timeframe)
        if df is not None and len(df) >= 20:
            return df

        if self.av_api_key:
            df = await loop.run_in_executor(None, self._fetch_alpha_vantage, pair, timeframe)
            if df is not None and len(df) >= 20:
                return df

        return None

    def _fetch_yahoo(self, pair: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Fetch from Yahoo Finance using yfinance."""
        try:
            import yfinance as yf

            symbol   = YAHOO_SYMBOL_MAP.get(pair, pair)
            interval = YAHOO_INTERVAL_MAP.get(timeframe, '1h')
            period   = YAHOO_PERIOD_MAP.get(timeframe, '60d')

            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval, auto_adjust=True)

            # Gold fallback: if XAUUSD=X fails, try GC=F (futures)
            if (df is None or df.empty) and pair == 'XAUUSD':
                logger.info("XAUUSD=X failed, falling back to GC=F (gold futures)")
                ticker = yf.Ticker('GC=F')
                df = ticker.history(period=period, interval=interval, auto_adjust=True)

            if df is None or df.empty:
                return None

            df = df.rename(columns={
                'Open': 'open', 'High': 'high',
                'Low': 'low',   'Close': 'close',
                'Volume': 'volume',
            })[['open', 'high', 'low', 'close', 'volume']]

            df.index = pd.to_datetime(df.index, utc=True)

            # Resample H1 → H4 if needed
            if timeframe == 'H4':
                df = df.resample('4h').agg({
                    'open':   'first',
                    'high':   'max',
                    'low':    'min',
                    'close':  'last',
                    'volume': 'sum',
                }).dropna()

            df.dropna(inplace=True)
            return df

        except ImportError:
            logger.warning("yfinance not installed — pip install yfinance")
            return None
        except Exception as e:
            logger.error(f"Yahoo Finance fetch failed for {pair} {timeframe}: {e}")
            return None

    def _fetch_alpha_vantage(self, pair: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Fetch from Alpha Vantage (free key required)."""
        if not self.av_api_key:
            return None

        try:
            fetch_tf = 'H1' if timeframe == 'H4' else timeframe
            av_interval = AV_INTERVAL_MAP.get(fetch_tf)
            if not av_interval:
                return None

            # Extract base/quote from pair (e.g. EURUSD → EUR, USD)
            from_symbol = pair[:3]
            to_symbol   = pair[3:]

            if av_interval == 'daily':
                url = (
                    f"https://www.alphavantage.co/query?"
                    f"function=FX_DAILY&from_symbol={from_symbol}&to_symbol={to_symbol}"
                    f"&outputsize=full&apikey={self.av_api_key}"
                )
                key = 'Time Series FX (Daily)'
            else:
                url = (
                    f"https://www.alphavantage.co/query?"
                    f"function=FX_INTRADAY&from_symbol={from_symbol}&to_symbol={to_symbol}"
                    f"&interval={av_interval}&outputsize=full&apikey={self.av_api_key}"
                )
                key = f"Time Series FX ({av_interval})"

            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if key not in data:
                logger.warning(f"AV: key '{key}' not in response for {pair}")
                return None

            rows = []
            for ts, vals in data[key].items():
                rows.append({
                    'datetime': pd.to_datetime(ts, utc=True),
                    'open':     float(vals['1. open']),
                    'high':     float(vals['2. high']),
                    'low':      float(vals['3. low']),
                    'close':    float(vals['4. close']),
                    'volume':   0.0,  # AV FX doesn't provide volume
                })

            df = pd.DataFrame(rows).set_index('datetime').sort_index()

            if timeframe == 'H4':
                df = df.resample('4h').agg({
                    'open': 'first', 'high': 'max',
                    'low': 'min', 'close': 'last', 'volume': 'sum'
                }).dropna()

            return df

        except Exception as e:
            logger.error(f"Alpha Vantage fetch failed for {pair} {timeframe}: {e}")
            return None

    def get_current_price(self, pair: str) -> Optional[float]:
        """Get latest price for a single pair. Used by signal monitor."""
        cache_key = ('_price', pair)
        cached = self._cache.get(cache_key)
        if cached:
            price, ts = cached
            if (time.time() - ts) < 30:   # 30-second cache
                return price

        try:
            import yfinance as yf
            symbol = YAHOO_SYMBOL_MAP.get(pair, pair)
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='1d', interval='5m')

            if (hist is None or hist.empty) and pair == 'XAUUSD':
                ticker = yf.Ticker('GC=F')
                hist = ticker.history(period='1d', interval='5m')

            if hist is not None and not hist.empty:
                price = float(hist['Close'].iloc[-1])
                self._cache[cache_key] = (price, time.time())
                return price
        except Exception as e:
            logger.error(f"Current price fetch failed for {pair}: {e}")
        return None

    def clear_cache(self, pair: str = None):
        """Clear cache for a pair (or all pairs)."""
        if pair:
            keys = [(k, tf) for (k, tf) in self._cache if k == pair]
            for key in keys:
                del self._cache[key]
        else:
            self._cache.clear()
