"""
Flask REST API
Connects the PHP admin panel to the Python bot.
All endpoints require X-API-Key header.

Endpoints:
  GET  /api/status          — Bot status, today stats
  GET  /api/signals         — List signals (paginated)
  GET  /api/signals/<id>    — Signal detail
  POST /api/signals/<id>/close — Close a signal manually
  GET  /api/pairs           — List pairs and their stats
  POST /api/pairs/<symbol>/toggle — Enable/disable a pair
  GET  /api/settings        — All settings
  POST /api/settings        — Update settings
  GET  /api/news            — Recent news archive
  GET  /api/stats/daily     — Daily stats history
  POST /api/bot/toggle      — Turn bot on/off
  POST /api/backtest/run    — Start a backtest
  GET  /api/backtest/results — List backtest results
  GET  /api/backtest/<id>   — Single backtest detail
  DELETE /api/backtest/<id> — Delete a backtest result
"""

from __future__ import annotations
import asyncio
import json
import time
import threading
from functools import wraps

from flask import Flask, request, jsonify
from flask_cors import CORS

from utils.logger import setup_logger
from utils.pair_config import get_pair_config as _pair_cfg

logger = setup_logger('api')


def create_app(db, config) -> Flask:
    """Application factory."""
    app = Flask(__name__)
    app.secret_key = config.FLASK_SECRET_KEY
    CORS(app, origins=['http://localhost', 'https://signal.lstrading.xyz'])

    # ── Auth decorator ─────────────────────────────────────────────────────
    def require_api_key(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            key = request.headers.get('X-API-Key', '')
            if not key or key != config.API_KEY:
                return jsonify({'error': 'Unauthorized'}), 401
            return f(*args, **kwargs)
        return decorated

    def ok(data: dict, code: int = 200):
        return jsonify({'success': True, **data}), code

    def err(message: str, code: int = 400):
        return jsonify({'success': False, 'error': message}), code

    # ── Status ────────────────────────────────────────────────────────────

    @app.route('/api/status')
    @require_api_key
    def get_status():
        today_signals = db.get_today_signal_count()
        open_signals  = db.get_open_signal_count()
        active_pairs  = db.get_active_pairs()

        cooloff_row = db.execute_one(
            "SELECT resume_at FROM cooloff_log WHERE is_active=TRUE AND resume_at > NOW() LIMIT 1"
        )

        return ok({
            'bot_active':      config.bot_active,
            'trading_mode':    config.trading_mode,
            'today_signals':   today_signals,
            'open_signals':    open_signals,
            'active_pairs':    active_pairs,
            'max_daily':       config.max_daily_signals,
            'max_open':        config.max_open_positions,
            'in_cooloff':      cooloff_row is not None,
            'cooloff_until':   str(cooloff_row['resume_at']) if cooloff_row else None,
        })

    # ── Signals ───────────────────────────────────────────────────────────

    @app.route('/api/signals')
    @require_api_key
    def list_signals():
        page     = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        status   = request.args.get('status', None)
        pair     = request.args.get('pair', None)
        offset   = (page - 1) * per_page

        where = []
        params = []
        if status:
            where.append("status = :p" + str(len(params)))
            params.append(status)
        if pair:
            where.append("pair = :p" + str(len(params)))
            params.append(pair)

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        count_row = db.execute_one(
            f"SELECT COUNT(*) as cnt FROM signals {where_sql}",
            tuple(params)
        )
        total = count_row['cnt'] if count_row else 0

        params_paged = tuple(params) + (per_page, offset)
        rows = db.execute(
            f"SELECT * FROM signals {where_sql} ORDER BY created_at DESC LIMIT :p{len(params)} OFFSET :p{len(params)+1}",
            params_paged
        )

        return ok({
            'signals':    rows,
            'total':      total,
            'page':       page,
            'per_page':   per_page,
            'pages':      (total + per_page - 1) // per_page,
        })

    @app.route('/api/signals/<signal_id>')
    @require_api_key
    def get_signal(signal_id):
        row = db.execute_one(
            "SELECT * FROM signals WHERE signal_id = :p0", (signal_id,)
        )
        if not row:
            return err('Signal not found', 404)
        return ok({'signal': row})

    @app.route('/api/signals/<signal_id>/close', methods=['POST'])
    @require_api_key
    def close_signal(signal_id):
        data = request.get_json() or {}
        close_price = data.get('close_price')
        close_reason = data.get('reason', 'MANUAL')

        signal = db.execute_one(
            "SELECT * FROM signals WHERE signal_id = :p0 AND status='OPEN'", (signal_id,)
        )
        if not signal:
            return err('Signal not found or already closed', 404)

        if not close_price:
            return err('close_price is required')

        close_price = float(close_price)
        entry_price = float(signal['entry_price'])
        direction   = signal['direction']

        # Calculate P&L
        if direction == 'BUY':
            pip_diff = close_price - entry_price
        else:
            pip_diff = entry_price - close_price

        # Centralized pair config — single source of truth
        _pair = signal['pair']
        _cfg = _pair_cfg(_pair)
        pip_size  = _cfg['pip_size']
        pip_value = _cfg['pip_value']

        actual_pips   = round(pip_diff / pip_size, 1)
        actual_profit = round(float(signal.get('suggested_lot') or 0.01) * actual_pips * pip_value, 2)

        from datetime import datetime, timezone
        created_at = signal.get('created_at')
        duration_min = 0
        if created_at:
            try:
                created = datetime.fromisoformat(str(created_at).replace('Z', '+00:00'))
                duration_min = int((datetime.now(timezone.utc) - created).total_seconds() / 60)
            except Exception:
                pass

        status = 'CLOSED_MANUAL'
        if close_reason == 'TP':
            status = 'CLOSED_TP'
        elif close_reason == 'SL':
            status = 'CLOSED_SL'

        success = db.close_signal(signal_id, {
            'status':           status,
            'close_price':      close_price,
            'actual_pips':      actual_pips,
            'actual_profit':    actual_profit,
            'duration_minutes': duration_min,
            'close_reason':     close_reason,
        })

        if success:
            return ok({'message': 'Signal closed', 'actual_pips': actual_pips, 'actual_profit': actual_profit})
        return err('Failed to close signal')

    # ── Pairs ─────────────────────────────────────────────────────────────

    @app.route('/api/pairs')
    @require_api_key
    def list_pairs():
        rows = db.execute("SELECT * FROM pairs ORDER BY category, symbol")
        return ok({'pairs': rows})

    @app.route('/api/pairs/<symbol>/toggle', methods=['POST'])
    @require_api_key
    def toggle_pair(symbol):
        row = db.execute_one("SELECT is_active FROM pairs WHERE symbol = :p0", (symbol,))
        if not row:
            return err('Pair not found', 404)

        new_state = not row['is_active']
        db.execute_write(
            "UPDATE pairs SET is_active = :p0 WHERE symbol = :p1", (new_state, symbol)
        )
        return ok({'symbol': symbol, 'is_active': new_state})

    # ── Settings ──────────────────────────────────────────────────────────

    @app.route('/api/settings')
    @require_api_key
    def get_settings():
        rows = db.execute("SELECT * FROM settings ORDER BY category, setting_key")
        return ok({'settings': rows})

    @app.route('/api/settings', methods=['POST'])
    @require_api_key
    def update_settings():
        data = request.get_json() or {}
        updated = []
        failed  = []

        for key, value in data.items():
            if db.set_setting(key, value):
                updated.append(key)
            else:
                failed.append(key)

        # Reload config
        config.refresh()

        return ok({'updated': updated, 'failed': failed})

    # ── News ──────────────────────────────────────────────────────────────

    @app.route('/api/news')
    @require_api_key
    def list_news():
        page     = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 30))
        offset   = (page - 1) * per_page

        rows = db.execute(
            "SELECT * FROM news_archive ORDER BY published_at DESC LIMIT :p0 OFFSET :p1",
            (per_page, offset)
        )
        count_row = db.execute_one("SELECT COUNT(*) as cnt FROM news_archive")
        total = count_row['cnt'] if count_row else 0

        return ok({'news': rows, 'total': total, 'page': page, 'per_page': per_page})

    # ── Daily Stats ───────────────────────────────────────────────────────

    @app.route('/api/stats/daily')
    @require_api_key
    def daily_stats():
        days = int(request.args.get('days', 30))
        rows = db.execute(
            "SELECT * FROM daily_stats ORDER BY stat_date DESC LIMIT :p0", (days,)
        )
        return ok({'stats': rows})

    # ── Bot Toggle ────────────────────────────────────────────────────────

    @app.route('/api/bot/toggle', methods=['POST'])
    @require_api_key
    def toggle_bot():
        data = request.get_json() or {}
        active = bool(data.get('active', not config.bot_active))
        db.set_setting('bot_active', str(active).lower())
        config.refresh()
        logger.info(f"Bot {'activated' if active else 'deactivated'} via API")
        return ok({'bot_active': active})

    # ── Sentiment ─────────────────────────────────────────────────────────

    @app.route('/api/sentiment/current')
    @require_api_key
    def get_current_sentiment():
        """Get current sentiment readings (Fear & Greed + VIX + performance)."""
        try:
            from indicators.sentiment_analyzer import SentimentAnalyzer
            analyzer = SentimentAnalyzer(db)

            loop = __import__('asyncio').new_event_loop()
            # Fetch both crypto and forex sentiment
            fng_result = loop.run_until_complete(analyzer.get_sentiment('BTCUSDT', 'BUY'))
            vix_result = loop.run_until_complete(analyzer.get_sentiment('EURUSD', 'BUY'))
            loop.close()

            return ok({
                'fear_greed': {
                    'value': fng_result.fear_greed_value,
                    'label': fng_result.fear_greed_label,
                    'sentiment': fng_result.overall_sentiment,
                },
                'vix': {
                    'value': round(vix_result.vix_value, 2),
                    'label': vix_result.vix_label,
                },
                'performance': {
                    'win_rate': round(fng_result.recent_win_rate, 1),
                    'consecutive_losses': fng_result.consecutive_losses,
                    'trend': fng_result.performance_trend,
                },
            })
        except Exception as e:
            logger.error(f"Sentiment API error: {e}")
            return err(f'Sentiment fetch failed: {str(e)}')

    @app.route('/api/sentiment/history')
    @require_api_key
    def get_sentiment_history():
        """Get sentiment history from DB."""
        source = request.args.get('source', '')
        days = int(request.args.get('days', 30))

        where = "WHERE created_at >= DATE_SUB(NOW(), INTERVAL :p0 DAY)"
        params = [days]
        if source:
            where += f" AND source = :p{len(params)}"
            params.append(source)

        rows = db.execute(
            f"""SELECT source, value, label, created_at
                FROM sentiment_history {where}
                ORDER BY created_at DESC LIMIT 500""",
            tuple(params)
        )
        return ok({'history': rows})

    # ── Backtest ──────────────────────────────────────────────────────────

    # Track running backtests
    _running_backtests: dict = {}

    @app.route('/api/backtest/run', methods=['POST'])
    @require_api_key
    def run_backtest():
        data = request.get_json() or {}
        pair = data.get('pair', 'EURUSD')
        timeframe = data.get('timeframe', 'H1')
        start_date = data.get('start_date', '2024-01-01')
        end_date = data.get('end_date', '2026-05-01')
        min_score = float(data.get('min_score', 80))
        sl_atr_mult = float(data.get('sl_atr_mult', 1.5))
        tp_atr_mult = float(data.get('tp_atr_mult', 2.0))
        trading_mode = data.get('trading_mode', 'technical')

        # Validate pair
        valid_pairs = db.get_active_pairs()
        all_pairs = [r['symbol'] for r in db.execute("SELECT symbol FROM pairs")]
        if pair not in all_pairs:
            return err(f'Invalid pair: {pair}')

        # Check if a backtest is already running
        for bt_id, info in list(_running_backtests.items()):
            if info.get('status') == 'running':
                return err(f'Backtest already running: {bt_id}. Wait for it to finish.')

        # Run backtest in background thread
        import uuid
        bt_id = f"BT-{pair}-{uuid.uuid4().hex[:8]}"
        _running_backtests[bt_id] = {
            'status': 'running',
            'pair': pair,
            'timeframe': timeframe,
            'start_date': start_date,
            'end_date': end_date,
        }

        def _run_bt():
            try:
                from signals.backtester import Backtester
                bt = Backtester(db)
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(bt.run(
                    pair=pair, timeframe=timeframe,
                    start_date=start_date, end_date=end_date,
                    min_score=min_score, sl_atr_mult=sl_atr_mult,
                    tp_atr_mult=tp_atr_mult, trading_mode=trading_mode,
                ))
                loop.close()
                _running_backtests[bt_id] = {
                    'status': 'completed',
                    'backtest_id': result.backtest_id,
                    'summary': {
                        'total_signals': result.total_signals,
                        'win_rate': round(result.win_rate, 1),
                        'net_pips': round(result.net_pips, 1),
                        'profit_factor': round(result.profit_factor, 2),
                    }
                }
                logger.info(f"Backtest {bt_id} completed: WR={result.win_rate:.1f}%")
            except Exception as e:
                _running_backtests[bt_id] = {'status': 'failed', 'error': str(e)}
                logger.error(f"Backtest {bt_id} failed: {e}")

        thread = threading.Thread(target=_run_bt, daemon=True)
        thread.start()

        return ok({
            'message': 'Backtest started',
            'backtest_id': bt_id,
            'pair': pair,
            'timeframe': timeframe,
            'period': f'{start_date} to {end_date}',
        }, 202)

    @app.route('/api/backtest/status')
    @require_api_key
    def backtest_status():
        return ok({'backtests': _running_backtests})

    @app.route('/api/backtest/results')
    @require_api_key
    def list_backtests():
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        pair = request.args.get('pair', '')
        offset = (page - 1) * per_page

        where = []
        params = []
        if pair:
            where.append(f"pair = :p{len(params)}")
            params.append(pair)

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        count_row = db.execute_one(
            f"SELECT COUNT(*) as cnt FROM backtest_results {where_sql}",
            tuple(params)
        )
        total = count_row['cnt'] if count_row else 0

        params_paged = tuple(params) + (per_page, offset)
        rows = db.execute(
            f"""SELECT backtest_id, strategy_name, pair, timeframe,
                       start_date, end_date, total_signals, wins, losses,
                       win_rate, net_pips, profit_factor, max_drawdown,
                       avg_rr, sharpe_ratio, created_at
                FROM backtest_results {where_sql}
                ORDER BY created_at DESC
                LIMIT :p{len(params)} OFFSET :p{len(params)+1}""",
            params_paged
        )

        return ok({
            'results': rows,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page,
        })

    @app.route('/api/backtest/<backtest_id>')
    @require_api_key
    def get_backtest(backtest_id):
        row = db.execute_one(
            "SELECT * FROM backtest_results WHERE backtest_id = :p0",
            (backtest_id,)
        )
        if not row:
            return err('Backtest not found', 404)

        # Parse JSON fields
        if isinstance(row.get('settings_json'), str):
            try:
                row['settings_json'] = json.loads(row['settings_json'])
            except Exception:
                pass
        if isinstance(row.get('trades_json'), str):
            try:
                row['trades_json'] = json.loads(row['trades_json'])
            except Exception:
                pass

        return ok({'backtest': row})

    @app.route('/api/backtest/<backtest_id>', methods=['DELETE'])
    @require_api_key
    def delete_backtest(backtest_id):
        row = db.execute_one(
            "SELECT id FROM backtest_results WHERE backtest_id = :p0",
            (backtest_id,)
        )
        if not row:
            return err('Backtest not found', 404)
        db.execute_write(
            "DELETE FROM backtest_results WHERE backtest_id = :p0",
            (backtest_id,)
        )
        return ok({'message': f'Backtest {backtest_id} deleted'})

    # ── Strategy Discovery ───────────────────────────────────────────────

    # Track running discoveries
    _running_discoveries: dict = {}

    @app.route('/api/discovery/run', methods=['POST'])
    @require_api_key
    def run_discovery():
        data = request.get_json() or {}
        pair          = data.get('pair', 'EURUSD').upper()
        timeframes    = data.get('timeframes', ['H1', 'H4', 'D1'])
        min_wr        = float(data.get('min_win_rate', 60.0))
        min_trades    = int(data.get('min_trades', 5))
        lookback_days = int(data.get('lookback_days', 0))

        # Check if discovery already running
        for disc_id, info in list(_running_discoveries.items()):
            if info.get('status') == 'running':
                return err(f'Discovery already running ({disc_id}). Wait for it.')

        import uuid
        disc_id = f"DISC-{pair}-{uuid.uuid4().hex[:6]}"
        _running_discoveries[disc_id] = {
            'status': 'running',
            'pair': pair,
            'timeframes': timeframes,
            'min_win_rate': min_wr,
            'lookback_days': lookback_days,
            'started_at': __import__('datetime').datetime.now().isoformat(),
        }

        def _run_disc():
            import sys, os, warnings
            warnings.filterwarnings('ignore')
            src = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
            if src not in sys.path:
                sys.path.insert(0, src)
            try:
                from discovery.discovery_engine import DiscoveryEngine
                engine = DiscoveryEngine(
                    pair=pair,
                    timeframes=timeframes,
                    min_win_rate=min_wr,
                    min_trades=min_trades,
                    output_dir='/tmp',
                    lookback_days=lookback_days,
                )
                results = engine.run()

                # Filter profitable winners
                profitable = [
                    r for r in results
                    if r['win_rate'] >= min_wr
                    and r['total_trades'] >= min_trades
                    and r['total_pips'] > 0
                    and r['profit_factor'] > 1.0
                ]
                profitable.sort(key=lambda x: (-x['profit_factor'], -x['win_rate']))

                all_winners = [
                    r for r in results
                    if r['win_rate'] >= min_wr and r['total_trades'] >= min_trades
                ]

                # Best strategy summary
                best = profitable[0] if profitable else None
                best_strategy = best['strategy_name'] if best else None
                best_wr       = best['win_rate']       if best else None
                best_pips     = best['total_pips']     if best else None
                best_pf       = best['profit_factor']  if best else None

                # ── Build multi-TF map from ALL profitable (not just top 100) ──
                # key = strategy_name + '|' + params_label
                # value = sorted list of timeframes where strategy is profitable
                _mtf: dict = {}
                for r in profitable:
                    key = (r.get('strategy_name') or r.get('strategy', '')) + '|' + (r.get('params_label') or '')
                    if key not in _mtf:
                        _mtf[key] = set()
                    _mtf[key].add(r['timeframe'])
                multi_tf_map = {k: sorted(v) for k, v in _mtf.items()}

                completed_data = {
                    'status': 'completed',
                    'pair': pair,
                    'timeframes': timeframes,
                    'total_tested': len(results),
                    'total_winners': len(all_winners),
                    'total_profitable': len(profitable),
                    'results': profitable[:200],   # increased from 100 to 200
                    'all_winners': all_winners[:50],
                    'multi_tf_map': multi_tf_map,  # complete TF map from ALL profitable
                    'best_strategy': best_strategy,
                    'best_wr': best_wr,
                    'best_pips': best_pips,
                    'best_pf': best_pf,
                }
                _running_discoveries[disc_id] = completed_data

                # ── Save to DB ─────────────────────────────────────────
                try:
                    db.execute_write(
                        """INSERT INTO discovery_results
                           (discovery_id, pair, timeframes, min_win_rate, min_trades,
                            total_tested, total_winners, total_profitable,
                            best_strategy, best_wr, best_pips, best_pf, results_json)
                           VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8,:p9,:p10,:p11,:p12)
                           ON DUPLICATE KEY UPDATE
                           total_tested=VALUES(total_tested),
                           total_winners=VALUES(total_winners),
                           total_profitable=VALUES(total_profitable),
                           best_strategy=VALUES(best_strategy),
                           best_wr=VALUES(best_wr), best_pips=VALUES(best_pips),
                           best_pf=VALUES(best_pf), results_json=VALUES(results_json)""",
                        (
                            disc_id, pair, ','.join(timeframes), min_wr, min_trades,
                            len(results), len(all_winners), len(profitable),
                            best_strategy, best_wr, best_pips, best_pf,
                            json.dumps(profitable[:100], default=str),
                        )
                    )
                    logger.info(f"Discovery {disc_id} saved to DB")
                except Exception as db_err:
                    logger.error(f"Discovery DB save failed: {db_err}")

                logger.info(f"Discovery {disc_id}: {len(profitable)} profitable strategies found")
            except Exception as e:
                _running_discoveries[disc_id] = {'status': 'failed', 'error': str(e)}
                logger.error(f"Discovery {disc_id} failed: {e}")

        thread = threading.Thread(target=_run_disc, daemon=True)
        thread.start()

        return ok({
            'message': 'Discovery started',
            'discovery_id': disc_id,
            'pair': pair,
            'timeframes': timeframes,
        }, 202)

    @app.route('/api/discovery/status')
    @require_api_key
    def discovery_status():
        return ok({'discoveries': _running_discoveries})

    @app.route('/api/discovery/history')
    @require_api_key
    def discovery_history():
        rows = db.execute(
            """SELECT id, discovery_id, pair, timeframes, min_win_rate, min_trades,
                      total_tested, total_winners, total_profitable,
                      best_strategy, best_wr, best_pips, best_pf, created_at
               FROM discovery_results
               ORDER BY created_at DESC LIMIT 50"""
        )
        return ok({'history': rows})

    @app.route('/api/discovery/<discovery_id>')
    @require_api_key
    def discovery_detail(discovery_id):
        row = db.execute_one(
            "SELECT * FROM discovery_results WHERE discovery_id = :p0",
            (discovery_id,)
        )
        if not row:
            return err('Discovery result not found', 404)
        if isinstance(row.get('results_json'), str):
            try:
                row['results_json'] = json.loads(row['results_json'])
            except Exception:
                pass
        return ok({'discovery': row})

    @app.route('/api/discovery/<discovery_id>', methods=['DELETE'])
    @require_api_key
    def discovery_delete(discovery_id):
        row = db.execute_one(
            "SELECT id FROM discovery_results WHERE discovery_id = :p0",
            (discovery_id,)
        )
        if not row:
            return err('Discovery result not found', 404)
        db.execute_write(
            "DELETE FROM discovery_results WHERE discovery_id = :p0",
            (discovery_id,)
        )
        # Also remove from memory if present
        _running_discoveries.pop(discovery_id, None)
        return ok({'message': f'Deleted {discovery_id}'})

    @app.route('/api/discovery/clear', methods=['POST'])
    @require_api_key
    def discovery_clear():
        _running_discoveries.clear()
        return ok({'message': 'Cleared'})

    # ── Pattern Analysis ────────────────────────────────────────────────

    _running_patterns: dict = {}

    @app.route('/api/pattern/run', methods=['POST'])
    @require_api_key
    def run_pattern():
        data = request.get_json() or {}
        pair          = data.get('pair', 'EURUSD').upper()
        timeframes    = data.get('timeframes', ['H1', 'H4', 'D1'])
        min_wr        = float(data.get('min_win_rate', 60.0))
        min_trades    = int(data.get('min_trades', 5))
        lookback_days = int(data.get('lookback_days', 0))

        for pid, info in list(_running_patterns.items()):
            if info.get('status') == 'running':
                return err(f'Pattern analysis already running ({pid}). Wait.')

        import uuid
        pat_id = f"PAT-{pair}-{uuid.uuid4().hex[:6]}"
        _running_patterns[pat_id] = {
            'status': 'running',
            'pair': pair,
            'timeframes': timeframes,
            'min_win_rate': min_wr,
            'started_at': __import__('datetime').datetime.now().isoformat(),
        }

        def _run_pat():
            import sys, os, warnings
            warnings.filterwarnings('ignore')
            src = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
            if src not in sys.path:
                sys.path.insert(0, src)
            try:
                from patterns.pattern_engine import PatternEngine
                engine = PatternEngine(
                    pair=pair, timeframes=timeframes,
                    min_win_rate=min_wr, min_trades=min_trades,
                    output_dir='/tmp', lookback_days=lookback_days,
                )
                results = engine.run()

                profitable = [
                    r for r in results
                    if r['win_rate'] >= min_wr
                    and r['total_trades'] >= min_trades
                    and r['total_pips'] > 0
                    and r['profit_factor'] > 1.0
                ]
                profitable.sort(key=lambda x: (-x['profit_factor'], -x['win_rate']))

                all_winners = [
                    r for r in results
                    if r['win_rate'] >= min_wr and r['total_trades'] >= min_trades
                ]

                best = profitable[0] if profitable else None

                # Multi-TF map
                _mtf: dict = {}
                for r in profitable:
                    key = (r.get('strategy_name', '') + '|' + (r.get('filter_name') or ''))
                    if key not in _mtf:
                        _mtf[key] = set()
                    _mtf[key].add(r['timeframe'])
                multi_tf_map = {k: sorted(v) for k, v in _mtf.items()}

                _running_patterns[pat_id] = {
                    'status': 'completed',
                    'pair': pair,
                    'timeframes': timeframes,
                    'total_tested': len(results),
                    'total_winners': len(all_winners),
                    'total_profitable': len(profitable),
                    'results': profitable[:200],
                    'multi_tf_map': multi_tf_map,
                    'best_strategy': best['strategy_name'] if best else None,
                    'best_wr': best['win_rate'] if best else None,
                    'best_pips': best['total_pips'] if best else None,
                    'best_pf': best['profit_factor'] if best else None,
                }

                # Save to DB
                try:
                    db.execute_write(
                        """INSERT INTO pattern_results
                           (pattern_id, pair, timeframes, min_win_rate, min_trades,
                            total_tested, total_winners, total_profitable,
                            best_strategy, best_wr, best_pips, best_pf, results_json)
                           VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8,:p9,:p10,:p11,:p12)
                           ON DUPLICATE KEY UPDATE
                           total_tested=VALUES(total_tested),
                           total_winners=VALUES(total_winners),
                           total_profitable=VALUES(total_profitable),
                           best_strategy=VALUES(best_strategy),
                           best_wr=VALUES(best_wr), best_pips=VALUES(best_pips),
                           best_pf=VALUES(best_pf), results_json=VALUES(results_json)""",
                        (
                            pat_id, pair, ','.join(timeframes), min_wr, min_trades,
                            len(results), len(all_winners), len(profitable),
                            best['strategy_name'] if best else None,
                            best['win_rate'] if best else None,
                            best['total_pips'] if best else None,
                            best['profit_factor'] if best else None,
                            json.dumps(profitable[:100], default=str),
                        )
                    )
                except Exception as db_err:
                    logger.error(f"Pattern DB save failed: {db_err}")

                logger.info(f"Pattern {pat_id}: {len(profitable)} profitable found")
            except Exception as e:
                _running_patterns[pat_id] = {'status': 'failed', 'error': str(e)}
                logger.error(f"Pattern {pat_id} failed: {e}")

        thread = threading.Thread(target=_run_pat, daemon=True)
        thread.start()

        return ok({'message': 'Pattern analysis started', 'pattern_id': pat_id, 'pair': pair}, 202)

    @app.route('/api/pattern/status')
    @require_api_key
    def pattern_status():
        return ok({'patterns': _running_patterns})

    @app.route('/api/pattern/history')
    @require_api_key
    def pattern_history():
        rows = db.execute(
            """SELECT id, pattern_id, pair, timeframes, min_win_rate, min_trades,
                      total_tested, total_winners, total_profitable,
                      best_strategy, best_wr, best_pips, best_pf, created_at
               FROM pattern_results
               ORDER BY created_at DESC LIMIT 50"""
        )
        return ok({'history': rows})

    @app.route('/api/pattern/<pattern_id>', methods=['DELETE'])
    @require_api_key
    def pattern_delete(pattern_id):
        row = db.execute_one(
            "SELECT id FROM pattern_results WHERE pattern_id = :p0",
            (pattern_id,)
        )
        if not row:
            return err('Pattern result not found', 404)
        db.execute_write(
            "DELETE FROM pattern_results WHERE pattern_id = :p0",
            (pattern_id,)
        )
        _running_patterns.pop(pattern_id, None)
        return ok({'message': f'Deleted {pattern_id}'})

    # ── Data Cache API ──────────────────────────────────────────────────────

    _data_refresh_status: dict = {}

    @app.route('/api/data/refresh', methods=['POST'])
    @require_api_key
    def data_refresh():
        """Download fresh market data for all pairs."""
        from data.market_data_cache import download_all, ALL_PAIRS, DEFAULT_TIMEFRAMES

        pairs = request.json.get('pairs', ALL_PAIRS) if request.is_json else ALL_PAIRS
        tfs = request.json.get('timeframes', DEFAULT_TIMEFRAMES) if request.is_json else DEFAULT_TIMEFRAMES

        if _data_refresh_status.get('status') == 'running':
            return ok({'message': 'Data refresh already running', **_data_refresh_status})

        def _run_refresh():
            _data_refresh_status.update({'status': 'running', 'started': time.strftime('%H:%M:%S')})
            try:
                success, failed = download_all(pairs, tfs)
                _data_refresh_status.update({
                    'status': 'completed', 'success': success,
                    'failed': failed, 'finished': time.strftime('%H:%M:%S'),
                })
                logger.info(f"Data refresh: {success} OK, {failed} failed")
            except Exception as e:
                _data_refresh_status.update({'status': 'failed', 'error': str(e)})
                logger.error(f"Data refresh failed: {e}")

        import time as _time_mod
        thread = threading.Thread(target=_run_refresh, daemon=True)
        thread.start()
        return ok({'message': 'Data refresh started', 'pairs': len(pairs), 'timeframes': tfs}, 202)

    @app.route('/api/data/status')
    @require_api_key
    def data_status():
        from data.market_data_cache import get_cache_info
        info = get_cache_info()
        return ok({'files': info, 'total': len(info), 'refresh': _data_refresh_status})

    # ── Trading Modes ────────────────────────────────────────────────────────

    @app.route('/api/trading-modes')
    @require_api_key
    def trading_modes_status():
        """Return config and recent signal counts for all 5 trading modes."""
        from signals.trading_modes import TRADING_MODES

        modes_info = []
        for mode in TRADING_MODES:
            # Count signals sent by this mode in last 24h
            try:
                row = db.execute_one(
                    "SELECT COUNT(*) as cnt FROM signals "
                    "WHERE mode = :p0 AND created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)",
                    (mode['name'],)
                )
                signals_24h = row['cnt'] if row else 0
            except Exception:
                signals_24h = 0

            modes_info.append({
                'id':         mode['id'],
                'name':       mode['name'],
                'label':      mode['label'],
                'pattern':    mode['pattern'],
                'filter':     mode['filter'],
                'timeframes': mode['timeframes'],
                'direction':  mode['direction'],
                'stats':      mode['stats'],
                'signals_24h': signals_24h,
            })

        return ok({'modes': modes_info, 'total': len(modes_info)})

    # ── Health check (no auth) ────────────────────────────────────────────

    @app.route('/health')
    def health():
        return jsonify({'status': 'ok', 'service': 'ls-signal-bot'})

    # ── Error handlers ────────────────────────────────────────────────────

    @app.errorhandler(404)
    def not_found(e):
        return err('Endpoint not found', 404)

    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"API 500: {e}")
        return err('Internal server error', 500)

    return app
