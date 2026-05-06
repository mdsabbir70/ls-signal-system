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

$discovery_id = trim($_POST['discovery_id'] ?? '');
if (!$discovery_id) {
    echo json_encode(['success' => false, 'error' => 'discovery_id required']);
    exit;
}

$result = bot_delete('/api/discovery/' . urlencode($discovery_id));

if ($result['success']) {
    echo json_encode(['success' => true, 'message' => 'Deleted']);
} else {
    echo json_encode(['success' => false, 'error' => $result['data']['error'] ?? $result['error'] ?? 'Failed to delete']);
}
