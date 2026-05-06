-- ============================================================
-- Migration: Economic Events Table
-- For storing ForexFactory calendar events
-- ============================================================

USE ls_trading_signals;

CREATE TABLE IF NOT EXISTS economic_events (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    event_title     VARCHAR(200) NOT NULL,
    currency        VARCHAR(10)  NOT NULL,
    event_time      DATETIME     NOT NULL,
    impact_level    VARCHAR(20)  DEFAULT 'low',
    forecast_value  VARCHAR(50)  DEFAULT '',
    previous_value  VARCHAR(50)  DEFAULT '',
    actual_value    VARCHAR(50)  DEFAULT '',
    affected_pairs  JSON,
    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_event (event_title(100), event_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Index for quick gate lookups
CREATE INDEX idx_econ_time_impact ON economic_events (event_time, impact_level);
CREATE INDEX idx_econ_currency ON economic_events (currency);
