<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow, noarchive, nosnippet">
<title><?= htmlspecialchars($page_title ?? 'Admin') ?> — <?= APP_NAME ?></title>
<link rel="stylesheet" href="/assets/css/admin.css">
</head>
<body>

<nav class="navbar">
    <div class="navbar-brand">
        <span class="brand-icon">📊</span>
        <span class="brand-name"><?= APP_NAME ?></span>
    </div>

    <div class="navbar-menu">
        <?php
        $current = basename($_SERVER['PHP_SELF']);
        $nav_items = [
            'dashboard.php' => ['icon' => '🏠', 'label' => 'Dashboard'],
            'signals.php'   => ['icon' => '📡', 'label' => 'Signals'],
            'pairs.php'     => ['icon' => '💱', 'label' => 'Pairs'],
            'news.php'      => ['icon' => '📰', 'label' => 'News'],
            'reports.php'   => ['icon' => '📈', 'label' => 'Reports'],
            'historical.php'=> ['icon' => '🗄️', 'label' => 'Historical'],
            'backtest.php'  => ['icon' => '🧪', 'label' => 'Backtest'],
            'discovery.php' => ['icon' => '🔍', 'label' => 'Discovery'],
            'sentiment.php' => ['icon' => '🧠', 'label' => 'Sentiment'],
            'settings.php'  => ['icon' => '⚙️', 'label' => 'Settings'],
        ];
        foreach ($nav_items as $file => $item):
            $active = ($current === $file) ? 'active' : '';
        ?>
        <a href="/<?= $file ?>" class="nav-link <?= $active ?>">
            <?= $item['icon'] ?> <?= $item['label'] ?>
        </a>
        <?php endforeach; ?>
    </div>

    <div class="navbar-right">
        <span class="nav-user">👤 <?= htmlspecialchars($_SESSION['username'] ?? '') ?></span>
        <a href="/logout.php" class="btn btn-sm btn-outline">Logout</a>
    </div>
</nav>

<main class="main-content">
    <div class="page-header">
        <h1><?= htmlspecialchars($page_title ?? 'Admin') ?></h1>
        <span class="page-time" id="server-time">
            <?= date('D, d M Y H:i:s') ?> (<?= TIMEZONE ?>)
        </span>
    </div>
