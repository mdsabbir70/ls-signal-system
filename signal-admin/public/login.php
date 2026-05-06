<?php
require_once __DIR__ . '/../includes/config.php';
require_once __DIR__ . '/../includes/db.php';
require_once __DIR__ . '/../includes/auth.php';

session_start_secure();

// Already logged in?
if (is_logged_in()) {
    header('Location: /dashboard.php');
    exit;
}

$error = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!verify_csrf($_POST['_csrf'] ?? '')) {
        $error = 'Invalid request. Please try again.';
    } else {
        $result = attempt_login(
            trim($_POST['username'] ?? ''),
            $_POST['password'] ?? ''
        );
        if ($result['success']) {
            header('Location: /dashboard.php');
            exit;
        }
        $error = htmlspecialchars($result['error']);
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Login — <?= APP_NAME ?></title>
<link rel="stylesheet" href="/assets/css/admin.css">
</head>
<body class="login-page">

<div class="login-container">
    <div class="login-header">
        <div class="login-logo">📊</div>
        <h1><?= APP_NAME ?></h1>
        <p>Admin Panel</p>
    </div>

    <?php if ($error): ?>
    <div class="alert alert-danger"><?= $error ?></div>
    <?php endif; ?>

    <form method="POST" action="/login.php" autocomplete="off">
        <input type="hidden" name="_csrf" value="<?= csrf_token() ?>">

        <div class="form-group">
            <label for="username">Username</label>
            <input type="text" id="username" name="username" required
                   autofocus autocomplete="username"
                   value="<?= htmlspecialchars($_POST['username'] ?? '') ?>">
        </div>

        <div class="form-group">
            <label for="password">Password</label>
            <input type="password" id="password" name="password" required
                   autocomplete="current-password">
        </div>

        <button type="submit" class="btn btn-primary btn-block">
            Sign In
        </button>
    </form>

    <p class="login-footer">signal.lstrading.xyz</p>
</div>

</body>
</html>
