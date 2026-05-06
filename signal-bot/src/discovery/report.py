"""
Report Generator — formats discovery results for console and file output.
"""

import json
import csv
import os
from datetime import datetime
from discovery.fast_backtest import BacktestMetrics


def print_results(results: list[dict], min_win_rate: float = 60.0, top_n: int = 30):
    """Print top strategies that meet the win rate threshold."""
    winners = [r for r in results if r['win_rate'] >= min_win_rate and r['total_trades'] >= 5]
    winners.sort(key=lambda x: (-x['win_rate'], -x['profit_factor']))

    # Also find profitable winners (WR + positive pips + PF > 1)
    profitable = [
        r for r in results
        if r['win_rate'] >= min_win_rate
        and r['total_trades'] >= 5
        and r['total_pips'] > 0
        and r['profit_factor'] > 1.0
    ]
    profitable.sort(key=lambda x: (-x['profit_factor'], -x['win_rate']))

    total_tested = len(results)
    total_winners = len(winners)

    print("\n" + "=" * 105)
    print(f"  STRATEGY DISCOVERY RESULTS")
    print(f"  Tested: {total_tested} | WR>={min_win_rate}%: {total_winners} | Profitable (WR + PF>1 + pips>0): {len(profitable)}")
    print("=" * 105)

    # ── Section 1: TOP PROFITABLE (most important) ───────────────────────
    if profitable:
        print(f"\n  ** TOP PROFITABLE STRATEGIES (WR>={min_win_rate}% AND Positive Pips AND PF>1) **\n")
        print(f"{'#':<4} {'Strategy':<50} {'TF':<4} {'Tr':<5} {'Win%':<6} "
              f"{'Pips':<9} {'PF':<6} {'Sharpe':<7} {'DD':<7}")
        print("-" * 105)

        for i, r in enumerate(profitable[:top_n], 1):
            print(f"{i:<4} {r['strategy']:<50} {r['timeframe']:<4} {r['total_trades']:<5} "
                  f"{r['win_rate']:<6.1f} {r['total_pips']:>+8.1f} {r['profit_factor']:<6.2f} "
                  f"{r['sharpe']:<7.2f} {r['max_dd']:<7.1f}")

        if len(profitable) > top_n:
            print(f"\n  ... and {len(profitable) - top_n} more profitable strategies")
    else:
        print(f"\n  No profitable strategies found with {min_win_rate}%+ win rate.")
        print("  Try lowering --min-wr or testing different timeframes.\n")

    # ── Section 2: BY WIN RATE (for reference) ───────────────────────────
    if winners and len(winners) != len(profitable):
        print(f"\n  -- ALL STRATEGIES WITH {min_win_rate}%+ WIN RATE (top 15) --\n")
        print(f"{'#':<4} {'Strategy':<50} {'TF':<4} {'Tr':<5} {'Win%':<6} "
              f"{'Pips':<9} {'PF':<6}")
        print("-" * 90)
        for i, r in enumerate(winners[:15], 1):
            print(f"{i:<4} {r['strategy']:<50} {r['timeframe']:<4} {r['total_trades']:<5} "
                  f"{r['win_rate']:<6.1f} {r['total_pips']:>+8.1f} {r['profit_factor']:<6.2f}")

    # ── Category breakdown ───────────────────────────────────────────────
    if profitable:
        print(f"\n{'-' * 60}")
        print("  Profitable winners by category:")
        cats = {}
        for r in profitable:
            cat = r.get('category', 'unknown')
            cats[cat] = cats.get(cat, 0) + 1
        for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
            print(f"    {cat:<20} : {count}")

    print()


def save_results(results: list[dict], pair: str, output_dir: str = '.'):
    """Save all results to JSON and CSV files."""
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    base = f"discovery_{pair}_{ts}"

    # JSON
    json_path = os.path.join(output_dir, f"{base}.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    # CSV
    csv_path = os.path.join(output_dir, f"{base}.csv")
    fields = [
        'strategy', 'category', 'timeframe', 'pair',
        'total_trades', 'wins', 'losses', 'win_rate',
        'total_pips', 'avg_pips', 'profit_factor',
        'sharpe', 'max_dd', 'best_trade', 'worst_trade', 'avg_hold_bars',
    ]
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in results:
            w.writerow(r)

    print(f"  Results saved:")
    print(f"    JSON: {json_path}")
    print(f"    CSV:  {csv_path}")

    return json_path, csv_path


def format_summary(results: list[dict], min_win_rate: float = 60.0) -> str:
    """Return a compact text summary (e.g. for Telegram)."""
    profitable = [
        r for r in results
        if r['win_rate'] >= min_win_rate
        and r['total_trades'] >= 5
        and r['total_pips'] > 0
        and r['profit_factor'] > 1.0
    ]
    profitable.sort(key=lambda x: (-x['profit_factor'], -x['win_rate']))

    lines = [
        f"[DISCOVERY] Strategy Discovery Complete",
        f"Tested: {len(results)} | Profitable winners: {len(profitable)}",
        "",
    ]

    for i, r in enumerate(profitable[:20], 1):
        lines.append(
            f"{i}. {r['strategy']} [{r['timeframe']}] "
            f"WR:{r['win_rate']:.0f}% | {r['total_pips']:+.0f} pips | "
            f"PF:{r['profit_factor']:.1f} | {r['total_trades']} trades"
        )

    if not profitable:
        lines.append("No profitable strategies found.")

    return "\n".join(lines)
