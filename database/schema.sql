-- ============================================================
-- LS Trading Signal System - Complete Database Schema
-- signal.lstrading.xyz
-- MySQL 8.0+
-- ============================================================

CREATE DATABASE IF NOT EXISTS ls_trading_signals
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE ls_trading_signals;

-- ============================================================
-- 1. ADMIN USERS
-- ============================================================
CREATE TABLE admin_users (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(50)  UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    email         VARCHAR(100),
    role          ENUM('admin','viewer') DEFAULT 'admin',
    last_login    DATETIME,
    login_attempts INT DEFAULT 0,
    locked_until  DATETIME,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Default admin (password: admin123 — change immediately after setup)
INSERT INTO admin_users (username, password_hash, email, role)
VALUES ('admin', '$2y$12$placeholder_change_this_hash', 'admin@lstrading.xyz', 'admin');

-- ============================================================
-- 2. SETTINGS (All system configurations)
-- ============================================================
CREATE TABLE settings (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    setting_key   VARCHAR(100) UNIQUE NOT NULL,
    setting_value TEXT,
    setting_type  ENUM('string','number','boolean','json'),
    category      VARCHAR(50),
    description   TEXT,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

INSERT INTO settings (setting_key, setting_value, setting_type, category, description) VALUES
-- General
('bot_active',              'false',              'boolean', 'general',      'Master bot on/off switch'),
('trading_mode',            'hybrid',             'string',  'general',      'technical | news | hybrid | ai'),
('timezone',                'Asia/Dhaka',         'string',  'general',      'Admin panel timezone'),
-- Timeframes
('primary_timeframe',       'H1',                 'string',  'timeframe',    'Primary analysis timeframe'),
('higher_timeframe',        'H4',                 'string',  'timeframe',    'Higher timeframe for trend'),
('highest_timeframe',       'D1',                 'string',  'timeframe',    'Highest timeframe for macro trend'),
-- Daily limits
('max_daily_signals',       '5',                  'number',  'limits',       'Max signals per day'),
('max_open_positions',      '3',                  'number',  'limits',       'Max concurrent open signals'),
('max_daily_loss_pct',      '3',                  'number',  'limits',       'Auto-stop when daily loss exceeds %'),
('max_drawdown_pct',        '15',                 'number',  'limits',       'Auto-stop when drawdown exceeds %'),
-- Trading hours (UTC)
('trading_start_utc',       '08:00',              'string',  'hours',        'Trading start time UTC'),
('trading_end_utc',         '22:00',              'string',  'hours',        'Trading end time UTC'),
('active_days',             '[1,2,3,4,5]',        'json',    'hours',        'Mon=1...Sun=7'),
-- Confluence filter
('min_confluence_score',    '80',                 'number',  'filter',       'Minimum score to generate signal (0-100)'),
-- Risk
('risk_per_trade_pct',      '2.0',                'number',  'risk',         'Account risk per trade %'),
('account_balance',         '1000',               'number',  'risk',         'Current account balance USD'),
-- News filter
('news_filter_enabled',     'true',               'boolean', 'news',         'Pause trading before high-impact news'),
('news_avoid_minutes',      '30',                 'number',  'news',         'Minutes to avoid before/after news'),
-- AI
('claude_model',            'claude-haiku-4-5-20251001', 'string', 'ai',    'Claude model for news analysis'),
('ai_confidence_threshold', '70',                 'number',  'ai',           'Minimum AI confidence % to use signal'),
-- Telegram
('telegram_enabled',        'true',               'boolean', 'notification', 'Send Telegram notifications'),
('telegram_bot_token',      '',                   'string',  'notification', 'Telegram bot token'),
('telegram_chat_id',        '',                   'string',  'notification', 'Telegram chat ID'),
('daily_summary_time_utc',  '23:00',              'string',  'notification', 'Daily summary send time UTC'),
-- Cool-off
('cooloff_enabled',         'true',               'boolean', 'risk',         'Enable cool-off after consecutive losses'),
('cooloff_losses_trigger',  '3',                  'number',  'risk',         'Trigger cool-off after N consecutive losses'),
('cooloff_hours',           '2',                  'number',  'risk',         'Cool-off duration in hours');

-- ============================================================
-- 3. PAIRS (Trading pair configuration)
-- ============================================================
CREATE TABLE pairs (
    id                   INT AUTO_INCREMENT PRIMARY KEY,
    symbol               VARCHAR(20) UNIQUE NOT NULL,
    display_name         VARCHAR(50),
    category             ENUM('major','minor','exotic','metal','crypto','index'),
    is_active            BOOLEAN DEFAULT FALSE,
    use_custom_settings  BOOLEAN DEFAULT FALSE,
    custom_settings      JSON,
    -- Statistics (auto-updated)
    total_signals        INT DEFAULT 0,
    winning_signals      INT DEFAULT 0,
    losing_signals       INT DEFAULT 0,
    total_pips           DECIMAL(10,1) DEFAULT 0,
    win_rate             DECIMAL(5,2)  DEFAULT 0,
    last_signal_at       DATETIME,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

INSERT INTO pairs (symbol, display_name, category, is_active) VALUES
('EURUSD', 'EUR/USD',        'major', TRUE),
('GBPUSD', 'GBP/USD',        'major', TRUE),
('USDJPY', 'USD/JPY',        'major', FALSE),
('USDCHF', 'USD/CHF',        'major', FALSE),
('AUDUSD', 'AUD/USD',        'major', FALSE),
('USDCAD', 'USD/CAD',        'major', FALSE),
('NZDUSD', 'NZD/USD',        'major', FALSE),
('XAUUSD', 'XAU/USD (Gold)', 'metal', TRUE),
('EURJPY', 'EUR/JPY',        'minor', FALSE),
('GBPJPY', 'GBP/JPY',        'minor', FALSE),
('AUDJPY', 'AUD/JPY',        'minor', FALSE),
('EURGBP', 'EUR/GBP',        'minor', FALSE);

-- ============================================================
-- 4. SIGNALS (Main signal table)
-- ============================================================
CREATE TABLE signals (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    signal_id           VARCHAR(50) UNIQUE NOT NULL,   -- e.g. LST20260505-001
    pair                VARCHAR(20) NOT NULL,
    direction           ENUM('BUY','SELL') NOT NULL,

    -- Mode & strategy
    mode                ENUM('technical','news','hybrid','ai') NOT NULL,
    strategy            VARCHAR(50),

    -- Entry levels
    entry_price         DECIMAL(15,5) NOT NULL,
    stop_loss           DECIMAL(15,5) NOT NULL,
    take_profit         DECIMAL(15,5) NOT NULL,
    suggested_lot       DECIMAL(8,4),
    risk_amount         DECIMAL(10,2),

    -- Pip distances
    sl_pips             DECIMAL(8,1),
    tp_pips             DECIMAL(8,1),
    risk_reward_ratio   DECIMAL(4,2),

    -- Quality scoring
    confluence_score    DECIMAL(5,2) NOT NULL,
    quality_label       VARCHAR(20),        -- A+, A, B, C, D
    score_breakdown     JSON,

    -- Multi-timeframe analysis
    timeframe           VARCHAR(5) NOT NULL,
    htf_trend           VARCHAR(10),        -- UP, DOWN, SIDEWAYS
    mtf_trend           VARCHAR(10),
    ltf_signal          VARCHAR(10),
    market_regime       VARCHAR(30),        -- TRENDING_UP, RANGING, etc.

    -- AI/News
    news_sentiment      VARCHAR(20),        -- bullish, bearish, neutral
    ai_confidence       DECIMAL(5,2),
    reasoning           TEXT,
    indicator_snapshot  JSON,

    -- Status
    status              ENUM('OPEN','CLOSED_TP','CLOSED_SL','CLOSED_MANUAL','EXPIRED','CANCELLED') DEFAULT 'OPEN',

    -- Close data
    close_price         DECIMAL(15,5),
    close_time          DATETIME,
    actual_pips         DECIMAL(8,1),
    actual_profit       DECIMAL(10,2),
    duration_minutes    INT,
    close_reason        VARCHAR(100),

    -- Telegram
    telegram_message_id BIGINT,
    notification_sent   BOOLEAN DEFAULT FALSE,

    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_status    (status),
    INDEX idx_pair      (pair),
    INDEX idx_created   (created_at),
    INDEX idx_signal_id (signal_id)
);

-- ============================================================
-- 5. NEWS ARCHIVE
-- ============================================================
CREATE TABLE news_archive (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    source                  VARCHAR(50)  NOT NULL,
    title                   VARCHAR(500) NOT NULL,
    summary                 TEXT,
    link                    VARCHAR(500),
    published_at            DATETIME NOT NULL,

    -- AI Analysis
    sentiment               ENUM('bullish','bearish','neutral'),
    affected_currencies     JSON,
    impact_strength         DECIMAL(3,2),   -- 0.0 to 1.0
    impact_level            ENUM('high','medium','low'),
    ai_summary              TEXT,
    ai_recommendation       VARCHAR(20),    -- BUY, SELL, WAIT

    -- Processing
    processed               BOOLEAN DEFAULT FALSE,
    used_in_signal_id       VARCHAR(50),

    fetched_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_published     (published_at),
    INDEX idx_source        (source),
    INDEX idx_processed     (processed),
    INDEX idx_sentiment     (sentiment)
);

-- ============================================================
-- 6. ECONOMIC CALENDAR
-- ============================================================
CREATE TABLE economic_calendar (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    event_id     VARCHAR(100) UNIQUE,
    event_name   VARCHAR(200),
    country      VARCHAR(50),
    currency     VARCHAR(10),
    impact       ENUM('high','medium','low'),
    forecast     VARCHAR(100),
    previous     VARCHAR(100),
    actual       VARCHAR(100),
    event_time   DATETIME NOT NULL,
    is_past      BOOLEAN DEFAULT FALSE,
    fetched_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_event_time         (event_time),
    INDEX idx_currency_impact    (currency, impact)
);

-- ============================================================
-- 7. DAILY STATS (auto-generated each night)
-- ============================================================
CREATE TABLE daily_stats (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    stat_date         DATE UNIQUE NOT NULL,
    total_signals     INT DEFAULT 0,
    closed_tp         INT DEFAULT 0,
    closed_sl         INT DEFAULT 0,
    still_open        INT DEFAULT 0,
    cancelled         INT DEFAULT 0,
    win_rate          DECIMAL(5,2) DEFAULT 0,
    total_pips_won    DECIMAL(10,1) DEFAULT 0,
    total_pips_lost   DECIMAL(10,1) DEFAULT 0,
    net_pips          DECIMAL(10,1) DEFAULT 0,
    total_profit      DECIMAL(10,2) DEFAULT 0,
    total_loss        DECIMAL(10,2) DEFAULT 0,
    net_pnl           DECIMAL(10,2) DEFAULT 0,
    profit_factor     DECIMAL(5,2),
    best_signal_id    VARCHAR(50),
    worst_signal_id   VARCHAR(50),
    strategy_breakdown JSON,
    pair_breakdown     JSON,
    telegram_sent     BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 8. SYSTEM LOGS
-- ============================================================
CREATE TABLE system_logs (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    log_level  ENUM('debug','info','warning','error','critical'),
    component  VARCHAR(50),
    message    TEXT,
    metadata   JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_level   (log_level),
    INDEX idx_created (created_at)
);

-- ============================================================
-- 9. NOTIFICATIONS QUEUE
-- ============================================================
CREATE TABLE notifications_queue (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    type             ENUM('signal_open','signal_close','tp_hit','sl_hit','daily_summary','weekly_report','error','custom'),
    priority         ENUM('high','normal','low') DEFAULT 'normal',
    message          TEXT,
    metadata         JSON,
    status           ENUM('pending','sent','failed') DEFAULT 'pending',
    attempts         INT DEFAULT 0,
    last_attempt_at  DATETIME,
    sent_at          DATETIME,
    error_message    TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 10. COOL-OFF TRACKER
-- ============================================================
CREATE TABLE cooloff_log (
    id                   INT AUTO_INCREMENT PRIMARY KEY,
    triggered_at         DATETIME NOT NULL,
    resume_at            DATETIME NOT NULL,
    consecutive_losses   INT,
    reason               VARCHAR(200),
    is_active            BOOLEAN DEFAULT TRUE,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
