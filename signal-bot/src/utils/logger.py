"""
Logging Setup — Rotating file + colored console output.
"""
import logging
import os
from logging.handlers import TimedRotatingFileHandler

_loggers: dict = {}


def setup_logger(name: str, level: str = None) -> logging.Logger:
    """Get or create a named logger with file + console handlers."""
    if name in _loggers:
        return _loggers[name]

    # Resolve level
    env_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_level  = getattr(logging, level or env_level, logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logger.propagate = False

    if logger.handlers:
        _loggers[name] = logger
        return logger

    fmt = logging.Formatter(
        fmt='%(asctime)s [%(levelname)-8s] %(name)s — %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    # ── Console handler ────────────────────────────────────────────────────
    console = logging.StreamHandler()
    console.setFormatter(_ColorFormatter(fmt))
    console.setLevel(log_level)
    logger.addHandler(console)

    # ── File handler (daily rotation, keep 30 days) ────────────────────────
    log_dir = os.getenv('LOG_DIR', 'logs')
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"{name.replace('.', '_')}.log")
    file_handler = TimedRotatingFileHandler(
        log_file,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8',
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(log_level)
    logger.addHandler(file_handler)

    _loggers[name] = logger
    return logger


class _ColorFormatter(logging.Formatter):
    """Adds ANSI color codes to console log levels."""

    COLORS = {
        'DEBUG':    '\033[36m',   # Cyan
        'INFO':     '\033[32m',   # Green
        'WARNING':  '\033[33m',   # Yellow
        'ERROR':    '\033[31m',   # Red
        'CRITICAL': '\033[35m',   # Magenta
    }
    RESET = '\033[0m'

    def __init__(self, base_formatter: logging.Formatter):
        super().__init__()
        self._base = base_formatter

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, '')
        msg   = self._base.format(record)
        return f"{color}{msg}{self.RESET}" if color else msg
