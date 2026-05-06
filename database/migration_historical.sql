-- ============================================================
-- LS Trading Signal System — Historical Data Tables
-- Migration: Add tables for 10-year historical data storage
-- Run after schema.sql
-- ============================================================

USE ls_trading_signals;

-- ============================================================
-- 1. HISTORICAL PRICE DATA (OHLCV)
-- Stores candle data per pair/timeframe from yfinance
-- ============================================================
CREATE TABLE IF NOT EXISTS historical_prices (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    pair            VARCHAR(20) NOT NULL,
    timeframe       VARCHAR(5)  NOT NULL,       -- W1, D1, H4, H1
    open_time       DATETIME    NOT NULL,
    open_price      DECIMAL(15,5) NOT NULL,
    high_price      DECIMAL(15,5) NOT NULL,
    low_price       DECIMAL(15,5) NOT NULL,
    close_price     DECIMAL(15,5) NOT NULL,
    volume          DECIMAL(20,2) DEFAULT 0,

    UNIQUE KEY uq_pair_tf_time (pair, timeframe, open_time),
    INDEX idx_pair_tf (pair, timeframe),
    INDEX idx_open_time (open_time)
) ENGINE=InnoDB;

-- ============================================================
-- 2. COT DATA (Commitment of Traders)
-- Weekly CFTC reports — speculator/commercial positioning
-- ============================================================
CREATE TABLE IF NOT EXISTS cot_data (
    id                      BIGINT AUTO_INCREMENT PRIMARY KEY,
    report_date             DATE        NOT NULL,
    currency                VARCHAR(10) NOT NULL,     -- EUR, GBP, JPY, etc.
    contract_name           VARCHAR(200),

    -- Non-commercial (speculators/hedge funds)
    noncomm_long            BIGINT DEFAULT 0,
    noncomm_short           BIGINT DEFAULT 0,
    noncomm_net             BIGINT DEFAULT 0,
    noncomm_spreading       BIGINT DEFAULT 0,

    -- Commercial (hedgers/banks)
    comm_long               BIGINT DEFAULT 0,
    comm_short              BIGINT DEFAULT 0,
    comm_net                BIGINT DEFAULT 0,

    -- Non-reportable (retail)
    nonrep_long             BIGINT DEFAULT 0,
    nonrep_short            BIGINT DEFAULT 0,
    nonrep_net              BIGINT DEFAULT 0,

    -- Open interest
    open_interest           BIGINT DEFAULT 0,
    oi_change               BIGINT DEFAULT 0,

    UNIQUE KEY uq_date_currency (report_date, currency),
    INDEX idx_currency (currency),
    INDEX idx_report_date (report_date)
) ENGINE=InnoDB;

-- ============================================================
-- 3. INTEREST RATES (Central Bank Rates)
-- Historical rate decisions for each major currency
-- ============================================================
CREATE TABLE IF NOT EXISTS interest_rates (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    rate_date       DATE        NOT NULL,
    currency        VARCHAR(10) NOT NULL,
    central_bank    VARCHAR(50) NOT NULL,
    rate_value      DECIMAL(6,3) NOT NULL,
    rate_change     DECIMAL(6,3) DEFAULT 0,

    UNIQUE KEY uq_date_currency (rate_date, currency),
    INDEX idx_currency (currency),
    INDEX idx_rate_date (rate_date)
) ENGINE=InnoDB;

-- ============================================================
-- 4. DATA COLLECTION LOG
-- Tracks what data was collected, when, and status
-- ============================================================
CREATE TABLE IF NOT EXISTS data_collection_log (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    data_type       VARCHAR(50) NOT NULL,          -- prices, cot, rates
    pair            VARCHAR(20),
    timeframe       VARCHAR(5),
    status          ENUM('started','completed','failed') NOT NULL,
    records_count   INT DEFAULT 0,
    date_from       DATE,
    date_to         DATE,
    error_message   TEXT,
    duration_sec    INT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ============================================================
-- 5. BACKTEST RESULTS
-- Stores strategy backtesting run outcomes
-- ============================================================
CREATE TABLE IF NOT EXISTS backtest_results (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    backtest_id     VARCHAR(50)  UNIQUE NOT NULL,
    strategy_name   VARCHAR(100),
    pair            VARCHAR(20),
    timeframe       VARCHAR(5),
    start_date      DATE,
    end_date        DATE,
    total_signals   INT DEFAULT 0,
    wins            INT DEFAULT 0,
    losses          INT DEFAULT 0,
    win_rate        DECIMAL(5,2) DEFAULT 0,
    net_pips        DECIMAL(10,1) DEFAULT 0,
    net_pnl         DECIMAL(10,2) DEFAULT 0,
    profit_factor   DECIMAL(5,2) DEFAULT 0,
    max_drawdown    DECIMAL(5,2) DEFAULT 0,
    avg_rr          DECIMAL(4,2) DEFAULT 0,
    sharpe_ratio    DECIMAL(6,3) DEFAULT 0,
    settings_json   JSON,
    trades_json     JSON,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
