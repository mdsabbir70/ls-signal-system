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

$data = [
    'pair'         => $_POST['pair'] ?? 'EURUSD',
    'timeframe'    => $_POST['timeframe'] ?? 'H1',
    'start_date'   => $_POST['start_date'] ?? '2024-01-01',
    'end_date'     => $_POST['end_date'] ?? '2026-05-01',
    'min_score'    => floatval($_POST['min_score'] ?? 80),
    'sl_atr_mult'  => floatval($_POST['sl_atr_mult'] ?? 1.5),
    'tp_atr_mult'  => floatval($_POST['tp_atr_mult'] ?? 2.0),
    'trading_mode' => $_POST['trading_mode'] ?? 'technical',
];

$result = bot_post('/api/backtest/run', $data);

if ($result['success'] && isset($result['data'])) {
    echo json_encode($result['data']);
} else {
    echo json_encode([
        'success' => false,
        'error'   => $result['data']['error'] ?? $result['error'] ?? 'Failed to start backtest',
    ]);
}
