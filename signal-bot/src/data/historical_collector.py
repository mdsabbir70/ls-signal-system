"""
Historical Data Collector
Collects up to 10 years of historical market data for backtesting & analysis.

Data sources:
  - Price OHLCV:     Yahoo Finance (yfinance) — free, no API key
  - COT Reports:     CFTC weekly reports — free CSV downloads
  - Interest Rates:  FRED API (optional key) or web data

Limitations (yfinance):
  - D1, W1: up to ~20 years available
  - H1:     ~730 days (~2 years)
  - H4:     ~730 days (resampled from H1)
  - M15/M5: ~60 days only (not collected here)
"""

import os
import sys
import time
import zipfile
import io
import csv
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Tuple

import pandas as pd
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from utils.logger import setup_logger

logger = setup_logger('historical_collector')

# ── Yahoo Finance symbol mapping ──────────────────────────────────────────────
YAHOO_SYMBOL_MAP = {
    # Forex majors & minors
    'EURUSD': 'EURUSD=X',
    'GBPUSD': 'GBPUSD=X',
    'USDJPY': 'USDJPY=X',
    'USDCHF': 'USDCHF=X',
    'AUDUSD': 'AUDUSD=X',
    'USDCAD': 'USDCAD=X',
    'NZDUSD': 'NZDUSD=X',
    'XAUUSD': 'XAUUSD=X',
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

# ── Timeframe config ──────────────────────────────────────────────────────────
TIMEFRAME_CONFIG = {
    'W1':  {'yf_interval': '1wk', 'yf_period': '10y',  'resample': None},
    'D1':  {'yf_interval': '1d',  'yf_period': '10y',  'resample': None},
    'H4':  {'yf_interval': '1h',  'yf_period': '730d', 'resample': '4h'},
    'H1':  {'yf_interval': '1h',  'yf_period': '730d', 'resample': None},
    'M30': {'yf_interval': '30m', 'yf_period': '60d',  'resample': None},
    'M15': {'yf_interval': '15m', 'yf_period': '60d',  'resample': None},
    'M5':  {'yf_interval': '5m',  'yf_period': '60d',  'resample': None},
}

# ── COT: CFTC contract names → our currency codes ────────────────────────────
COT_CURRENCY_MAP = {
    'EURO FX':              'EUR',
    'BRITISH POUND':        'GBP',
    'JAPANESE YEN':         'JPY',
    'SWISS FRANC':          'CHF',
    'AUSTRALIAN DOLLAR':    'AUD',
    'CANADIAN DOLLAR':      'CAD',
    'NZ DOLLAR':            'NZD',
    'GOLD':                 'XAU',
    'U.S. DOLLAR INDEX':    'USD',
}

# ── Interest rate: FRED series IDs ────────────────────────────────────────────
FRED_SERIES = {
    'USD': {'series': 'FEDFUNDS',     'bank': 'Federal Reserve'},
    'EUR': {'series': 'ECBDFR',       'bank': 'European Central Bank'},
    'GBP': {'series': 'BOERUKQ',      'bank': 'Bank of England'},
    'JPY': {'series': 'INTDSRJPM193N','bank': 'Bank of Japan'},
    'AUD': {'series': 'RBATCTR',      'bank': 'Reserve Bank of Australia'},
    'CAD': {'series': 'INTDSRCAM193N','bank': 'Bank of Canada'},
    'CHF': {'series': 'INTDSRCHM193N','bank': 'Swiss National Bank'},
    'NZD': {'series': 'INTDSRNZM193N','bank': 'Reserve Bank of New Zealand'},
}


class HistoricalCollector:
    """Master collector — orchestrates all data collection."""

    def __init__(self, db_engine):
        self.engine = db_engine
        self.pairs = list(YAHOO_SYMBOL_MAP.keys())

    # ══════════════════════════════════════════════════════════════════════════
    #  PRICE DATA COLLECTION (Yahoo Finance direct API)
    # ══════════════════════════════════════════════════════════════════════════

    def collect_prices(self, pairs: List[str] = None, timeframes: List[str] = None):
        """
        Collect OHLCV price data from Yahoo Finance v8 API (direct calls).
        D1/W1: up to 10 years, H1/H4: ~2 years.
        """
        pairs = pairs or self.pairs
        timeframes = timeframes or ['D1', 'W1', 'H4', 'H1']
        total_inserted = 0

        for pair in pairs:
            for tf in timeframes:
                cfg = TIMEFRAME_CONFIG.get(tf)
                if not cfg:
                    logger.warning(f"Unknown timeframe: {tf}")
                    continue

                start_time = time.time()
                self._log_collection('started', 'prices', pair=pair, timeframe=tf)

                try:
                    logger.info(f"Fetching {pair} {tf} from Yahoo Finance...")
                    symbol = YAHOO_SYMBOL_MAP.get(pair, pair)

                    df = self._fetch_yahoo_direct(symbol, cfg)

                    # Gold fallback
                    if df is None and pair == 'XAUUSD':
                        logger.info("XAUUSD=X empty, trying GC=F (gold futures)")
                        df = self._fetch_yahoo_direct('GC=F', cfg)

                    if df is None or len(df) == 0:
                        logger.warning(f"No data returned for {pair} {tf}")
                        self._log_collection('failed', 'prices', pair=pair, timeframe=tf,
                                             error='No data returned')
                        continue

                    # Resample H4 from H1
                    if cfg.get('resample'):
                        df = df.resample(cfg['resample']).agg({
                            'open': 'first', 'high': 'max',
                            'low': 'min', 'close': 'last', 'volume': 'sum'
                        }).dropna()

                    # Build row tuples
                    rows = []
                    for ts, row in df.iterrows():
                        dt = ts.to_pydatetime().replace(tzinfo=None)
                        rows.append((
                            pair, tf, dt,
                            round(float(row['open']), 5),
                            round(float(row['high']), 5),
                            round(float(row['low']), 5),
                            round(float(row['close']), 5),
                            round(float(row['volume']), 2),
                        ))

                    inserted = self._bulk_insert_prices(rows)
                    total_inserted += inserted
                    duration = int(time.time() - start_time)

                    date_from = df.index.min().date() if len(df) > 0 else None
                    date_to = df.index.max().date() if len(df) > 0 else None

                    logger.info(
                        f"  {pair} {tf}: {len(rows)} bars "
                        f"({date_from} → {date_to}), "
                        f"{inserted} new rows, {duration}s"
                    )
                    self._log_collection(
                        'completed', 'prices', pair=pair, timeframe=tf,
                        records=inserted, date_from=date_from, date_to=date_to,
                        duration=duration,
                    )

                except Exception as e:
                    logger.error(f"Failed to collect {pair} {tf}: {e}")
                    self._log_collection('failed', 'prices', pair=pair, timeframe=tf,
                                         error=str(e)[:500])

                # Delay to avoid rate limiting
                time.sleep(2)

        logger.info(f"Price collection complete. Total new rows: {total_inserted}")
        return total_inserted

    def _fetch_yahoo_direct(self, symbol: str, cfg: dict) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data using Yahoo Finance v8 chart API directly."""
        try:
            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
                f"?interval={cfg['yf_interval']}&range={cfg['yf_period']}"
            )

            resp = requests.get(url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; LSTrading/1.0)',
            })

            if resp.status_code != 200:
                logger.warning(f"Yahoo API returned HTTP {resp.status_code} for {symbol}")
                return None

            data = resp.json()
            result = data.get('chart', {}).get('result')
            if not result:
                return None

            chart = result[0]
            timestamps = chart.get('timestamp', [])
            quote = chart.get('indicators', {}).get('quote', [{}])[0]

            if not timestamps:
                return None

            df = pd.DataFrame({
                'open':   quote.get('open', []),
                'high':   quote.get('high', []),
                'low':    quote.get('low', []),
                'close':  quote.get('close', []),
                'volume': quote.get('volume', []),
            }, index=pd.to_datetime(timestamps, unit='s', utc=True))

            df = df.dropna(subset=['open', 'high', 'low', 'close'])
            df['volume'] = df['volume'].fillna(0)
            return df

        except Exception as e:
            logger.error(f"Yahoo direct fetch failed for {symbol}: {e}")
            return None

    def _bulk_insert_prices(self, rows: List[tuple]) -> int:
        """Bulk insert price rows using INSERT IGNORE (skip duplicates)."""
        if not rows:
            return 0

        sql = """INSERT IGNORE INTO historical_prices
                 (pair, timeframe, open_time, open_price, high_price,
                  low_price, close_price, volume)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"""

        inserted = 0
        chunk_size = 500

        raw_conn = self.engine.raw_connection()
        try:
            cursor = raw_conn.cursor()
            for i in range(0, len(rows), chunk_size):
                chunk = rows[i:i + chunk_size]
                cursor.executemany(sql, chunk)
                inserted += cursor.rowcount
            raw_conn.commit()
            cursor.close()
        except Exception as e:
            raw_conn.rollback()
            logger.error(f"Bulk insert failed: {e}")
            raise
        finally:
            raw_conn.close()

        return inserted

    # ══════════════════════════════════════════════════════════════════════════
    #  COT DATA COLLECTION (CFTC)
    # ══════════════════════════════════════════════════════════════════════════

    def collect_cot(self, years: int = 10):
        """
        Collect Commitment of Traders data from CFTC.
        Downloads yearly CSV archives (legacy futures-only format).
        """
        current_year = datetime.now().year
        start_year = current_year - years
        total_inserted = 0

        start_time = time.time()
        self._log_collection('started', 'cot')

        for year in range(start_year, current_year + 1):
            try:
                rows = self._download_cot_year(year)
                if rows:
                    inserted = self._bulk_insert_cot(rows)
                    total_inserted += inserted
                    logger.info(f"  COT {year}: {len(rows)} records, {inserted} new")
                else:
                    logger.info(f"  COT {year}: no matching records found")

                time.sleep(2)  # Be polite to CFTC servers

            except Exception as e:
                logger.error(f"COT {year} failed: {e}")

        duration = int(time.time() - start_time)
        logger.info(f"COT collection complete. Total new rows: {total_inserted}")
        self._log_collection(
            'completed', 'cot', records=total_inserted, duration=duration,
            date_from=f"{start_year}-01-01", date_to=f"{current_year}-12-31",
        )
        return total_inserted

    def _download_cot_year(self, year: int) -> List[tuple]:
        """Download and parse one year of COT data from CFTC."""
        current_year = datetime.now().year

        if year == current_year:
            url = f"https://www.cftc.gov/files/dea/history/deacot{year}.zip"
        else:
            url = f"https://www.cftc.gov/files/dea/history/deacot{year}.zip"

        logger.info(f"Downloading COT data: {url}")
        resp = requests.get(url, timeout=60, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; LSTrading/1.0)',
        })

        if resp.status_code != 200:
            logger.warning(f"COT download failed for {year}: HTTP {resp.status_code}")
            return []

        rows = []
        try:
            z = zipfile.ZipFile(io.BytesIO(resp.content))
            for filename in z.namelist():
                if not filename.endswith('.txt'):
                    continue

                with z.open(filename) as f:
                    content = io.TextIOWrapper(f, encoding='utf-8', errors='replace')
                    reader = csv.DictReader(content)

                    for record in reader:
                        market_name = record.get('Market and Exchange Names', '')

                        # Check if this is a currency/gold we care about
                        matched_currency = None
                        for cot_name, currency in COT_CURRENCY_MAP.items():
                            if cot_name in market_name.upper():
                                matched_currency = currency
                                break

                        if not matched_currency:
                            continue

                        # Parse the report date (YYYY-MM-DD format)
                        date_str = record.get('As of Date in Form YYYY-MM-DD', '')
                        if not date_str:
                            date_str = record.get('As of Date in Form YYMMDD', '')
                            if date_str:
                                try:
                                    report_date = datetime.strptime(date_str, '%y%m%d').date()
                                except ValueError:
                                    continue
                            else:
                                continue
                        else:
                            try:
                                report_date = datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
                            except ValueError:
                                continue

                        def safe_int(val):
                            try:
                                return int(str(val).replace(',', '').strip()) if val else 0
                            except (ValueError, AttributeError):
                                return 0

                        noncomm_long   = safe_int(record.get('Noncommercial Positions-Long (All)', '0'))
                        noncomm_short  = safe_int(record.get('Noncommercial Positions-Short (All)', '0'))
                        noncomm_spread = safe_int(record.get('Noncommercial Positions-Spreading (All)', '0'))
                        comm_long      = safe_int(record.get('Commercial Positions-Long (All)', '0'))
                        comm_short     = safe_int(record.get('Commercial Positions-Short (All)', '0'))
                        nonrep_long    = safe_int(record.get('Nonreportable Positions-Long (All)', '0'))
                        nonrep_short   = safe_int(record.get('Nonreportable Positions-Short (All)', '0'))
                        oi             = safe_int(record.get('Open Interest (All)', '0'))
                        oi_change      = safe_int(record.get('Change in Open Interest (All)', '0'))

                        rows.append((
                            report_date,
                            matched_currency,
                            market_name.strip()[:200],
                            noncomm_long,
                            noncomm_short,
                            noncomm_long - noncomm_short,   # noncomm_net
                            noncomm_spread,
                            comm_long,
                            comm_short,
                            comm_long - comm_short,         # comm_net
                            nonrep_long,
                            nonrep_short,
                            nonrep_long - nonrep_short,     # nonrep_net
                            oi,
                            oi_change,
                        ))

        except Exception as e:
            logger.error(f"COT parse error for {year}: {e}")

        return rows

    def _bulk_insert_cot(self, rows: List[tuple]) -> int:
        """Bulk insert COT rows."""
        if not rows:
            return 0

        sql = """INSERT IGNORE INTO cot_data
                 (report_date, currency, contract_name,
                  noncomm_long, noncomm_short, noncomm_net, noncomm_spreading,
                  comm_long, comm_short, comm_net,
                  nonrep_long, nonrep_short, nonrep_net,
                  open_interest, oi_change)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""

        inserted = 0
        raw_conn = self.engine.raw_connection()
        try:
            cursor = raw_conn.cursor()
            cursor.executemany(sql, rows)
            inserted = cursor.rowcount
            raw_conn.commit()
            cursor.close()
        except Exception as e:
            raw_conn.rollback()
            logger.error(f"COT bulk insert failed: {e}")
        finally:
            raw_conn.close()

        return inserted

    # ══════════════════════════════════════════════════════════════════════════
    #  INTEREST RATE COLLECTION (FRED API)
    # ══════════════════════════════════════════════════════════════════════════

    def collect_interest_rates(self, fred_api_key: str = None):
        """
        Collect central bank interest rate history from FRED.
        Requires free API key from https://fred.stlouisfed.org/docs/api/api_key.html
        If no key, tries to get from env var FRED_API_KEY.
        """
        api_key = fred_api_key or os.getenv('FRED_API_KEY', '')
        if not api_key:
            logger.warning(
                "FRED_API_KEY not set — skipping interest rate collection. "
                "Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html"
            )
            return 0

        start_time = time.time()
        self._log_collection('started', 'rates')
        total_inserted = 0

        ten_years_ago = (datetime.now() - timedelta(days=3650)).strftime('%Y-%m-%d')
        today = datetime.now().strftime('%Y-%m-%d')

        for currency, info in FRED_SERIES.items():
            try:
                url = (
                    f"https://api.stlouisfed.org/fred/series/observations"
                    f"?series_id={info['series']}"
                    f"&api_key={api_key}"
                    f"&file_type=json"
                    f"&observation_start={ten_years_ago}"
                    f"&observation_end={today}"
                    f"&frequency=m"
                )

                resp = requests.get(url, timeout=30)
                if resp.status_code != 200:
                    logger.warning(f"FRED failed for {currency}: HTTP {resp.status_code}")
                    continue

                data = resp.json()
                observations = data.get('observations', [])

                rows = []
                prev_rate = None
                for obs in observations:
                    rate_str = obs.get('value', '.')
                    if rate_str == '.' or not rate_str:
                        continue

                    rate_date = obs.get('date', '')
                    try:
                        rate_val = float(rate_str)
                        change = round(rate_val - prev_rate, 3) if prev_rate is not None else 0
                        prev_rate = rate_val

                        rows.append((
                            rate_date,
                            currency,
                            info['bank'],
                            rate_val,
                            change,
                        ))
                    except ValueError:
                        continue

                if rows:
                    inserted = self._bulk_insert_rates(rows)
                    total_inserted += inserted
                    logger.info(f"  Rates {currency} ({info['bank']}): {len(rows)} records, {inserted} new")

                time.sleep(0.5)  # FRED rate limit

            except Exception as e:
                logger.error(f"Interest rate collection failed for {currency}: {e}")

        duration = int(time.time() - start_time)
        logger.info(f"Interest rate collection complete. Total new rows: {total_inserted}")
        self._log_collection('completed', 'rates', records=total_inserted, duration=duration)
        return total_inserted

    def _bulk_insert_rates(self, rows: List[tuple]) -> int:
        """Bulk insert interest rate rows."""
        if not rows:
            return 0

        sql = """INSERT IGNORE INTO interest_rates
                 (rate_date, currency, central_bank, rate_value, rate_change)
                 VALUES (%s, %s, %s, %s, %s)"""

        inserted = 0
        raw_conn = self.engine.raw_connection()
        try:
            cursor = raw_conn.cursor()
            cursor.executemany(sql, rows)
            inserted = cursor.rowcount
            raw_conn.commit()
            cursor.close()
        except Exception as e:
            raw_conn.rollback()
            logger.error(f"Rates bulk insert failed: {e}")
        finally:
            raw_conn.close()

        return inserted

    # ══════════════════════════════════════════════════════════════════════════
    #  COLLECTION STATUS & LOGGING
    # ══════════════════════════════════════════════════════════════════════════

    def get_status(self) -> Dict:
        """Get collection status — counts and date ranges per data type."""
        from sqlalchemy import text

        status = {'prices': {}, 'cot': {}, 'rates': {}}

        with self.engine.connect() as conn:
            # Price data status
            rows = conn.execute(text(
                """SELECT pair, timeframe,
                          COUNT(*) as bar_count,
                          MIN(open_time) as date_from,
                          MAX(open_time) as date_to
                   FROM historical_prices
                   GROUP BY pair, timeframe
                   ORDER BY pair, timeframe"""
            ))
            for r in rows:
                key = f"{r[0]}_{r[1]}"
                status['prices'][key] = {
                    'pair': r[0], 'timeframe': r[1],
                    'bars': r[2],
                    'from': str(r[3]) if r[3] else None,
                    'to': str(r[4]) if r[4] else None,
                }

            # COT data status
            rows = conn.execute(text(
                """SELECT currency,
                          COUNT(*) as records,
                          MIN(report_date) as date_from,
                          MAX(report_date) as date_to
                   FROM cot_data
                   GROUP BY currency ORDER BY currency"""
            ))
            for r in rows:
                status['cot'][r[0]] = {
                    'records': r[1],
                    'from': str(r[2]) if r[2] else None,
                    'to': str(r[3]) if r[3] else None,
                }

            # Interest rate status
            rows = conn.execute(text(
                """SELECT currency, central_bank,
                          COUNT(*) as records,
                          MIN(rate_date) as date_from,
                          MAX(rate_date) as date_to
                   FROM interest_rates
                   GROUP BY currency, central_bank ORDER BY currency"""
            ))
            for r in rows:
                status['rates'][r[0]] = {
                    'bank': r[1], 'records': r[2],
                    'from': str(r[3]) if r[3] else None,
                    'to': str(r[4]) if r[4] else None,
                }

        return status

    def _log_collection(self, status, data_type, pair=None, timeframe=None,
                        records=0, date_from=None, date_to=None,
                        error=None, duration=0):
        """Log a collection event to data_collection_log table."""
        sql = """INSERT INTO data_collection_log
                 (data_type, pair, timeframe, status, records_count,
                  date_from, date_to, error_message, duration_sec)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""

        raw_conn = self.engine.raw_connection()
        try:
            cursor = raw_conn.cursor()
            cursor.execute(sql, (
                data_type, pair, timeframe, status, records,
                str(date_from) if date_from else None,
                str(date_to) if date_to else None,
                error, duration,
            ))
            raw_conn.commit()
            cursor.close()
        except Exception as e:
            raw_conn.rollback()
            logger.debug(f"Collection log write failed: {e}")
        finally:
            raw_conn.close()

    # ══════════════════════════════════════════════════════════════════════════
    #  COLLECT ALL
    # ══════════════════════════════════════════════════════════════════════════

    def collect_all(self, pairs: List[str] = None, timeframes: List[str] = None):
        """Run all collectors."""
        logger.info("=" * 60)
        logger.info("  HISTORICAL DATA COLLECTION — Starting")
        logger.info("=" * 60)

        grand_start = time.time()

        # 1. Price data
        logger.info("\n[1/3] Collecting Price Data (yfinance)...")
        price_count = self.collect_prices(pairs=pairs, timeframes=timeframes)

        # 2. COT data
        logger.info("\n[2/3] Collecting COT Data (CFTC)...")
        cot_count = self.collect_cot()

        # 3. Interest rates
        logger.info("\n[3/3] Collecting Interest Rates (FRED)...")
        rate_count = self.collect_interest_rates()

        total_duration = int(time.time() - grand_start)
        logger.info("=" * 60)
        logger.info(f"  COLLECTION COMPLETE — {total_duration}s total")
        logger.info(f"  Prices: {price_count} rows")
        logger.info(f"  COT:    {cot_count} rows")
        logger.info(f"  Rates:  {rate_count} rows")
        logger.info("=" * 60)

        return {
            'prices': price_count,
            'cot': cot_count,
            'rates': rate_count,
            'duration': total_duration,
        }
