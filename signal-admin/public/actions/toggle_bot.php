<?php
require_once __DIR__ . '/../../includes/config.php';
require_once __DIR__ . '/../../includes/db.php';
require_once __DIR__ . '/../../includes/auth.php';
require_once __DIR__ . '/../../includes/bot_api.php';

require_login();

if ($_SERVER['REQUEST_METHOD'] !== 'POST' || !verify_csrf($_POST['_csrf'] ?? '')) {
    header('Location: /dashboard.php');
    exit;
}

$current = get_setting('bot_active', false);
$new_state = !$current;

set_setting('bot_active', $new_state ? 'true' : 'false');
bot_post('/api/bot/toggle', ['active' => $new_state]);

header('Location: /dashboard.php');
exit;
