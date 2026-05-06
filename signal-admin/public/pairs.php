<?php
require_once __DIR__ . '/../includes/config.php';
require_once __DIR__ . '/../includes/db.php';
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/bot_api.php';

require_login();

// Handle toggle
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['toggle_pair'])) {
    if (verify_csrf($_POST['_csrf'] ?? '')) {
        $symbol = $_POST['symbol'];
        $row = db_one("SELECT is_active FROM pairs WHERE symbol = ?", [$symbol]);
        if ($row) {
            $new = $row['is_active'] ? 0 : 1;
            db_exec("UPDATE pairs SET is_active = ? WHERE symbol = ?", [$new, $symbol]);
        }
    }
    header('Location: /pairs.php');
    exit;
}

$pairs = db_query("SELECT * FROM pairs ORDER BY category, symbol");

$page_title = 'Pairs';
require_once __DIR__ . '/../includes/header.php';
?>

<div class="card">
    <div class="card-header">
        <h2>Trading Pairs</h2>
        <span class="text-muted"><?= count(array_filter($pairs, fn($p) => $p['is_active'])) ?> active</span>
    </div>
    <div class="table-wrapper">
        <table class="data-table">
            <thead>
                <tr>
                    <th>Pair</th>
                    <th>Category</th>
                    <th>Status</th>
                    <th>Signals</th>
                    <th>Win Rate</th>
                    <th>Total Pips</th>
                    <th>Last Signal</th>
                    <th>Toggle</th>
                </tr>
            </thead>
            <tbody>
            <?php foreach ($pairs as $p): ?>
                <tr>
                    <td><strong><?= htmlspecialchars($p['symbol']) ?></strong>
                        <small class="text-muted"><?= htmlspecialchars($p['display_name'] ?? '') ?></small>
                    </td>
                    <td><?= ucfirst(htmlspecialchars($p['category'])) ?></td>
                    <td>
                        <?php if ($p['is_active']): ?>
                        <span class="badge badge-buy">Active</span>
                        <?php else: ?>
                        <span class="badge">Inactive</span>
                        <?php endif; ?>
                    </td>
                    <td><?= (int)$p['total_signals'] ?></td>
                    <td><?= $p['total_signals'] > 0
                            ? number_format((float)$p['win_rate'], 1) . '%'
                            : '—' ?></td>
                    <td class="<?= ($p['total_pips'] ?? 0) >= 0 ? 'text-success' : 'text-danger' ?>">
                        <?= $p['total_signals'] > 0
                            ? (($p['total_pips'] >= 0 ? '+' : '') . number_format((float)$p['total_pips'], 1))
                            : '—' ?>
                    </td>
                    <td>
                        <?= $p['last_signal_at']
                            ? date('M j, h:i A', strtotime($p['last_signal_at']))
                            : '—' ?>
                    </td>
                    <td>
                        <form method="POST" action="/pairs.php" style="display:inline">
                            <input type="hidden" name="_csrf" value="<?= csrf_token() ?>">
                            <input type="hidden" name="toggle_pair" value="1">
                            <input type="hidden" name="symbol" value="<?= htmlspecialchars($p['symbol']) ?>">
                            <button type="submit"
                                    class="btn btn-xs <?= $p['is_active'] ? 'btn-danger' : 'btn-success' ?>">
                                <?= $p['is_active'] ? 'Disable' : 'Enable' ?>
                            </button>
                        </form>
                    </td>
                </tr>
            <?php endforeach; ?>
            </tbody>
        </table>
    </div>
</div>

<?php require_once __DIR__ . '/../includes/footer.php'; ?>
