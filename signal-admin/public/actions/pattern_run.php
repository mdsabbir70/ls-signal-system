<?php
require_once __DIR__ . '/../../includes/config.php';
require_once __DIR__ . '/../../includes/db.php';
require_once __DIR__ . '/../../includes/auth.php';
require_once __DIR__ . '/../../includes/bot_api.php';

require_login();
header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo json_encode(['success' => false, 'error' => 'POST required']);
    exit;
}

$pair       = strtoupper(trim($_POST['pair'] ?? 'EURUSD'));
$timeframes = $_POST['timeframes'] ?? ['H1', 'H4', 'D1'];
if (!is_array($timeframes)) {
    $timeframes = explode(',', $timeframes);
}
$min_win_rate  = floatval($_POST['min_win_rate']  ?? 60.0);
$min_trades    = intval($_POST['min_trades']    ?? 5);
$lookback_days = intval($_POST['lookback_days'] ?? 0);

$data = [
    'pair'          => $pair,
    'timeframes'    => array_values($timeframes),
    'min_win_rate'  => $min_win_rate,
    'min_trades'    => $min_trades,
    'lookback_days' => $lookback_days,
];

$result = bot_post('/api/pattern/run', $data);

if ($result['success'] && isset($result['data'])) {
    echo json_encode($result['data']);
} else {
    echo json_encode([
        'success' => false,
        'error'   => $result['data']['error'] ?? $result['error'] ?? 'Failed to start pattern analysis',
    ]);
}
