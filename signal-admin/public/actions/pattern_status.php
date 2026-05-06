<?php
require_once __DIR__ . '/../../includes/config.php';
require_once __DIR__ . '/../../includes/db.php';
require_once __DIR__ . '/../../includes/auth.php';
require_once __DIR__ . '/../../includes/bot_api.php';

require_login();
header('Content-Type: application/json');

$result = bot_get('/api/pattern/status');

if ($result['success'] && isset($result['data'])) {
    echo json_encode($result['data']);
} else {
    echo json_encode(['success' => false, 'error' => $result['error'] ?? 'Failed']);
}
