"""
Configuration Manager
DB-backed settings with .env fallback.
All runtime settings live in the `settings` MySQL table.
"""
import os
from dotenv import load_dotenv
from utils.logger import setup_logger

load_dotenv()
logger = setup_logger('config')


class Config:
    """Reads settings from DB (authoritative) with .env as fallback."""

    # ── DB connection (from .env only — not stored in DB) ─────────────────
    DB_HOST     = os.getenv('DB_HOST', 'localhost')
    DB_PORT     = int(os.getenv('DB_PORT', 3306))
    DB_NAME     = os.getenv('DB_NAME', 'ls_trading_signals')
    DB_USER     = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', 5))

    # ── Flask API ─────────────────────────────────────────────────────────
    FLASK_SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-change-me')
    FLASK_HOST       = os.getenv('FLASK_HOST', '127.0.0.1')
    FLASK_PORT       = int(os.getenv('FLASK_PORT', 5050))
    API_KEY          = os.getenv('API_KEY', '')

    # ── External APIs ─────────────────────────────────────────────────────
    ANTHROPIC_API_KEY    = os.getenv('ANTHROPIC_API_KEY', '')
    TELEGRAM_BOT_TOKEN   = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID     = os.getenv('TELEGRAM_CHAT_ID', '')

    # ── Logging ───────────────────────────────────────────────────────────
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_DIR   = os.getenv('LOG_DIR', 'logs')

    def __init__(self):
        self._cache: dict = {}
        self._db = None  # Injected after DB is ready

    def init_db(self, db_instance):
        """Call this after DB connection is established."""
        self._db = db_instance
        self._load_all()

    def _load_all(self):
        """Load all settings from DB into local cache."""
        if not self._db:
            return
        try:
            rows = self._db.execute("SELECT setting_key, setting_value, setting_type FROM settings")
            for row in rows:
                key   = row['setting_key']
                value = self._cast(row['setting_value'], row['setting_type'])
                self._cache[key] = value
            logger.info(f"Loaded {len(self._cache)} settings from DB")
        except Exception as e:
            logger.error(f"Failed to load settings from DB: {e}")

    def _cast(self, value: str, dtype: str):
        """Cast DB string value to the correct Python type."""
        if value is None:
            return None
        try:
            if dtype == 'boolean':
                return value.lower() in ('true', '1', 'yes', 'on')
            elif dtype == 'number':
                return float(value) if '.' in value else int(value)
            elif dtype == 'json':
                import json
                return json.loads(value)
            else:
                return value
        except Exception:
            return value

    def get(self, key: str, default=None):
        """Get a setting value. Returns default if not found."""
        return self._cache.get(key, default)

    def refresh(self):
        """Reload all settings from DB (atomic swap — no empty-cache window)."""
        if not self._db:
            return
        try:
            new_cache = {}
            rows = self._db.execute("SELECT setting_key, setting_value, setting_type FROM settings")
            for row in rows:
                new_cache[row['setting_key']] = self._cast(row['setting_value'], row['setting_type'])
            self._cache = new_cache
            logger.debug(f"Config refreshed: {len(new_cache)} settings")
        except Exception as e:
            logger.error(f"Config refresh failed (keeping old values): {e}")

    # ── Convenience accessors ─────────────────────────────────────────────

    @property
    def bot_active(self) -> bool:
        return self.get('bot_active', False)

    @property
    def trading_mode(self) -> str:
        return self.get('trading_mode', 'hybrid')

    @property
    def min_confluence_score(self) -> float:
        return float(self.get('min_confluence_score', 80))

    @property
    def risk_per_trade_pct(self) -> float:
        return float(self.get('risk_per_trade_pct', 2.0))

    @property
    def account_balance(self) -> float:
        return float(self.get('account_balance', 1000))

    @property
    def max_daily_signals(self) -> int:
        return int(self.get('max_daily_signals', 5))

    @property
    def max_open_positions(self) -> int:
        return int(self.get('max_open_positions', 3))

    @property
    def max_daily_loss_pct(self) -> float:
        return float(self.get('max_daily_loss_pct', 3))

    @property
    def primary_timeframe(self) -> str:
        return self.get('primary_timeframe', 'H1')

    @property
    def higher_timeframe(self) -> str:
        return self.get('higher_timeframe', 'H4')

    @property
    def highest_timeframe(self) -> str:
        return self.get('highest_timeframe', 'D1')

    @property
    def news_filter_enabled(self) -> bool:
        return self.get('news_filter_enabled', True)

    @property
    def news_avoid_minutes(self) -> int:
        return int(self.get('news_avoid_minutes', 30))

    @property
    def claude_model(self) -> str:
        return self.get('claude_model', 'claude-haiku-4-5-20251001')

    @property
    def ai_confidence_threshold(self) -> float:
        return float(self.get('ai_confidence_threshold', 70))

    @property
    def telegram_enabled(self) -> bool:
        return self.get('telegram_enabled', True)

    @property
    def cooloff_enabled(self) -> bool:
        return self.get('cooloff_enabled', True)

    @property
    def cooloff_losses_trigger(self) -> int:
        return int(self.get('cooloff_losses_trigger', 3))

    @property
    def cooloff_hours(self) -> float:
        return float(self.get('cooloff_hours', 2))

    @property
    def trading_start_utc(self) -> str:
        return self.get('trading_start_utc', '08:00')

    @property
    def trading_end_utc(self) -> str:
        return self.get('trading_end_utc', '22:00')

    @property
    def active_days(self) -> list:
        return self.get('active_days', [1, 2, 3, 4, 5])


# Singleton
config = Config()
