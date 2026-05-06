#!/usr/bin/env python3
"""Download all market data — crypto via CCXT, forex via yfinance."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from data.market_data_cache import download_all, CRYPTO_PAIRS, FOREX_PAIRS, DEFAULT_TIMEFRAMES

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--crypto':
        print("Downloading CRYPTO only (CCXT)...")
        download_all(CRYPTO_PAIRS, DEFAULT_TIMEFRAMES)
    elif len(sys.argv) > 1 and sys.argv[1] == '--forex':
        print("Downloading FOREX only (yfinance)...")
        download_all(FOREX_PAIRS, DEFAULT_TIMEFRAMES)
    else:
        print("Downloading ALL pairs...")
        # Crypto first (fast, reliable via CCXT)
        download_all(CRYPTO_PAIRS, DEFAULT_TIMEFRAMES)
        # Then forex (may fail if yfinance is down)
        download_all(FOREX_PAIRS, DEFAULT_TIMEFRAMES)
