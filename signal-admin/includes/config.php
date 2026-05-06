<?php
/**
 * LS Signal Admin — Configuration
 * signal.lstrading.xyz
 */

// ── Database ─────────────────────────────────────────────────────────────────
define('DB_HOST',    getenv('DB_HOST')     ?: 'localhost');
define('DB_PORT',    getenv('DB_PORT')     ?: '3306');
define('DB_NAME',    getenv('DB_NAME')     ?: 'ls_trading_signals');
define('DB_USER',    getenv('DB_USER')     ?: 'root');
define('DB_PASS',    getenv('DB_PASS')     ?: '');

// ── Bot API ───────────────────────────────────────────────────────────────────
define('BOT_API_URL', getenv('BOT_API_URL') ?: 'http://127.0.0.1:5050');
define('BOT_API_KEY', getenv('BOT_API_KEY') ?: '');

// ── Session ────────────────────────────────────────────────────────────────────
define('SESSION_LIFETIME', 7200);          // 2 hours
define('MAX_LOGIN_ATTEMPTS', 5);
define('LOCKOUT_DURATION', 900);           // 15 minutes

// ── App ────────────────────────────────────────────────────────────────────────
define('APP_NAME',    'LS Signal System');
define('APP_VERSION', '1.0.0');
define('APP_URL',     'https://signal.lstrading.xyz');
define('TIMEZONE',    'Asia/Dhaka');

date_default_timezone_set(TIMEZONE);
