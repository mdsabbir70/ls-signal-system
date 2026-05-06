<?php
require_once __DIR__ . '/../includes/config.php';
require_once __DIR__ . '/../includes/db.php';
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/bot_api.php';

require_login();

// ── Data ──────────────────────────────────────────────────────────────────────
$bot_status = get_bot_status();

// Today stats
$today = date('Y-m-d');
$today_signals = db_one(
    "SELECT COUNT(*) as total,
            SUM(status='CLOSED_TP') as tp_hits,
            SUM(status='CLOSED_SL') as sl_hits,
            SUM(status='OPEN') as open_count,
            SUM(actual_profit) as net_pnl
     FROM signals WHERE DATE(created_at) = ?",
    [$today]
) ?: ['total' => 0, 'tp_hits' => 0, 'sl_hits' => 0, 'open_count' => 0, 'net_pnl' => 0];

$total = (int)$today_signals['total'];
$win_rate = $total > 0 ? round(($today_signals['tp_hits'] / $total) * 100, 1) : 0;

// Open signals
$open_signals = db_query(
    "SELECT * FROM signals WHERE status='OPEN' ORDER BY created_at DESC LIMIT 10"
);

// Recent signals (last 5)
$recent_signals = db_query(
    "SELECT * FROM signals ORDER BY created_at DESC LIMIT 5"
);

// Active pairs
$active_pairs = db_query("SELECT * FROM pairs WHERE is_active=TRUE ORDER BY symbol");

// Last 7 days performance
$weekly_stats = db_query(
    "SELECT stat_date, win_rate, net_pips, net_pnl, total_signals
     FROM daily_stats ORDER BY stat_date DESC LIMIT 7"
);

// Bot settings
$bot_active    = get_setting('bot_active', false);
$trading_mode  = get_setting('trading_mode', 'hybrid');
$min_score     = get_setting('min_confluence_score', 80);
$risk_pct      = get_setting('risk_per_trade_pct', 2.0);
$account_bal   = get_setting('account_balance', 1000);

$page_title = 'Dashboard';
require_once __DIR__ . '/../includes/header.php';
?>

<!-- ── Stats Bar ─────────────────────────────────────────────────────────── -->
<div class="stats-grid">
    <div class="stat-card <?= $bot_active ? 'stat-active' : 'stat-inactive' ?>">
        <div class="stat-icon"><?= $bot_active ? '🟢' : '🔴' ?></div>
        <div class="stat-body">
            <div class="stat-value"><?= $bot_active ? 'ACTIVE' : 'INACTIVE' ?></div>
            <div class="stat-label">Bot Status</div>
        </div>
    </div>

    <div class="stat-card">
        <div class="stat-icon">📊</div>
        <div class="stat-body">
            <div class="stat-value"><?= $total ?></div>
            <div class="stat-label">Signals Today</div>
        </div>
    </div>

    <div class="stat-card">
        <div class="stat-icon">🎯</div>
        <div class="stat-body">
            <div class="stat-value"><?= $win_rate ?>%</div>
            <div class="stat-label">Win Rate Today</div>
        </div>
    </div>

    <div class="stat-card <?= ($today_signals['net_pnl'] ?? 0) >= 0 ? 'stat-profit' : 'stat-loss' ?>">
        <div class="stat-icon"><?= ($today_signals['net_pnl'] ?? 0) >= 0 ? '📈' : '📉' ?></div>
        <div class="stat-body">
            <div class="stat-value">$<?= number_format((float)($today_signals['net_pnl'] ?? 0), 2) ?></div>
            <div class="stat-label">Net P&L Today</div>
        </div>
    </div>

    <div class="stat-card">
        <div class="stat-icon">📂</div>
        <div class="stat-body">
            <div class="stat-value"><?= count($open_signals) ?></div>
            <div class="stat-label">Open Signals</div>
        </div>
    </div>

    <div class="stat-card">
        <div class="stat-icon">💰</div>
        <div class="stat-body">
            <div class="stat-value">$<?= number_format($account_bal, 0) ?></div>
            <div class="stat-label">Account Balance</div>
        </div>
    </div>
</div>

<!-- ── Bot Controls ───────────────────────────────────────────────────────── -->
<div class="card">
    <div class="card-header">
        <h2>Bot Controls</h2>
        <div class="badge badge-mode"><?= strtoupper($trading_mode) ?></div>
    </div>
    <div class="card-body controls-row">
        <form method="POST" action="/actions/toggle_bot.php">
            <input type="hidden" name="_csrf" value="<?= csrf_token() ?>">
            <button type="submit" class="btn <?= $bot_active ? 'btn-danger' : 'btn-success' ?>">
                <?= $bot_active ? '⏹ Stop Bot' : '▶ Start Bot' ?>
            </button>
        </form>

        <div class="control-info">
            <span class="badge">Mode: <?= htmlspecialchars($trading_mode) ?></span>
            <span class="badge">Min Score: <?= $min_score ?></span>
            <span class="badge">Risk: <?= $risk_pct ?>%</span>
        </div>

        <a href="/settings.php" class="btn btn-secondary">⚙️ Settings</a>
    </div>
</div>

<!-- ── Open Signals ───────────────────────────────────────────────────────── -->
<?php if ($open_signals): ?>
<div class="card">
    <div class="card-header">
        <h2>Open Signals (<?= count($open_signals) ?>)</h2>
        <a href="/signals.php?status=OPEN" class="btn btn-sm">View All</a>
    </div>
    <div class="table-wrapper">
        <table class="data-table">
            <thead>
                <tr>
                    <th>Signal ID</th>
                    <th>Pair</th>
                    <th>Direction</th>
                    <th>Entry</th>
                    <th>SL</th>
                    <th>TP</th>
                    <th>Score</th>
                    <th>Time</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>
            <?php foreach ($open_signals as $s): ?>
                <tr>
                    <td><code><?= htmlspecialchars($s['signal_id']) ?></code></td>
                    <td><strong><?= htmlspecialchars($s['pair']) ?></strong></td>
                    <td>
                        <span class="badge <?= $s['direction'] === 'BUY' ? 'badge-buy' : 'badge-sell' ?>">
                            <?= $s['direction'] ?>
                        </span>
                    </td>
                    <td><?= number_format((float)$s['entry_price'], 5) ?></td>
                    <td class="text-danger"><?= number_format((float)$s['stop_loss'], 5) ?></td>
                    <td class="text-success"><?= number_format((float)$s['take_profit'], 5) ?></td>
                    <td>
                        <span class="badge badge-score"><?= $s['confluence_score'] ?></span>
                        <small><?= htmlspecialchars($s['quality_label'] ?? '') ?></small>
                    </td>
                    <td><?= date('h:i A', strtotime($s['created_at'])) ?></td>
                    <td>
                        <a href="/signals.php?id=<?= urlencode($s['signal_id']) ?>"
                           class="btn btn-xs">Detail</a>
                    </td>
                </tr>
            <?php endforeach; ?>
            </tbody>
        </table>
    </div>
</div>
<?php endif; ?>

<!-- ── Weekly Performance ─────────────────────────────────────────────────── -->
<?php if ($weekly_stats): ?>
<div class="card">
    <div class="card-header">
        <h2>Last 7 Days Performance</h2>
        <a href="/reports.php" class="btn btn-sm">Full Report</a>
    </div>
    <div class="table-wrapper">
        <table class="data-table">
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Signals</th>
                    <th>Win Rate</th>
                    <th>Net Pips</th>
                    <th>Net P&L</th>
                </tr>
            </thead>
            <tbody>
            <?php foreach ($weekly_stats as $s): ?>
                <tr>
                    <td><?= date('D, M j', strtotime($s['stat_date'])) ?></td>
                    <td><?= (int)$s['total_signals'] ?></td>
                    <td><?= number_format((float)$s['win_rate'], 1) ?>%</td>
                    <td class="<?= $s['net_pips'] >= 0 ? 'text-success' : 'text-danger' ?>">
                        <?= ($s['net_pips'] >= 0 ? '+' : '') . number_format((float)$s['net_pips'], 1) ?>
                    </td>
                    <td class="<?= $s['net_pnl'] >= 0 ? 'text-success' : 'text-danger' ?>">
                        <?= ($s['net_pnl'] >= 0 ? '+$' : '-$') . number_format(abs((float)$s['net_pnl']), 2) ?>
                    </td>
                </tr>
            <?php endforeach; ?>
            </tbody>
        </table>
    </div>
</div>
<?php endif; ?>

<?php require_once __DIR__ . '/../includes/footer.php'; ?>
