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

$id = $_POST['backtest_id'] ?? '';
if (!$id) {
    echo json_encode(['success' => false, 'error' => 'backtest_id required']);
    exit;
}

// Delete via bot API (server-side curl to 127.0.0.1:5050)
$result = bot_delete('/api/backtest/' . urlencode($id));

if ($result['success']) {
    echo json_encode(['success' => true, 'message' => "Deleted $id"]);
} else {
    // Fallback: delete directly from DB
    try {
        db_exec("DELETE FROM backtest_results WHERE backtest_id = ?", [$id]);
        echo json_encode(['success' => true, 'message' => "Deleted $id (direct)"]);
    } catch (Exception $e) {
        echo json_encode(['success' => false, 'error' => $e->getMessage()]);
    }
}
