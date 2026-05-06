-- ============================================================
-- LS Trading Signal System — Sentiment History Table
-- Migration: Add table for sentiment tracking
-- ============================================================

CREATE TABLE IF NOT EXISTS sentiment_history (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    source          VARCHAR(30) NOT NULL,           -- 'fear_greed', 'vix', 'social'
    value           DECIMAL(10,2) NOT NULL,         -- Numeric value (FnG 0-100, VIX level)
    label           VARCHAR(50),                    -- Human label (Extreme Fear, Low, etc.)
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_source_time (source, created_at),
    INDEX idx_created (created_at)
) ENGINE=InnoDB;
