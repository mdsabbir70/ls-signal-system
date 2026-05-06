<?php
require_once __DIR__ . '/../includes/config.php';
require_once __DIR__ . '/../includes/db.php';
require_once __DIR__ . '/../includes/auth.php';

require_login();
$page_title = 'Backtest';

// ── Load all pairs for dropdown ────────────────────────────────────
$pairs = db_query("SELECT symbol FROM pairs ORDER BY category, symbol", []);

// ── Load past backtest results ─────────────────────────────────────
$results = db_query("SELECT backtest_id, strategy_name, pair, timeframe,
    start_date, end_date, total_signals, wins, losses,
    win_rate, net_pips, profit_factor, max_drawdown, avg_rr, sharpe_ratio, settings_json, created_at
    FROM backtest_results ORDER BY created_at DESC LIMIT 50", []);

// ── Load single result detail if requested ─────────────────────────
$detail = null;
$detail_trades = [];
if (!empty($_GET['id'])) {
    $detail = db_one("SELECT * FROM backtest_results WHERE backtest_id = ?", [$_GET['id']]);
    if ($detail && !empty($detail['trades_json'])) {
        $detail_trades = json_decode($detail['trades_json'], true) ?: [];
    }
}

require_once __DIR__ . '/../includes/header.php';
?>

<!-- Run New Backtest Form -->
<div class="card">
    <div class="card-header">
        <h2>Run Backtest</h2>
        <span id="bt-status-badge" class="badge" style="display:none"></span>
    </div>
    <div class="card-body">
        <form id="backtest-form" class="controls-row" style="flex-wrap:wrap;gap:.75rem">
            <div class="form-group" style="margin-bottom:0">
                <label>Pair</label>
                <select name="pair" class="form-select" style="max-width:140px">
                    <?php foreach ($pairs as $p): ?>
                    <option value="<?= $p['symbol'] ?>"><?= $p['symbol'] ?></option>
                    <?php endforeach; ?>
                </select>
            </div>
            <div class="form-group" style="margin-bottom:0">
                <label>Timeframe</label>
                <select name="timeframe" class="form-select" style="max-width:90px">
                    <option value="M5">M5</option>
                    <option value="M15">M15</option>
                    <option value="M30">M30</option>
                    <option value="H1" selected>H1</option>
                    <option value="H4">H4</option>
                    <option value="D1">D1</option>
                </select>
            </div>
            <div class="form-group" style="margin-bottom:0">
                <label>Start Date</label>
                <input type="date" name="start_date" class="form-input" value="2024-01-01" style="max-width:160px">
            </div>
            <div class="form-group" style="margin-bottom:0">
                <label>End Date</label>
                <input type="date" name="end_date" class="form-input" value="2026-05-01" style="max-width:160px">
            </div>
            <div class="form-group" style="margin-bottom:0">
                <label>Min Score</label>
                <input type="number" name="min_score" class="form-input" value="80" min="50" max="100" step="5" style="max-width:80px">
            </div>
            <div class="form-group" style="margin-bottom:0">
                <label>SL ATR x</label>
                <input type="number" name="sl_atr_mult" class="form-input" value="1.5" min="0.5" max="5" step="0.5" style="max-width:80px">
            </div>
            <div class="form-group" style="margin-bottom:0">
                <label>TP ATR x</label>
                <input type="number" name="tp_atr_mult" class="form-input" value="2.0" min="0.5" max="10" step="0.5" style="max-width:80px">
            </div>
            <div class="form-group" style="margin-bottom:0">
                <label>Mode</label>
                <select name="trading_mode" class="form-select" style="max-width:180px">
                    <option value="technical" selected>Technical</option>
                    <option value="news">News</option>
                    <option value="hybrid">Hybrid</option>
                    <option value="ai">AI</option>
                    <option value="technical_news_filter">Tech + News Filter</option>
                </select>
            </div>
            <div class="form-group" style="margin-bottom:0;align-self:flex-end">
                <button type="submit" class="btn btn-primary" id="btn-run-bt">Run Backtest</button>
            </div>
        </form>
        <div id="bt-progress" style="display:none;margin-top:1rem">
            <div style="display:flex;align-items:center;gap:.75rem">
                <div class="spinner"></div>
                <span id="bt-progress-text" style="color:var(--text-muted)">Starting backtest...</span>
            </div>
        </div>
        <div id="bt-result-msg" style="display:none;margin-top:1rem"></div>
    </div>
</div>

<?php if ($detail): ?>
<!-- Single Backtest Detail -->
<div class="card" id="detail-card">
    <div class="card-header">
        <h2>Backtest: <?= htmlspecialchars($detail['backtest_id']) ?></h2>
        <span class="badge badge-score"><?= htmlspecialchars($detail['pair']) ?> <?= htmlspecialchars($detail['timeframe']) ?></span>
    </div>
    <div class="card-body">
        <div class="stats-grid">
            <div class="stat-card">
                <div><div class="stat-value"><?= $detail['total_signals'] ?></div><div class="stat-label">Signals</div></div>
            </div>
            <div class="stat-card <?= $detail['win_rate'] >= 55 ? 'stat-profit' : ($detail['win_rate'] >= 45 ? '' : 'stat-loss') ?>">
                <div><div class="stat-value"><?= round($detail['win_rate'], 1) ?>%</div><div class="stat-label">Win Rate (<?= $detail['wins'] ?>W / <?= $detail['losses'] ?>L)</div></div>
            </div>
            <div class="stat-card <?= $detail['net_pips'] >= 0 ? 'stat-profit' : 'stat-loss' ?>">
                <div><div class="stat-value"><?= $detail['net_pips'] >= 0 ? '+' : '' ?><?= round($detail['net_pips'], 1) ?></div><div class="stat-label">Net Pips</div></div>
            </div>
            <div class="stat-card <?= $detail['profit_factor'] >= 1.5 ? 'stat-profit' : ($detail['profit_factor'] >= 1 ? '' : 'stat-loss') ?>">
                <div><div class="stat-value"><?= round($detail['profit_factor'], 2) ?></div><div class="stat-label">Profit Factor</div></div>
            </div>
            <div class="stat-card">
                <div><div class="stat-value"><?= round($detail['max_drawdown'], 1) ?></div><div class="stat-label">Max DD (pips)</div></div>
            </div>
            <div class="stat-card">
                <div><div class="stat-value"><?= round($detail['avg_rr'], 2) ?></div><div class="stat-label">Avg R:R</div></div>
            </div>
            <div class="stat-card">
                <div><div class="stat-value"><?= round($detail['sharpe_ratio'], 2) ?></div><div class="stat-label">Sharpe Ratio</div></div>
            </div>
            <div class="stat-card">
                <div><div class="stat-value"><?= $detail['start_date'] ?></div><div class="stat-label">to <?= $detail['end_date'] ?></div></div>
            </div>
        </div>

        <?php
        $settings = json_decode($detail['settings_json'] ?? '{}', true);
        if ($settings): ?>
        <div style="margin-bottom:1rem;color:var(--text-muted);font-size:.85rem">
            Settings: Min Score <?= $settings['min_score'] ?? '?' ?> | SL ATR x<?= $settings['sl_atr_mult'] ?? '?' ?> | TP ATR x<?= $settings['tp_atr_mult'] ?? '?' ?> | Mode: <?= strtoupper($settings['trading_mode'] ?? '?') ?>
        </div>
        <?php endif; ?>

        <?php if (!empty($detail_trades)): ?>
        <h3 style="margin:1rem 0 .5rem;font-size:.95rem">Trade Log (<?= count($detail_trades) ?> trades)</h3>
        <div class="table-wrapper" style="max-height:500px;overflow-y:auto">
            <table class="data-table">
                <thead><tr>
                    <th>#</th><th>Time</th><th>Dir</th><th>Entry</th><th>SL</th><th>TP</th>
                    <th>Score</th><th>Result</th><th>Pips</th><th>Bars</th>
                </tr></thead>
                <tbody>
                <?php foreach ($detail_trades as $idx => $t):
                    $is_win = ($t['result'] ?? '') === 'TP';
                    $res_color = $is_win ? 'var(--buy)' : (($t['result'] ?? '') === 'SL' ? 'var(--sell)' : 'var(--warning)');
                    $pips = round($t['pips'] ?? 0, 1);
                ?>
                <tr>
                    <td style="color:var(--text-muted)"><?= $idx + 1 ?></td>
                    <td style="font-size:.8rem"><?= htmlspecialchars(substr($t['time'] ?? '', 0, 16)) ?></td>
                    <td>
                        <span class="badge <?= ($t['dir'] ?? '') === 'BUY' ? 'badge-buy' : 'badge-sell' ?>">
                            <?= $t['dir'] ?? '?' ?>
                        </span>
                    </td>
                    <td style="font-family:monospace"><?= $t['entry'] ?? '' ?></td>
                    <td style="font-family:monospace;color:var(--sell)"><?= $t['sl'] ?? '' ?></td>
                    <td style="font-family:monospace;color:var(--buy)"><?= $t['tp'] ?? '' ?></td>
                    <td><span class="badge badge-score"><?= round($t['score'] ?? 0) ?></span></td>
                    <td style="color:<?= $res_color ?>;font-weight:600"><?= $t['result'] ?? '?' ?></td>
                    <td style="color:<?= $pips >= 0 ? 'var(--buy)' : 'var(--sell)' ?>;font-weight:500">
                        <?= $pips >= 0 ? '+' : '' ?><?= $pips ?>
                    </td>
                    <td style="color:var(--text-muted)"><?= $t['bars'] ?? '' ?></td>
                </tr>
                <?php endforeach; ?>
                </tbody>
            </table>
        </div>
        <?php endif; ?>
    </div>
</div>
<?php endif; ?>

<!-- Past Backtest Results -->
<div class="card">
    <div class="card-header">
        <h2>Backtest History</h2>
        <span class="badge"><?= count($results) ?> results</span>
    </div>
    <div class="table-wrapper">
        <table class="data-table">
            <thead><tr>
                <th>ID</th><th>Pair</th><th>TF</th><th>Period</th>
                <th>Min Score</th><th>SL/TP</th><th>Mode</th>
                <th>Signals</th><th>W/L</th><th>Win%</th>
                <th>Net Pips</th><th>PF</th><th>Sharpe</th><th>DD</th>
                <th>Date</th><th></th>
            </tr></thead>
            <tbody>
            <?php foreach ($results as $row):
                $wr = round($row['win_rate'], 1);
                $np = round($row['net_pips'], 1);
                $pf = round($row['profit_factor'], 2);
                $wr_color = $wr >= 55 ? 'var(--buy)' : ($wr >= 45 ? 'var(--warning)' : 'var(--sell)');
                $np_color = $np >= 0 ? 'var(--buy)' : 'var(--sell)';
                $pf_color = $pf >= 1.5 ? 'var(--buy)' : ($pf >= 1 ? 'var(--warning)' : 'var(--sell)');
                $settings = json_decode($row['settings_json'] ?? '{}', true);
                $min_sc = $settings['min_score'] ?? '—';
                $sl_m = $settings['sl_atr_mult'] ?? '—';
                $tp_m = $settings['tp_atr_mult'] ?? '—';
                $mode = $settings['trading_mode'] ?? '—';
                $mode_short = ['technical'=>'Tech','news'=>'News','hybrid'=>'Hybrid','ai'=>'AI','technical_news_filter'=>'Tech+NF'];
            ?>
            <tr>
                <td style="font-family:monospace;font-size:.75rem">
                    <a href="?id=<?= urlencode($row['backtest_id']) ?>"><?= htmlspecialchars(substr($row['backtest_id'], 0, 18)) ?></a>
                </td>
                <td><strong><?= $row['pair'] ?></strong></td>
                <td><?= $row['timeframe'] ?></td>
                <td style="font-size:.8rem;color:var(--text-muted)"><?= $row['start_date'] ?><br><?= $row['end_date'] ?></td>
                <td style="font-weight:600"><?= $min_sc ?></td>
                <td style="font-size:.8rem"><?= $sl_m ?> / <?= $tp_m ?></td>
                <td><span class="badge" style="font-size:.7rem"><?= $mode_short[$mode] ?? strtoupper($mode) ?></span></td>
                <td><?= $row['total_signals'] ?></td>
                <td>
                    <span style="color:var(--buy)"><?= $row['wins'] ?></span> /
                    <span style="color:var(--sell)"><?= $row['losses'] ?></span>
                </td>
                <td style="color:<?= $wr_color ?>;font-weight:600"><?= $wr ?>%</td>
                <td style="color:<?= $np_color ?>;font-weight:500"><?= $np >= 0 ? '+' : '' ?><?= $np ?></td>
                <td style="color:<?= $pf_color ?>"><?= $pf ?></td>
                <td><?= round($row['sharpe_ratio'], 2) ?></td>
                <td><?= round($row['max_drawdown'], 1) ?></td>
                <td style="font-size:.8rem;color:var(--text-muted)"><?= date('d M Y H:i', strtotime($row['created_at'])) ?></td>
                <td>
                    <button class="btn btn-xs btn-danger btn-delete-bt" data-id="<?= htmlspecialchars($row['backtest_id']) ?>">Del</button>
                </td>
            </tr>
            <?php endforeach; ?>
            <?php if (empty($results)): ?>
            <tr><td colspan="16" style="text-align:center;color:var(--text-muted);padding:2rem">
                No backtest results yet. Run your first backtest above.
            </td></tr>
            <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

<style>
.spinner {
    width: 20px; height: 20px;
    border: 3px solid var(--border);
    border-top-color: var(--primary);
    border-radius: 50%;
    animation: spin .8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>

<script>
// Run backtest (via PHP proxy → server-side curl)
document.getElementById('backtest-form').addEventListener('submit', async function(e) {
    e.preventDefault();
    const form = new FormData(this);

    const btn = document.getElementById('btn-run-bt');
    const progress = document.getElementById('bt-progress');
    const progressText = document.getElementById('bt-progress-text');
    const resultMsg = document.getElementById('bt-result-msg');
    const badge = document.getElementById('bt-status-badge');

    btn.disabled = true;
    btn.textContent = 'Running...';
    progress.style.display = 'block';
    resultMsg.style.display = 'none';
    progressText.textContent = `Starting backtest for ${form.get('pair')} ${form.get('timeframe')}...`;

    try {
        const res = await fetch('/actions/backtest_run.php', { method: 'POST', body: form });
        const json = await res.json();

        if (!json.success) {
            throw new Error(json.error || 'Failed to start backtest');
        }

        const btId = json.backtest_id;
        progressText.textContent = `Backtest ${btId} running... This may take several minutes.`;
        badge.textContent = 'RUNNING';
        badge.style.display = 'inline-flex';
        badge.style.background = 'rgba(245,158,11,.15)';
        badge.style.color = 'var(--warning)';

        // Poll for completion (via PHP proxy)
        const poll = setInterval(async () => {
            try {
                const statusRes = await fetch('/actions/backtest_status.php');
                const statusJson = await statusRes.json();
                const bt = statusJson.backtests?.[btId];

                if (bt && bt.status === 'completed') {
                    clearInterval(poll);
                    progress.style.display = 'none';
                    badge.textContent = 'DONE';
                    badge.style.background = 'rgba(34,197,94,.15)';
                    badge.style.color = 'var(--buy)';

                    const s = bt.summary || {};
                    resultMsg.style.display = 'block';
                    resultMsg.innerHTML = `<div class="alert alert-success">
                        Backtest complete! ${s.total_signals || 0} signals | Win Rate: ${s.win_rate || 0}% | Net: ${(s.net_pips||0) >= 0 ? '+':''}${s.net_pips || 0} pips | PF: ${s.profit_factor || 0}
                        &nbsp; <a href="?id=${encodeURIComponent(bt.backtest_id || btId)}" class="btn btn-sm btn-primary">View Details</a>
                    </div>`;
                    btn.disabled = false;
                    btn.textContent = 'Run Backtest';
                } else if (bt && bt.status === 'failed') {
                    clearInterval(poll);
                    progress.style.display = 'none';
                    badge.textContent = 'FAILED';
                    badge.style.background = 'rgba(239,68,68,.15)';
                    badge.style.color = 'var(--sell)';
                    resultMsg.style.display = 'block';
                    resultMsg.innerHTML = `<div class="alert alert-danger">Backtest failed: ${bt.error || 'Unknown error'}</div>`;
                    btn.disabled = false;
                    btn.textContent = 'Run Backtest';
                } else {
                    progressText.textContent = `Backtest ${btId} still running... (be patient, large datasets take time)`;
                }
            } catch (err) {
                // Keep polling on network errors
            }
        }, 5000);

    } catch (err) {
        progress.style.display = 'none';
        resultMsg.style.display = 'block';
        resultMsg.innerHTML = `<div class="alert alert-danger">${err.message}</div>`;
        btn.disabled = false;
        btn.textContent = 'Run Backtest';
    }
});

// Delete backtest (via PHP proxy)
document.querySelectorAll('.btn-delete-bt').forEach(btn => {
    btn.addEventListener('click', async function() {
        const id = this.dataset.id;
        if (!confirm(`Delete backtest ${id}?`)) return;
        const row = this.closest('tr');
        try {
            const form = new FormData();
            form.append('backtest_id', id);
            const res = await fetch('/actions/backtest_delete.php', { method: 'POST', body: form });
            const json = await res.json();
            if (json.success) {
                row.remove();
            } else {
                alert(json.error || 'Delete failed');
            }
        } catch (err) {
            alert('Delete failed: ' + err.message);
        }
    });
});
</script>

<?php require_once __DIR__ . '/../includes/footer.php'; ?>
