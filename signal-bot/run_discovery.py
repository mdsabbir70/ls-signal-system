#!/usr/bin/env python3
"""
Strategy Discovery Bot — CLI Entry Point

Usage:
  python run_discovery.py EURUSD
  python run_discovery.py EURUSD --tf H1 H4 D1
  python run_discovery.py BTCUSDT --tf M15 H1 --min-wr 55
  python run_discovery.py EURUSD --all-tf

Examples:
  # Quick scan (H1 only)
  python run_discovery.py EURUSD --tf H1

  # Full scan (all timeframes)
  python run_discovery.py EURUSD --all-tf

  # Lower win-rate threshold (find more strategies)
  python run_discovery.py GBPUSD --min-wr 55

  # Multiple pairs (run one at a time)
  python run_discovery.py EURUSD --all-tf
  python run_discovery.py GBPUSD --all-tf
"""

import os
import sys
import argparse

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from discovery.discovery_engine import DiscoveryEngine


ALL_TIMEFRAMES = ['M5', 'M15', 'M30', 'H1', 'H4', 'D1']
DEFAULT_TIMEFRAMES = ['M15', 'H1', 'H4', 'D1']


def main():
    parser = argparse.ArgumentParser(
        description='Strategy Discovery Bot — find profitable trading strategies automatically',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Supported pairs:
  Forex:  EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD, NZDUSD, XAUUSD,
          EURJPY, GBPJPY, AUDJPY, EURGBP
  Crypto: BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT, DOGEUSDT, ADAUSDT,
          LINKUSDT, DOTUSDT

Timeframes: M5, M15, M30, H1, H4, D1
  M5/M15/M30: ~60 days data (Yahoo Finance limit)
  H1/H4:      ~2 years data
  D1:          ~10 years data
        """,
    )
    parser.add_argument('pair', type=str, help='Trading pair (e.g. EURUSD, BTCUSDT)')
    parser.add_argument('--tf', nargs='+', default=None,
                        help=f'Timeframes to test (default: {" ".join(DEFAULT_TIMEFRAMES)})')
    parser.add_argument('--all-tf', action='store_true',
                        help='Test all timeframes (M5 M15 M30 H1 H4 D1)')
    parser.add_argument('--min-wr', type=float, default=60.0,
                        help='Minimum win rate %% to report (default: 60)')
    parser.add_argument('--min-trades', type=int, default=5,
                        help='Minimum trades required (default: 5)')
    parser.add_argument('--output', type=str, default='.',
                        help='Output directory for results files (default: current dir)')

    args = parser.parse_args()

    # Determine timeframes
    if args.all_tf:
        timeframes = ALL_TIMEFRAMES
    elif args.tf:
        timeframes = [t.upper() for t in args.tf]
    else:
        timeframes = DEFAULT_TIMEFRAMES

    # Validate timeframes
    for tf in timeframes:
        if tf not in ALL_TIMEFRAMES:
            print(f"Error: Invalid timeframe '{tf}'. Valid: {', '.join(ALL_TIMEFRAMES)}")
            sys.exit(1)

    # Create output directory
    os.makedirs(args.output, exist_ok=True)

    # Run discovery
    engine = DiscoveryEngine(
        pair=args.pair,
        timeframes=timeframes,
        min_win_rate=args.min_wr,
        min_trades=args.min_trades,
        output_dir=args.output,
    )

    results = engine.run()

    # Final summary
    winners = [r for r in results if r['win_rate'] >= args.min_wr and r['total_trades'] >= args.min_trades]
    print(f"\n  DONE! Found {len(winners)} strategies with {args.min_wr}%+ win rate.")

    if winners:
        best = max(winners, key=lambda x: (x['win_rate'], x['profit_factor']))
        print(f"\n  BEST STRATEGY:")
        print(f"    {best['strategy']}")
        print(f"    Timeframe: {best['timeframe']}")
        print(f"    Win Rate:  {best['win_rate']}%")
        print(f"    Trades:    {best['total_trades']}")
        print(f"    Pips:      {best['total_pips']:+.1f}")
        print(f"    PF:        {best['profit_factor']}")
        print(f"    Sharpe:    {best['sharpe']}")
    print()


if __name__ == '__main__':
    main()
