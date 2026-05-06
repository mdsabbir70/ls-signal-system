"""
LS Trading Signal System — Main Bot Entry Point
signal.lstrading.xyz

Runs two concurrent tasks:
  1. Signal Engine loop  — checks for new signals every 5 minutes
  2. Flask API server    — serves the PHP admin panel

Usage:
    cd signal-bot
    python main.py              # Run bot + API
    python main.py --api-only   # API only (no trading)
    python main.py --bot-only   # Bot only (no API)
"""

import asyncio
import argparse
import sys
import os
import signal as os_signal
from datetime import datetime, timedelta, timezone

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
load_dotenv()

from utils.logger import setup_logger
from utils.database import db
from utils.config import config

logger = setup_logger('main')

# ─── Graceful shutdown ────────────────────────────────────────────────────────

_shutdown: asyncio.Event = None  # Created inside async context

def _handle_shutdown(signum, frame):
    logger.info(f"Shutdown signal received ({signum})")
    if _shutdown:
        _shutdown.set()


# ─── Signal Engine Loop ───────────────────────────────────────────────────────

async def run_signal_engine():
    """Main trading loop — runs every 5 minutes."""
    from signals.signal_engine import SignalEngine

    engine = SignalEngine(db, config)
    await engine.initialize()

    logger.info("Signal engine started")

    while not _shutdown.is_set():
        try:
            if not config.bot_active:
                logger.debug("Bot is inactive (bot_active=false in settings)")
                await asyncio.sleep(60)
                continue

            # Reload config from DB (picks up admin panel changes)
            config.refresh()

            # Check trading hours
            if not _is_trading_hours():
                logger.debug("Outside trading hours — sleeping")
                await asyncio.sleep(60)
                continue

            # Run signal engine cycle
            await engine.run_cycle()

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Signal engine error: {e}", exc_info=True)
            db.log('error', 'signal_engine', str(e))
            await asyncio.sleep(30)  # Brief pause before retry

        # Wait 5 minutes between cycles
        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=300)
        except asyncio.TimeoutError:
            pass  # Normal — just means no shutdown requested

    logger.info("Signal engine stopped")


def _is_trading_hours() -> bool:
    """Check if current UTC time is within configured trading hours."""
    from datetime import timezone
    import pytz

    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.isoweekday()  # Mon=1 ... Sun=7

    active_days = config.active_days
    if weekday not in active_days:
        return False

    start_str = config.trading_start_utc  # e.g. "08:00"
    end_str   = config.trading_end_utc    # e.g. "22:00"

    try:
        start_h, start_m = map(int, start_str.split(':'))
        end_h,   end_m   = map(int, end_str.split(':'))
        start_mins = start_h * 60 + start_m
        end_mins   = end_h   * 60 + end_m
        now_mins   = now_utc.hour * 60 + now_utc.minute

        if end_mins >= start_mins:
            # Normal: e.g. 08:00–22:00
            return start_mins <= now_mins <= end_mins
        else:
            # Overnight: e.g. 22:00–06:00
            return now_mins >= start_mins or now_mins <= end_mins
    except Exception:
        return True  # Default: allow trading if config is malformed


# ─── Flask API (thread-based) ─────────────────────────────────────────────────

async def run_flask_api():
    """Run Flask API in a separate thread (non-blocking)."""
    import threading
    from api.app import create_app

    app = create_app(db, config)
    host = config.FLASK_HOST
    port = config.FLASK_PORT

    def _run():
        logger.info(f"Flask API listening on http://{host}:{port}")
        app.run(host=host, port=port, debug=False, use_reloader=False)

    thread = threading.Thread(target=_run, daemon=True, name='flask-api')
    thread.start()
    logger.info("Flask API thread started")

    # Keep alive until shutdown
    while not _shutdown.is_set():
        await asyncio.sleep(5)


# ─── Independent News Fetcher Loop ──────────────────────────────────────────

async def run_news_fetcher():
    """Fetch news every 15 minutes, independent of signal engine."""
    logger.info("News fetcher loop started")

    # Wait a bit for DB to be ready
    await asyncio.sleep(10)

    news_feed = None
    try:
        from data.news_fetcher import NewsFetcher
        news_feed = NewsFetcher(db)
    except Exception as e:
        logger.error(f"News fetcher init failed: {e}")
        return

    while not _shutdown.is_set():
        try:
            items = await news_feed.fetch_latest(hours=4)
            logger.info(f"News fetcher: {len(items)} items fetched")
        except Exception as e:
            logger.error(f"News fetcher error: {e}")

        # Wait 15 minutes
        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=900)
        except asyncio.TimeoutError:
            pass

    logger.info("News fetcher loop stopped")


# ─── Signal Monitor (TP/SL Auto-Detection) ──────────────────────────────────

async def run_signal_monitor():
    """Monitor open signals every 60s — detect TP/SL hits, send close notifications."""
    from data.price_fetcher import PriceFetcher
    from notifications.telegram_notifier import TelegramNotifier

    logger.info("Signal monitor started")
    await asyncio.sleep(20)   # Wait for DB / signal engine to be ready

    fetcher  = PriceFetcher()
    notifier = None
    try:
        notifier = TelegramNotifier(config)
    except Exception as e:
        logger.warning(f"Signal monitor: Telegram not available: {e}")

    while not _shutdown.is_set():
        try:
            if config.bot_active:
                await _check_open_signals(fetcher, notifier)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Signal monitor error: {e}", exc_info=True)

        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass

    logger.info("Signal monitor stopped")


async def _check_open_signals(fetcher, notifier):
    """Check all open signals against current market prices."""
    open_signals = db.execute("SELECT * FROM signals WHERE status = 'OPEN'")
    if not open_signals:
        return

    # Group by pair to minimize price fetches
    pairs = list(set(s['pair'] for s in open_signals))
    loop  = asyncio.get_event_loop()

    prices = {}
    for pair in pairs:
        try:
            price = await loop.run_in_executor(None, fetcher.get_current_price, pair)
            if price:
                prices[pair] = price
        except Exception as e:
            logger.debug(f"Price fetch failed for {pair}: {e}")

    if not prices:
        return

    logger.debug(f"Signal monitor: checking {len(open_signals)} signals, prices for {list(prices.keys())}")

    for signal in open_signals:
        pair = signal['pair']
        if pair not in prices:
            continue

        current_price = prices[pair]
        stop_loss     = float(signal['stop_loss'])
        take_profit   = float(signal['take_profit'])
        direction     = signal['direction']

        hit = None
        if direction == 'BUY':
            if current_price >= take_profit:
                hit = 'TP'
            elif current_price <= stop_loss:
                hit = 'SL'
        else:   # SELL
            if current_price <= take_profit:
                hit = 'TP'
            elif current_price >= stop_loss:
                hit = 'SL'

        if hit:
            await _close_signal_auto(signal, current_price, hit, notifier)


async def _close_signal_auto(signal, close_price, hit_type, notifier):
    """Auto-close a signal that hit TP or SL."""
    signal_id   = signal['signal_id']
    pair        = signal['pair']
    direction   = signal['direction']
    entry_price = float(signal['entry_price'])

    status = 'CLOSED_TP' if hit_type == 'TP' else 'CLOSED_SL'

    # Calculate pips
    pip_diff = (close_price - entry_price) if direction == 'BUY' else (entry_price - close_price)

    pip_size = 0.01 if 'JPY' in pair else 0.0001
    if 'XAU' in pair:
        pip_size = 0.1

    actual_pips   = round(pip_diff / pip_size, 1)
    lot_size      = float(signal.get('suggested_lot') or 0.01)
    pip_value     = 10.0
    actual_profit = round(lot_size * actual_pips * pip_value, 2)

    # Duration
    duration_min = 0
    created_at = signal.get('created_at')
    if created_at:
        try:
            from datetime import timezone as tz
            created = datetime.fromisoformat(str(created_at).replace('Z', '+00:00'))
            if created.tzinfo is None:
                created = created.replace(tzinfo=tz.utc)
            duration_min = int((datetime.now(tz.utc) - created).total_seconds() / 60)
        except Exception:
            pass

    close_data = {
        'status':           status,
        'close_price':      close_price,
        'actual_pips':      actual_pips,
        'actual_profit':    actual_profit,
        'duration_minutes': duration_min,
        'close_reason':     f'Auto {hit_type} hit',
    }

    success = db.close_signal(signal_id, close_data)

    if success:
        icon = '✅' if hit_type == 'TP' else '🛑'
        logger.info(
            f"{icon} {pair} {direction} {status} | "
            f"Entry={entry_price:.5f} Close={close_price:.5f} "
            f"Pips={actual_pips:+.1f} P&L=${actual_profit:+.2f} "
            f"Duration={duration_min}min"
        )
        db.log('info', 'signal_monitor', f"{status}: {signal_id} {pair}", {
            'signal_id': signal_id, 'pair': pair, 'direction': direction,
            'actual_pips': actual_pips, 'actual_profit': actual_profit,
        })

        # Telegram close notification
        if notifier and config.telegram_enabled:
            try:
                await notifier.send_signal_close(signal, close_data)
            except Exception as e:
                logger.error(f"Close notification failed: {e}")


# ─── Daily Summary Scheduler ─────────────────────────────────────────────────

async def run_daily_scheduler():
    """Send daily/weekly/monthly summaries at configured UTC time."""
    from datetime import timezone, timedelta

    logger.info("Daily scheduler started")
    last_summary_date  = None
    last_weekly_sent   = None
    last_monthly_sent  = None

    while not _shutdown.is_set():
        now_utc = datetime.now(timezone.utc)
        summary_time_str = config.get('daily_summary_time_utc', '23:00')

        try:
            s_h, s_m = map(int, summary_time_str.split(':'))
            if (now_utc.hour == s_h and now_utc.minute == s_m
                    and last_summary_date != now_utc.date()):

                # Daily
                logger.info("Sending daily summary...")
                await _send_daily_summary()
                last_summary_date = now_utc.date()

                # Weekly — send on Sunday
                if now_utc.isoweekday() == 7 and last_weekly_sent != now_utc.date():
                    logger.info("Sending weekly summary...")
                    await _send_weekly_summary()
                    last_weekly_sent = now_utc.date()

                # Monthly — send on 1st of month
                if now_utc.day == 1 and last_monthly_sent != now_utc.date():
                    logger.info("Sending monthly summary...")
                    await _send_monthly_summary()
                    last_monthly_sent = now_utc.date()

        except Exception as e:
            logger.error(f"Daily scheduler error: {e}")

        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass


async def _send_daily_summary():
    """Generate and send daily stats via Telegram."""
    try:
        from notifications.telegram_notifier import TelegramNotifier
        notifier = TelegramNotifier(config)

        today = datetime.utcnow().date()
        stats = db.execute_one(
            "SELECT * FROM daily_stats WHERE stat_date = :p0", (str(today),)
        )

        if not stats:
            stats = _calculate_daily_stats(today)

        await notifier.send_daily_summary(stats)
    except Exception as e:
        logger.error(f"Daily summary failed: {e}")


async def _send_weekly_summary():
    """Generate and send weekly stats via Telegram."""
    try:
        from notifications.telegram_notifier import TelegramNotifier
        from datetime import timezone, timedelta
        notifier = TelegramNotifier(config)

        today = datetime.now(timezone.utc).date()
        week_start = today - timedelta(days=6)   # Last 7 days

        stats = _calculate_period_stats(week_start, today)
        stats['week_start'] = str(week_start)
        stats['week_end']   = str(today)

        await notifier.send_weekly_summary(stats)
        logger.info(f"Weekly summary sent: {stats['total_signals']} signals, {stats['net_pips']:+.0f} pips")
    except Exception as e:
        logger.error(f"Weekly summary failed: {e}")


async def _send_monthly_summary():
    """Generate and send previous month stats via Telegram."""
    try:
        from notifications.telegram_notifier import TelegramNotifier
        from datetime import timezone, timedelta
        import calendar
        notifier = TelegramNotifier(config)

        today = datetime.now(timezone.utc).date()
        # Previous month
        if today.month == 1:
            month_start = today.replace(year=today.year - 1, month=12, day=1)
        else:
            month_start = today.replace(month=today.month - 1, day=1)
        last_day = calendar.monthrange(month_start.year, month_start.month)[1]
        month_end = month_start.replace(day=last_day)

        stats = _calculate_period_stats(month_start, month_end)
        stats['month_label'] = month_start.strftime('%B %Y')

        await notifier.send_monthly_summary(stats)
        logger.info(f"Monthly summary sent: {stats['month_label']} — {stats['total_signals']} signals")
    except Exception as e:
        logger.error(f"Monthly summary failed: {e}")


def _calculate_period_stats(start_date, end_date) -> dict:
    """Calculate stats for a date range from signals table."""
    rows = db.execute(
        "SELECT * FROM signals WHERE DATE(created_at) >= :p0 AND DATE(created_at) <= :p1 AND status != 'CANCELLED'",
        (str(start_date), str(end_date))
    )

    total     = len(rows)
    tp_hits   = sum(1 for r in rows if r['status'] == 'CLOSED_TP')
    sl_hits   = sum(1 for r in rows if r['status'] == 'CLOSED_SL')
    open_c    = sum(1 for r in rows if r['status'] == 'OPEN')
    win_rate  = (tp_hits / (tp_hits + sl_hits) * 100) if (tp_hits + sl_hits) > 0 else 0

    pips_won  = sum(float(r.get('actual_pips') or 0) for r in rows if r['status'] == 'CLOSED_TP')
    pips_lost = sum(abs(float(r.get('actual_pips') or 0)) for r in rows if r['status'] == 'CLOSED_SL')
    net_pips  = pips_won - pips_lost

    profit = sum(float(r.get('actual_profit') or 0) for r in rows if float(r.get('actual_profit') or 0) > 0)
    loss   = sum(abs(float(r.get('actual_profit') or 0)) for r in rows if float(r.get('actual_profit') or 0) < 0)
    net_pnl = profit - loss
    pf = (profit / loss) if loss > 0 else 0

    # Best/worst pair by net pips
    pair_pips = {}
    for r in rows:
        if r['status'] in ('CLOSED_TP', 'CLOSED_SL'):
            p = r['pair']
            pair_pips[p] = pair_pips.get(p, 0) + float(r.get('actual_pips') or 0)

    best_pair  = max(pair_pips, key=pair_pips.get) if pair_pips else 'N/A'
    worst_pair = min(pair_pips, key=pair_pips.get) if pair_pips else 'N/A'

    if best_pair != 'N/A':
        best_pair  = f"{best_pair} ({pair_pips[best_pair]:+.0f} pips)"
        worst_pair = f"{worst_pair} ({pair_pips[worst_pair]:+.0f} pips)"

    # Trading days
    trading_days = len(set(str(r.get('created_at', ''))[:10] for r in rows if r.get('created_at')))

    return {
        'total_signals':   total,
        'closed_tp':       tp_hits,
        'closed_sl':       sl_hits,
        'still_open':      open_c,
        'win_rate':        round(win_rate, 1),
        'total_pips_won':  round(pips_won, 1),
        'total_pips_lost': round(pips_lost, 1),
        'net_pips':        round(net_pips, 1),
        'total_profit':    round(profit, 2),
        'total_loss':      round(loss, 2),
        'net_pnl':         round(net_pnl, 2),
        'profit_factor':   round(pf, 2),
        'best_pair':       best_pair,
        'worst_pair':      worst_pair,
        'trading_days':    trading_days,
    }


def _calculate_daily_stats(date) -> dict:
    """Calculate and save daily stats for a given date."""
    rows = db.execute(
        "SELECT * FROM signals WHERE DATE(created_at) = :p0", (str(date),)
    )

    total   = len(rows)
    tp_hits = sum(1 for r in rows if r['status'] == 'CLOSED_TP')
    sl_hits = sum(1 for r in rows if r['status'] == 'CLOSED_SL')
    open_c  = sum(1 for r in rows if r['status'] == 'OPEN')
    cancelled = sum(1 for r in rows if r['status'] == 'CANCELLED')
    win_rate = (tp_hits / total * 100) if total > 0 else 0

    pips_won  = sum(float(r.get('actual_pips') or 0) for r in rows if r['status'] == 'CLOSED_TP')
    pips_lost = sum(abs(float(r.get('actual_pips') or 0)) for r in rows if r['status'] == 'CLOSED_SL')
    net_pips  = pips_won - pips_lost

    profit = sum(float(r.get('actual_profit') or 0) for r in rows if float(r.get('actual_profit') or 0) > 0)
    loss   = sum(abs(float(r.get('actual_profit') or 0)) for r in rows if float(r.get('actual_profit') or 0) < 0)
    net_pnl = profit - loss
    pf = (profit / loss) if loss > 0 else 0

    stats = {
        'stat_date': str(date), 'total_signals': total, 'closed_tp': tp_hits,
        'closed_sl': sl_hits, 'still_open': open_c, 'cancelled': cancelled,
        'win_rate': round(win_rate, 2), 'total_pips_won': round(pips_won, 1),
        'total_pips_lost': round(pips_lost, 1), 'net_pips': round(net_pips, 1),
        'total_profit': round(profit, 2), 'total_loss': round(loss, 2),
        'net_pnl': round(net_pnl, 2), 'profit_factor': round(pf, 2),
    }

    try:
        db.execute_write(
            """INSERT INTO daily_stats
               (stat_date,total_signals,closed_tp,closed_sl,still_open,cancelled,
                win_rate,total_pips_won,total_pips_lost,net_pips,
                total_profit,total_loss,net_pnl,profit_factor)
               VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8,:p9,:p10,:p11,:p12,:p13)
               ON DUPLICATE KEY UPDATE
               total_signals=:p1, closed_tp=:p2, closed_sl=:p3, still_open=:p4,
               cancelled=:p5, win_rate=:p6, total_pips_won=:p7, total_pips_lost=:p8,
               net_pips=:p9, total_profit=:p10, total_loss=:p11, net_pnl=:p12,
               profit_factor=:p13""",
            tuple(stats.values())
        )
    except Exception as e:
        logger.error(f"Failed to save daily stats: {e}")

    return stats


# ─── Startup ──────────────────────────────────────────────────────────────────

async def startup():
    """Connect to DB and initialize config."""
    logger.info("=" * 60)
    logger.info(" LS Trading Signal System")
    logger.info(f" signal.lstrading.xyz")
    BDT = datetime.now(timezone.utc) + timedelta(hours=6)
    logger.info(f" Starting at {BDT.strftime('%d %b %Y, %I:%M:%S %p')} BDT")
    logger.info("=" * 60)

    # Connect DB
    db.connect(
        host     = config.DB_HOST,
        port     = config.DB_PORT,
        dbname   = config.DB_NAME,
        user     = config.DB_USER,
        password = config.DB_PASSWORD,
        pool_size= config.DB_POOL_SIZE,
    )

    # Load settings from DB
    config.init_db(db)

    logger.info(f"Bot active:     {config.bot_active}")
    logger.info(f"Trading mode:   {config.trading_mode}")
    logger.info(f"Min confluence: {config.min_confluence_score}")
    logger.info(f"Active pairs:   {db.get_active_pairs()}")


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main(run_bot: bool = True, run_api: bool = True):
    """Start all async tasks."""
    global _shutdown
    _shutdown = asyncio.Event()  # Must be created inside the running event loop

    await startup()

    # Register shutdown signals
    for sig in (os_signal.SIGINT, os_signal.SIGTERM):
        os_signal.signal(sig, _handle_shutdown)

    tasks = []
    if run_api:
        tasks.append(asyncio.create_task(run_flask_api(),   name='flask-api'))
    if run_bot:
        tasks.append(asyncio.create_task(run_signal_engine(), name='signal-engine'))
        tasks.append(asyncio.create_task(run_daily_scheduler(), name='daily-scheduler'))
        tasks.append(asyncio.create_task(run_news_fetcher(), name='news-fetcher'))
        tasks.append(asyncio.create_task(run_signal_monitor(), name='signal-monitor'))

    if not tasks:
        logger.error("Nothing to run — specify --bot-only or --api-only or both")
        return

    logger.info(f"Running tasks: {[t.get_name() for t in tasks]}")

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Shutting down...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Shutdown complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='LS Trading Signal System')
    parser.add_argument('--api-only', action='store_true', help='Run API server only')
    parser.add_argument('--bot-only', action='store_true', help='Run signal bot only')
    args = parser.parse_args()

    run_bot = not args.api_only
    run_api = not args.bot_only

    asyncio.run(main(run_bot=run_bot, run_api=run_api))
