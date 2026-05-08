"""
Database Manager — MySQL connection pool using PyMySQL.
Thread-safe with connection pooling via SQLAlchemy.
"""
import os
import json
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

import pymysql
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import OperationalError

from utils.logger import setup_logger

logger = setup_logger('database')


class Database:
    """MySQL database wrapper with connection pooling."""

    def __init__(self):
        self.engine = None
        self._connected = False

    def connect(
        self,
        host: str,
        port: int,
        dbname: str,
        user: str,
        password: str,
        pool_size: int = 5,
    ):
        """Create connection pool. Call once at startup."""
        dsn = f"mysql+pymysql://{user}:{password}@{host}:{port}/{dbname}?charset=utf8mb4"
        try:
            self.engine = create_engine(
                dsn,
                poolclass=QueuePool,
                pool_size=pool_size,
                max_overflow=2,
                pool_pre_ping=True,       # Reconnect on stale connections
                pool_recycle=3600,        # Recycle connections every hour
                echo=False,
            )
            # Test connection
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            self._connected = True
            logger.info(f"DB connected: {host}:{port}/{dbname} (pool={pool_size})")
        except Exception as e:
            logger.critical(f"DB connection failed: {e}")
            raise

    def is_connected(self) -> bool:
        return self._connected and self.engine is not None

    @contextmanager
    def _get_conn(self):
        """Context manager for database connections."""
        if not self.is_connected():
            raise RuntimeError("Database not connected. Call db.connect() first.")
        conn = self.engine.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Run a SELECT query and return list of dicts."""
        with self._get_conn() as conn:
            result = conn.execute(text(query), self._build_params(query, params))
            columns = result.keys()
            return [dict(zip(columns, row)) for row in result.fetchall()]

    def execute_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Run a SELECT query and return the first row as dict, or None."""
        rows = self.execute(query, params)
        return rows[0] if rows else None

    def execute_write(self, query: str, params: tuple = ()) -> int:
        """Run INSERT/UPDATE/DELETE. Returns lastrowid for INSERTs."""
        with self._get_conn() as conn:
            result = conn.execute(text(query), self._build_params(query, params))
            if query.strip().upper().startswith('INSERT'):
                return result.lastrowid
            return result.rowcount

    def execute_many(self, query: str, params_list: List[tuple]):
        """Run batch INSERT/UPDATE. Returns rows affected."""
        with self._get_conn() as conn:
            total = 0
            for params in params_list:
                result = conn.execute(text(query), self._build_params(query, params))
                total += result.rowcount
            return total

    @staticmethod
    def _build_params(query: str, params: tuple) -> dict:
        """Convert positional %s params to SQLAlchemy named params (:p0, :p1...)."""
        if not params:
            return {}
        named = {}
        idx = 0
        new_query_parts = query.split('%s')
        for i, val in enumerate(params):
            named[f'p{i}'] = val
        # SQLAlchemy text() uses :name syntax — handled by callers using text()
        # For simple positional use, map to dict with positional keys
        return {f'p{i}': v for i, v in enumerate(params)}

    # ── Convenience methods ───────────────────────────────────────────────

    def get_setting(self, key: str, default=None):
        """Fetch a single setting value from DB."""
        row = self.execute_one(
            "SELECT setting_value, setting_type FROM settings WHERE setting_key = :p0",
            (key,)
        )
        if not row:
            return default
        value = row['setting_value']
        dtype = row['setting_type']
        try:
            if dtype == 'boolean':
                return value.lower() in ('true', '1', 'yes')
            elif dtype == 'number':
                return float(value) if '.' in str(value) else int(value)
            elif dtype == 'json':
                return json.loads(value)
            return value
        except Exception:
            return value

    def set_setting(self, key: str, value) -> bool:
        """Update a setting value in DB."""
        str_value = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        try:
            self.execute_write(
                "UPDATE settings SET setting_value = :p0 WHERE setting_key = :p1",
                (str_value, key)
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update setting {key}: {e}")
            return False

    def log(self, level: str, component: str, message: str, metadata: dict = None):
        """Write a log entry to system_logs table."""
        try:
            meta_json = json.dumps(metadata) if metadata else None
            self.execute_write(
                """INSERT INTO system_logs (log_level, component, message, metadata)
                   VALUES (:p0, :p1, :p2, :p3)""",
                (level, component, message, meta_json)
            )
        except Exception as e:
            logger.error(f"Failed to write log to DB: {e}")

    def has_open_pattern_signal(self, pair: str, mode: str, timeframe: str) -> bool:
        """Return True if an OPEN pattern signal already exists for this pair+mode+tf."""
        row = self.execute_one(
            "SELECT COUNT(*) as cnt FROM signals WHERE pair = :p0 AND mode = :p1 AND timeframe = :p2 AND status = 'OPEN'",
            (pair, mode, timeframe)
        )
        return (row['cnt'] if row else 0) > 0

    def get_active_pairs(self) -> List[str]:
        """Return list of active trading pair symbols."""
        rows = self.execute("SELECT symbol FROM pairs WHERE is_active = TRUE")
        return [r['symbol'] for r in rows]

    def get_open_signal_count(self, mode: str = None) -> int:
        """Count currently open signals. Optionally filter by mode."""
        if mode:
            row = self.execute_one(
                "SELECT COUNT(*) as cnt FROM signals WHERE status = 'OPEN' AND mode = :p0",
                (mode,)
            )
        else:
            row = self.execute_one(
                "SELECT COUNT(*) as cnt FROM signals WHERE status = 'OPEN'"
            )
        return row['cnt'] if row else 0

    def get_open_signals_summary(self, mode: str = None) -> list:
        """Get summary of open signals for correlation checks.
        Args:
            mode: Filter by exact mode name (e.g. 'hybrid', 'technical', 'news').
                  'pattern' is special — matches all 'Mode_%' pattern signals.
                  None returns all open signals.
        """
        try:
            if mode is None:
                rows = self.execute(
                    "SELECT pair, direction FROM signals WHERE status = 'OPEN'"
                )
            elif mode == 'pattern':
                rows = self.execute(
                    "SELECT pair, direction FROM signals WHERE status = 'OPEN' AND mode LIKE 'Mode_%'"
                )
            else:
                # Exact mode match: hybrid, technical, news, technical_news_filter, ai, etc.
                rows = self.execute(
                    "SELECT pair, direction FROM signals WHERE status = 'OPEN' AND mode = :p0",
                    (mode,)
                )
            return [{'pair': r['pair'], 'direction': r['direction']} for r in rows] if rows else []
        except Exception:
            return []

    def get_today_signal_count(self, mode: str = None) -> int:
        """Count signals generated today. Optionally filter by mode."""
        if mode:
            row = self.execute_one(
                "SELECT COUNT(*) as cnt FROM signals WHERE DATE(created_at) = CURDATE() AND status != 'CANCELLED' AND mode = :p0",
                (mode,)
            )
        else:
            row = self.execute_one(
                "SELECT COUNT(*) as cnt FROM signals WHERE DATE(created_at) = CURDATE() AND status != 'CANCELLED'"
            )
        return row['cnt'] if row else 0

    def save_signal(self, signal: dict) -> int:
        """Insert a new signal record. Returns new signal ID."""
        return self.execute_write(
            """INSERT INTO signals
               (signal_id, pair, direction, mode, strategy, entry_price, stop_loss, take_profit,
                suggested_lot, risk_amount, sl_pips, tp_pips, risk_reward_ratio,
                confluence_score, quality_label, score_breakdown,
                timeframe, htf_trend, mtf_trend, ltf_signal, market_regime,
                news_sentiment, ai_confidence, reasoning, indicator_snapshot, status)
               VALUES (:p0,:p1,:p2,:p3,:p4,:p5,:p6,:p7,:p8,:p9,:p10,:p11,:p12,
                       :p13,:p14,:p15,:p16,:p17,:p18,:p19,:p20,:p21,:p22,:p23,:p24,:p25)""",
            (
                signal.get('signal_id'),
                signal.get('pair'),
                signal.get('direction'),
                signal.get('mode'),
                signal.get('strategy'),
                signal.get('entry_price'),
                signal.get('stop_loss'),
                signal.get('take_profit'),
                signal.get('suggested_lot'),
                signal.get('risk_amount'),
                signal.get('sl_pips'),
                signal.get('tp_pips'),
                signal.get('risk_reward_ratio'),
                signal.get('confluence_score'),
                signal.get('quality_label'),
                json.dumps(signal.get('score_breakdown', {})),
                signal.get('timeframe'),
                signal.get('htf_trend'),
                signal.get('mtf_trend'),
                signal.get('ltf_signal'),
                signal.get('market_regime'),
                signal.get('news_sentiment'),
                signal.get('ai_confidence'),
                signal.get('reasoning'),
                json.dumps(signal.get('indicator_snapshot', {})),
                'OPEN',
            )
        )

    def get_mode_stats(self) -> list:
        """
        Per-mode performance stats.
        Returns list of dicts: {mode, total, wins, losses, open, win_rate, avg_pips}
        """
        rows = self.execute("""
            SELECT
                mode,
                COUNT(*)                                              AS total,
                SUM(status = 'CLOSED_TP')                            AS wins,
                SUM(status = 'CLOSED_SL')                            AS losses,
                SUM(status = 'OPEN')                                 AS open_signals,
                ROUND(
                    SUM(status='CLOSED_TP') * 100.0
                    / NULLIF(SUM(status IN ('CLOSED_TP','CLOSED_SL')), 0)
                , 1)                                                  AS win_rate,
                ROUND(AVG(CASE WHEN status IN ('CLOSED_TP','CLOSED_SL')
                               THEN actual_pips END), 1)             AS avg_pips,
                ROUND(SUM(CASE WHEN status IN ('CLOSED_TP','CLOSED_SL')
                               THEN actual_profit ELSE 0 END), 2)    AS total_profit
            FROM signals
            WHERE mode IS NOT NULL
            GROUP BY mode
            ORDER BY win_rate DESC
        """)
        return [dict(r) for r in (rows or [])]

    def get_recent_closed(self, limit: int = 10) -> list:
        """Last N closed signals with result."""
        rows = self.execute("""
            SELECT signal_id, pair, direction, mode, timeframe,
                   entry_price, close_price, actual_pips, actual_profit,
                   status, duration_minutes, close_time
            FROM signals
            WHERE status IN ('CLOSED_TP', 'CLOSED_SL')
            ORDER BY close_time DESC
            LIMIT %s
        """ % int(limit))
        return [dict(r) for r in (rows or [])]

    def close_signal(self, signal_id: str, close_data: dict) -> bool:
        """Update a signal with close information."""
        try:
            self.execute_write(
                """UPDATE signals SET
                   status         = :p0,
                   close_price    = :p1,
                   close_time     = NOW(),
                   actual_pips    = :p2,
                   actual_profit  = :p3,
                   duration_minutes = :p4,
                   close_reason   = :p5
                   WHERE signal_id = :p6""",
                (
                    close_data.get('status'),
                    close_data.get('close_price'),
                    close_data.get('actual_pips'),
                    close_data.get('actual_profit'),
                    close_data.get('duration_minutes'),
                    close_data.get('close_reason'),
                    signal_id,
                )
            )
            return True
        except Exception as e:
            logger.error(f"Failed to close signal {signal_id}: {e}")
            return False


# Singleton — import and use everywhere
db = Database()
