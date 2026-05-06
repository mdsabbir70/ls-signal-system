#!/usr/bin/env python3
"""
LS Trading Signal System — Historical Data Collector CLI

Collects up to 10 years of historical data for backtesting & analysis.

Usage:
    python collect_historical.py                    # Collect everything
    python collect_historical.py --prices           # Price data only
    python collect_historical.py --cot              # COT data only
    python collect_historical.py --rates            # Interest rates only
    python collect_historical.py --pair EURUSD      # Specific pair (prices)
    python collect_historical.py --tf D1 W1         # Specific timeframes
    python collect_historical.py --status           # Show collection status
"""

import argparse
import sys
import os
import json

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
load_dotenv()

from utils.logger import setup_logger
from utils.database import db
from utils.config import Config

logger = setup_logger('collect_cli')


def connect_db():
    """Connect to the database."""
    db.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        dbname=Config.DB_NAME,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        pool_size=3,
    )


def create_tables():
    """Create historical data tables if they don't exist."""
    migration_sql = """
    CREATE TABLE IF NOT EXISTS historical_prices (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        pair VARCHAR(20) NOT NULL,
        timeframe VARCHAR(5) NOT NULL,
        open_time DATETIME NOT NULL,
        open_price DECIMAL(15,5) NOT NULL,
        high_price DECIMAL(15,5) NOT NULL,
        low_price DECIMAL(15,5) NOT NULL,
        close_price DECIMAL(15,5) NOT NULL,
        volume DECIMAL(20,2) DEFAULT 0,
        UNIQUE KEY uq_pair_tf_time (pair, timeframe, open_time),
        INDEX idx_pair_tf (pair, timeframe),
        INDEX idx_open_time (open_time)
    ) ENGINE=InnoDB;

    CREATE TABLE IF NOT EXISTS cot_data (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        report_date DATE NOT NULL,
        currency VARCHAR(10) NOT NULL,
        contract_name VARCHAR(200),
        noncomm_long BIGINT DEFAULT 0,
        noncomm_short BIGINT DEFAULT 0,
        noncomm_net BIGINT DEFAULT 0,
        noncomm_spreading BIGINT DEFAULT 0,
        comm_long BIGINT DEFAULT 0,
        comm_short BIGINT DEFAULT 0,
        comm_net BIGINT DEFAULT 0,
        nonrep_long BIGINT DEFAULT 0,
        nonrep_short BIGINT DEFAULT 0,
        nonrep_net BIGINT DEFAULT 0,
        open_interest BIGINT DEFAULT 0,
        oi_change BIGINT DEFAULT 0,
        UNIQUE KEY uq_date_currency (report_date, currency),
        INDEX idx_currency (currency),
        INDEX idx_report_date (report_date)
    ) ENGINE=InnoDB;

    CREATE TABLE IF NOT EXISTS interest_rates (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        rate_date DATE NOT NULL,
        currency VARCHAR(10) NOT NULL,
        central_bank VARCHAR(50) NOT NULL,
        rate_value DECIMAL(6,3) NOT NULL,
        rate_change DECIMAL(6,3) DEFAULT 0,
        UNIQUE KEY uq_date_currency (rate_date, currency),
        INDEX idx_currency (currency),
        INDEX idx_rate_date (rate_date)
    ) ENGINE=InnoDB;

    CREATE TABLE IF NOT EXISTS data_collection_log (
        id INT AUTO_INCREMENT PRIMARY KEY,
        data_type VARCHAR(50) NOT NULL,
        pair VARCHAR(20),
        timeframe VARCHAR(5),
        status ENUM('started','completed','failed') NOT NULL,
        records_count INT DEFAULT 0,
        date_from DATE,
        date_to DATE,
        error_message TEXT,
        duration_sec INT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;

    CREATE TABLE IF NOT EXISTS backtest_results (
        id INT AUTO_INCREMENT PRIMARY KEY,
        backtest_id VARCHAR(50) UNIQUE NOT NULL,
        strategy_name VARCHAR(100),
        pair VARCHAR(20),
        timeframe VARCHAR(5),
        start_date DATE,
        end_date DATE,
        total_signals INT DEFAULT 0,
        wins INT DEFAULT 0,
        losses INT DEFAULT 0,
        win_rate DECIMAL(5,2) DEFAULT 0,
        net_pips DECIMAL(10,1) DEFAULT 0,
        net_pnl DECIMAL(10,2) DEFAULT 0,
        profit_factor DECIMAL(5,2) DEFAULT 0,
        max_drawdown DECIMAL(5,2) DEFAULT 0,
        avg_rr DECIMAL(4,2) DEFAULT 0,
        sharpe_ratio DECIMAL(6,3) DEFAULT 0,
        settings_json JSON,
        trades_json JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;
    """

    raw_conn = db.engine.raw_connection()
    try:
        cursor = raw_conn.cursor()
        for stmt in migration_sql.strip().split(';'):
            stmt = stmt.strip()
            if stmt:
                cursor.execute(stmt)
        raw_conn.commit()
        cursor.close()
        logger.info("Historical data tables verified/created")
    except Exception as e:
        raw_conn.rollback()
        logger.error(f"Table creation failed: {e}")
        raise
    finally:
        raw_conn.close()


def show_status(collector):
    """Print collection status to console."""
    status = collector.get_status()

    print("\n" + "=" * 70)
    print("  HISTORICAL DATA STATUS")
    print("=" * 70)

    # Prices
    print("\n📊 PRICE DATA (OHLCV)")
    print("-" * 70)
    if status['prices']:
        print(f"  {'Pair':<10} {'TF':<5} {'Bars':>8}   {'From':<20} {'To':<20}")
        print("  " + "-" * 65)
        for key, info in sorted(status['prices'].items()):
            print(f"  {info['pair']:<10} {info['timeframe']:<5} {info['bars']:>8}   "
                  f"{info['from'] or '—':<20} {info['to'] or '—':<20}")
    else:
        print("  No price data collected yet.")

    # COT
    print(f"\n📋 COT DATA (Commitment of Traders)")
    print("-" * 70)
    if status['cot']:
        print(f"  {'Currency':<10} {'Records':>8}   {'From':<20} {'To':<20}")
        print("  " + "-" * 55)
        for currency, info in sorted(status['cot'].items()):
            print(f"  {currency:<10} {info['records']:>8}   "
                  f"{info['from'] or '—':<20} {info['to'] or '—':<20}")
    else:
        print("  No COT data collected yet.")

    # Interest rates
    print(f"\n🏦 INTEREST RATES")
    print("-" * 70)
    if status['rates']:
        print(f"  {'Currency':<6} {'Central Bank':<30} {'Records':>8}   {'From':<12} {'To':<12}")
        print("  " + "-" * 65)
        for currency, info in sorted(status['rates'].items()):
            print(f"  {currency:<6} {info['bank']:<30} {info['records']:>8}   "
                  f"{info['from'] or '—':<12} {info['to'] or '—':<12}")
    else:
        print("  No interest rate data yet. Set FRED_API_KEY for collection.")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description='LS Trading Signal System — Historical Data Collector'
    )
    parser.add_argument('--prices', action='store_true', help='Collect price data only')
    parser.add_argument('--cot', action='store_true', help='Collect COT data only')
    parser.add_argument('--rates', action='store_true', help='Collect interest rate data only')
    parser.add_argument('--pair', type=str, nargs='+', help='Specific pairs (e.g. EURUSD GBPUSD)')
    parser.add_argument('--tf', type=str, nargs='+', help='Specific timeframes (e.g. D1 W1)')
    parser.add_argument('--status', action='store_true', help='Show collection status')
    parser.add_argument('--fred-key', type=str, help='FRED API key for interest rates')

    args = parser.parse_args()

    # Connect to DB
    connect_db()
    create_tables()

    from data.historical_collector import HistoricalCollector
    collector = HistoricalCollector(db.engine)

    # Status mode
    if args.status:
        show_status(collector)
        return

    # Determine what to collect
    collect_specific = args.prices or args.cot or args.rates

    if not collect_specific:
        # Collect everything
        result = collector.collect_all(
            pairs=args.pair,
            timeframes=args.tf,
        )
        print(f"\nCollection complete!")
        print(f"  Prices: {result['prices']} new rows")
        print(f"  COT:    {result['cot']} new rows")
        print(f"  Rates:  {result['rates']} new rows")
        print(f"  Time:   {result['duration']}s")
    else:
        if args.prices:
            count = collector.collect_prices(pairs=args.pair, timeframes=args.tf)
            print(f"\nPrice collection complete: {count} new rows")

        if args.cot:
            count = collector.collect_cot()
            print(f"\nCOT collection complete: {count} new rows")

        if args.rates:
            count = collector.collect_interest_rates(fred_api_key=args.fred_key)
            print(f"\nInterest rate collection complete: {count} new rows")

    # Show final status
    show_status(collector)


if __name__ == '__main__':
    main()
