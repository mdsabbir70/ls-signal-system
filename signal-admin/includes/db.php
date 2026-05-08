<?php
/**
 * Database connection (PDO) — Singleton
 */

function get_db(): PDO {
    static $pdo = null;
    if ($pdo !== null) return $pdo;

    $dsn = sprintf(
        'mysql:host=%s;port=%s;dbname=%s;charset=utf8mb4',
        DB_HOST, DB_PORT, DB_NAME
    );
    $options = [
        PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES   => false,
    ];
    try {
        $pdo = new PDO($dsn, DB_USER, DB_PASS, $options);
    } catch (PDOException $e) {
        error_log('DB connection failed: ' . $e->getMessage());
        die(json_encode(['error' => 'Database connection failed']));
    }
    return $pdo;
}

/**
 * Execute a SELECT and return all rows.
 */
function db_query(string $sql, array $params = []): array {
    $stmt = get_db()->prepare($sql);
    $stmt->execute($params);
    return $stmt->fetchAll();
}

/**
 * Execute a SELECT and return one row.
 */
function db_one(string $sql, array $params = []): ?array {
    $rows = db_query($sql, $params);
    return $rows[0] ?? null;
}

/**
 * Execute INSERT/UPDATE/DELETE. Returns lastInsertId for INSERT.
 */
function db_exec(string $sql, array $params = []): string {
    $stmt = get_db()->prepare($sql);
    $stmt->execute($params);
    $verb = strtoupper(substr(ltrim($sql), 0, 6));
    return $verb === 'INSERT' ? get_db()->lastInsertId() : (string)$stmt->rowCount();
}

/**
 * Get a single setting value from DB.
 */
function get_setting(string $key, $default = null) {
    $row = db_one('SELECT setting_value, setting_type FROM settings WHERE setting_key = ?', [$key]);
    if (!$row) return $default;
    return cast_setting($row['setting_value'], $row['setting_type']);
}

/**
 * Update a setting in DB.
 */
function set_setting(string $key, $value): void {
    $val = is_array($value) || is_object($value) ? json_encode($value) : (string)$value;
    db_exec('UPDATE settings SET setting_value = ? WHERE setting_key = ?', [$val, $key]);
}

/**
 * Get the correct number of decimal places for a trading pair's price display.
 */
function price_decimals(string $pair): int {
    static $map = [
        'BTCUSDT'=>2,'ETHUSDT'=>2,'BNBUSDT'=>2,
        'SOLUSDT'=>4,'LINKUSDT'=>4,'DOTUSDT'=>4,'ADAUSDT'=>4,'TONUSDT'=>4,'HYPEUSDT'=>4,'SUIUSDT'=>4,
        'XRPUSDT'=>6,'DOGEUSDT'=>6,
        'PEPEUSDT'=>8,
    ];
    if (isset($map[$pair])) return $map[$pair];
    if (str_contains($pair, 'JPY')) return 3;
    if (str_contains($pair, 'XAU') || str_contains($pair, 'XAG')) return 2;
    return 5;
}

/**
 * Format a price with the correct decimals for the given pair.
 */
function fmt_price(float $price, string $pair): string {
    return number_format($price, price_decimals($pair));
}

function cast_setting($value, string $type) {
    if ($value === null) return null;
    switch ($type) {
        case 'boolean': return in_array(strtolower($value), ['true', '1', 'yes', 'on']);
        case 'number':  return strpos($value, '.') !== false ? (float)$value : (int)$value;
        case 'json':    return json_decode($value, true);
        default:        return $value;
    }
}
