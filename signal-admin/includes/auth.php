<?php
/**
 * Authentication helpers
 */

function session_start_secure(): void {
    if (session_status() === PHP_SESSION_NONE) {
        ini_set('session.cookie_httponly', 1);
        ini_set('session.cookie_secure', isset($_SERVER['HTTPS']) ? 1 : 0);
        ini_set('session.use_strict_mode', 1);
        session_start();
    }
}

function is_logged_in(): bool {
    session_start_secure();
    if (empty($_SESSION['user_id']) || empty($_SESSION['logged_in_at'])) {
        return false;
    }
    // Session timeout
    if (time() - $_SESSION['logged_in_at'] > SESSION_LIFETIME) {
        session_destroy();
        return false;
    }
    return true;
}

function require_login(): void {
    if (!is_logged_in()) {
        header('Location: /login.php');
        exit;
    }
}

function attempt_login(string $username, string $password): array {
    // Check lockout
    $user = db_one(
        'SELECT * FROM admin_users WHERE username = ? AND is_active = TRUE',
        [trim($username)]
    );

    if (!$user) {
        return ['success' => false, 'error' => 'Invalid credentials'];
    }

    // Check locked
    if ($user['locked_until'] && strtotime($user['locked_until']) > time()) {
        $remaining = ceil((strtotime($user['locked_until']) - time()) / 60);
        return ['success' => false, 'error' => "Account locked. Try again in {$remaining} minutes."];
    }

    if (!password_verify($password, $user['password_hash'])) {
        // Increment failed attempts
        $attempts = $user['login_attempts'] + 1;
        $lock_sql = '';
        $lock_params = [$attempts, $user['id']];

        if ($attempts >= MAX_LOGIN_ATTEMPTS) {
            $lock_until = date('Y-m-d H:i:s', time() + LOCKOUT_DURATION);
            db_exec(
                'UPDATE admin_users SET login_attempts = ?, locked_until = ? WHERE id = ?',
                [$attempts, $lock_until, $user['id']]
            );
            return ['success' => false, 'error' => 'Too many failed attempts. Account locked for 15 minutes.'];
        }

        db_exec(
            'UPDATE admin_users SET login_attempts = ? WHERE id = ?',
            [$attempts, $user['id']]
        );
        return ['success' => false, 'error' => 'Invalid credentials'];
    }

    // Success — reset attempts, update last login
    db_exec(
        'UPDATE admin_users SET login_attempts = 0, locked_until = NULL, last_login = NOW() WHERE id = ?',
        [$user['id']]
    );

    session_start_secure();
    session_regenerate_id(true);
    $_SESSION['user_id']      = $user['id'];
    $_SESSION['username']     = $user['username'];
    $_SESSION['role']         = $user['role'];
    $_SESSION['logged_in_at'] = time();

    return ['success' => true, 'user' => $user];
}

function logout(): void {
    session_start_secure();
    session_destroy();
    header('Location: /login.php');
    exit;
}

function csrf_token(): string {
    if (empty($_SESSION['csrf_token'])) {
        $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
    }
    return $_SESSION['csrf_token'];
}

function verify_csrf(string $token): bool {
    return isset($_SESSION['csrf_token']) && hash_equals($_SESSION['csrf_token'], $token);
}
