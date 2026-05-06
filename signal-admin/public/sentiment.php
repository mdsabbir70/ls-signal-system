<?php
require_once __DIR__ . '/../includes/config.php';
require_once __DIR__ . '/../includes/db.php';
require_once __DIR__ . '/../includes/auth.php';

require_login();
$page_title = 'Market Sentiment';

// ── Load sentiment history from DB ────────────────────────────────
$fng_history = db_query("SELECT value, label, created_at
    FROM sentiment_history WHERE source = 'fear_greed'
    ORDER BY created_at DESC LIMIT 100", []);

$vix_history = db_query("SELECT value, label, created_at
    FROM sentiment_history WHERE source = 'vix'
    ORDER BY created_at DESC LIMIT 100", []);

// ── Latest readings ───────────────────────────────────────────────
$latest_fng = $fng_history[0] ?? null;
$latest_vix = $vix_history[0] ?? null;

// ── Performance from signals ──────────────────────────────────────
$perf = db_one("SELECT
    COUNT(*) as total,
    SUM(status='CLOSED_TP') as wins,
    SUM(status='CLOSED_SL') as losses,
    ROUND(AVG(CASE WHEN status IN ('CLOSED_TP','CLOSED_SL') THEN
        CASE WHEN status='CLOSED_TP' THEN 1 ELSE 0 END END) * 100, 1) as win_rate
    FROM (SELECT status FROM signals
          WHERE status IN ('CLOSED_TP','CLOSED_SL')
          ORDER BY close_time DESC LIMIT 20) as recent", []);

// Count consecutive losses
$recent_signals = db_query("SELECT status FROM signals
    WHERE status IN ('CLOSED_TP','CLOSED_SL')
    ORDER BY close_time DESC LIMIT 10", []);
$consec_losses = 0;
foreach ($recent_signals as $s) {
    if ($s['status'] === 'CLOSED_SL') $consec_losses++;
    else break;
}

require_once __DIR__ . '/../includes/header.php';

// Helper for Fear & Greed gauge color
function fng_color($val) {
    if ($val <= 25) return 'var(--sell)';
    if ($val <= 45) return 'var(--warning)';
    if ($val <= 55) return 'var(--text-muted)';
    if ($val <= 75) return 'var(--warning)';
    return 'var(--buy)';
}
function vix_color($val) {
    if ($val < 15) return 'var(--buy)';
    if ($val < 25) return 'var(--text-muted)';
    if ($val < 35) return 'var(--warning)';
    return 'var(--sell)';
}
?>

<!-- Live Sentiment Cards -->
<div class="stats-grid" style="grid-template-columns: repeat(4, 1fr)">

    <!-- Fear & Greed -->
    <div class="stat-card" id="fng-card" style="border-color:<?= $latest_fng ? fng_color($latest_fng['value']) : 'var(--border)' ?>">
        <div>
            <div class="stat-value" id="fng-value" style="color:<?= $latest_fng ? fng_color($latest_fng['value']) : 'var(--text)' ?>">
                <?= $latest_fng ? round($latest_fng['value']) : '—' ?>
            </div>
            <div class="stat-label">Fear & Greed Index</div>
            <div style="font-size:.75rem;color:var(--text-muted);margin-top:2px" id="fng-label">
                <?= $latest_fng ? htmlspecialchars($latest_fng['label']) : 'Loading...' ?>
            </div>
        </div>
    </div>

    <!-- VIX -->
    <div class="stat-card" style="border-color:<?= $latest_vix ? vix_color($latest_vix['value']) : 'var(--border)' ?>">
        <div>
            <div class="stat-value" style="color:<?= $latest_vix ? vix_color($latest_vix['value']) : 'var(--text)' ?>">
                <?= $latest_vix ? round($latest_vix['value'], 1) : '—' ?>
            </div>
            <div class="stat-label">VIX (Volatility Index)</div>
            <div style="font-size:.75rem;color:var(--text-muted);margin-top:2px">
                <?= $latest_vix ? htmlspecialchars($latest_vix['label']) : 'Loading...' ?>
            </div>
        </div>
    </div>

    <!-- Bot Performance -->
    <div class="stat-card <?= ($perf['win_rate'] ?? 0) >= 55 ? 'stat-profit' : (($perf['win_rate'] ?? 0) >= 45 ? '' : 'stat-loss') ?>">
        <div>
            <div class="stat-value"><?= $perf['win_rate'] ?? '—' ?>%</div>
            <div class="stat-label">Recent Win Rate (20 trades)</div>
            <div style="font-size:.75rem;color:var(--text-muted);margin-top:2px">
                <?= $perf['wins'] ?? 0 ?>W / <?= $perf['losses'] ?? 0 ?>L
            </div>
        </div>
    </div>

    <!-- Consecutive Losses -->
    <div class="stat-card <?= $consec_losses >= 3 ? 'stat-loss' : '' ?>">
        <div>
            <div class="stat-value" style="color:<?= $consec_losses >= 5 ? 'var(--sell)' : ($consec_losses >= 3 ? 'var(--warning)' : 'var(--text)') ?>">
                <?= $consec_losses ?>
            </div>
            <div class="stat-label">Consecutive Losses</div>
            <div style="font-size:.75rem;color:var(--text-muted);margin-top:2px">
                <?= $consec_losses >= 5 ? 'Risk: REDUCE' : ($consec_losses >= 3 ? 'Caution' : 'Normal') ?>
            </div>
        </div>
    </div>
</div>

<!-- Sentiment Gauge Visual -->
<div class="card">
    <div class="card-header">
        <h2>Fear & Greed Gauge</h2>
        <button class="btn btn-sm btn-outline" id="btn-refresh-sentiment">Refresh</button>
    </div>
    <div class="card-body" style="text-align:center">
        <div style="position:relative;display:inline-block;width:300px;height:160px">
            <svg viewBox="0 0 300 160" style="width:100%;height:100%">
                <!-- Gauge background -->
                <path d="M30,150 A120,120 0 0,1 270,150" fill="none" stroke="var(--border)" stroke-width="20" stroke-linecap="round"/>
                <!-- Extreme Fear (red) -->
                <path d="M30,150 A120,120 0 0,1 78,52" fill="none" stroke="#ef4444" stroke-width="20" stroke-linecap="round"/>
                <!-- Fear (orange) -->
                <path d="M78,52 A120,120 0 0,1 126,32" fill="none" stroke="#f59e0b" stroke-width="20" stroke-linecap="round"/>
                <!-- Neutral (gray) -->
                <path d="M126,32 A120,120 0 0,1 174,32" fill="none" stroke="#94a3b8" stroke-width="20" stroke-linecap="round"/>
                <!-- Greed (green) -->
                <path d="M174,32 A120,120 0 0,1 222,52" fill="none" stroke="#22c55e" stroke-width="20" stroke-linecap="round"/>
                <!-- Extreme Greed (bright green) -->
                <path d="M222,52 A120,120 0 0,1 270,150" fill="none" stroke="#16a34a" stroke-width="20" stroke-linecap="round"/>
                <!-- Needle -->
                <?php
                $val = $latest_fng ? $latest_fng['value'] : 50;
                $angle = -90 + ($val / 100) * 180;
                $rad = deg2rad($angle);
                $nx = 150 + cos($rad) * 95;
                $ny = 150 + sin($rad) * 95;
                ?>
                <line x1="150" y1="150" x2="<?= round($nx) ?>" y2="<?= round($ny) ?>" stroke="var(--text)" stroke-width="3" stroke-linecap="round"/>
                <circle cx="150" cy="150" r="6" fill="var(--text)"/>
                <!-- Labels -->
                <text x="25" y="155" fill="var(--text-muted)" font-size="10">0</text>
                <text x="268" y="155" fill="var(--text-muted)" font-size="10">100</text>
                <text x="145" y="20" fill="var(--text-muted)" font-size="10">50</text>
            </svg>
        </div>
        <div style="margin-top:.5rem">
            <span style="font-size:2rem;font-weight:700;color:<?= fng_color($val) ?>"><?= $val ?></span>
            <span style="color:var(--text-muted);margin-left:.5rem"><?= $latest_fng ? htmlspecialchars($latest_fng['label']) : '—' ?></span>
        </div>
        <div style="display:flex;justify-content:center;gap:1.5rem;margin-top:.75rem;font-size:.8rem">
            <span style="color:#ef4444">Extreme Fear (0-25)</span>
            <span style="color:#f59e0b">Fear (25-45)</span>
            <span style="color:#94a3b8">Neutral (45-55)</span>
            <span style="color:#22c55e">Greed (55-75)</span>
            <span style="color:#16a34a">Extreme Greed (75-100)</span>
        </div>
    </div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:1.25rem">

<!-- Fear & Greed History -->
<div class="card">
    <div class="card-header"><h2>Fear & Greed History</h2></div>
    <div class="table-wrapper" style="max-height:400px;overflow-y:auto">
        <table class="data-table">
            <thead><tr><th>Date</th><th>Value</th><th>Label</th></tr></thead>
            <tbody>
            <?php foreach ($fng_history as $row):
                $color = fng_color($row['value']);
            ?>
            <tr>
                <td style="color:var(--text-muted);font-size:.8rem"><?= date('d M Y H:i', strtotime($row['created_at'])) ?></td>
                <td style="color:<?= $color ?>;font-weight:600"><?= round($row['value']) ?></td>
                <td><?= htmlspecialchars($row['label']) ?></td>
            </tr>
            <?php endforeach; ?>
            <?php if (empty($fng_history)): ?>
            <tr><td colspan="3" style="text-align:center;color:var(--text-muted);padding:1.5rem">No data yet — sentiment will be tracked as the bot runs</td></tr>
            <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

<!-- VIX History -->
<div class="card">
    <div class="card-header"><h2>VIX History</h2></div>
    <div class="table-wrapper" style="max-height:400px;overflow-y:auto">
        <table class="data-table">
            <thead><tr><th>Date</th><th>Value</th><th>Label</th></tr></thead>
            <tbody>
            <?php foreach ($vix_history as $row):
                $color = vix_color($row['value']);
            ?>
            <tr>
                <td style="color:var(--text-muted);font-size:.8rem"><?= date('d M Y H:i', strtotime($row['created_at'])) ?></td>
                <td style="color:<?= $color ?>;font-weight:600"><?= round($row['value'], 1) ?></td>
                <td><?= htmlspecialchars($row['label']) ?></td>
            </tr>
            <?php endforeach; ?>
            <?php if (empty($vix_history)): ?>
            <tr><td colspan="3" style="text-align:center;color:var(--text-muted);padding:1.5rem">No data yet — VIX tracked during forex signal cycles</td></tr>
            <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

</div>

<!-- How Sentiment Affects Trading -->
<div class="card">
    <div class="card-header"><h2>How Sentiment Works</h2></div>
    <div class="card-body" style="font-size:.85rem;color:var(--text-muted)">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem">
            <div>
                <h3 style="color:var(--text);font-size:.9rem;margin-bottom:.5rem">Crypto (Fear & Greed)</h3>
                <ul style="list-style:disc;padding-left:1.25rem;line-height:1.8">
                    <li><b style="color:#ef4444">Extreme Fear (0-20)</b>: Contrarian BUY boost (+3.0)</li>
                    <li><b style="color:#f59e0b">Fear (21-40)</b>: Mild BUY bias (+1.5)</li>
                    <li><b style="color:#94a3b8">Neutral (41-60)</b>: No effect</li>
                    <li><b style="color:#22c55e">Greed (61-80)</b>: Mild SELL bias (+1.5)</li>
                    <li><b style="color:#16a34a">Extreme Greed (81-100)</b>: Contrarian SELL boost (+3.0)</li>
                </ul>
            </div>
            <div>
                <h3 style="color:var(--text);font-size:.9rem;margin-bottom:.5rem">Forex (VIX)</h3>
                <ul style="list-style:disc;padding-left:1.25rem;line-height:1.8">
                    <li><b style="color:var(--buy)">Low (&lt;15)</b>: Trend-following boost (+1.0)</li>
                    <li><b style="color:var(--text-muted)">Normal (15-25)</b>: Standard conditions</li>
                    <li><b style="color:var(--warning)">Elevated (25-35)</b>: Safe-haven flows, reduce size</li>
                    <li><b style="color:var(--sell)">Extreme (&gt;35)</b>: Max caution, gold/JPY/CHF rally</li>
                </ul>
                <h3 style="color:var(--text);font-size:.9rem;margin:1rem 0 .5rem">Performance Guard</h3>
                <ul style="list-style:disc;padding-left:1.25rem;line-height:1.8">
                    <li><b>3+ consecutive losses</b>: Score penalty (-1.0)</li>
                    <li><b>5+ consecutive losses</b>: Score penalty (-2.0) + reduce risk</li>
                    <li><b>Declining win rate &lt;40%</b>: Additional penalty (-1.0)</li>
                </ul>
            </div>
        </div>
    </div>
</div>

<script>
document.getElementById('btn-refresh-sentiment')?.addEventListener('click', async function() {
    this.textContent = 'Loading...';
    this.disabled = true;
    try {
        const res = await fetch('/actions/sentiment_current.php');
        const json = await res.json();
        if (json.success) {
            // Reload page to update gauge & all cards from DB
            location.reload();
        } else {
            alert('Failed: ' + (json.error || 'Unknown error'));
        }
    } catch (e) {
        alert('Failed to fetch sentiment: ' + e.message);
    }
    this.textContent = 'Refresh';
    this.disabled = false;
});
</script>

<?php require_once __DIR__ . '/../includes/footer.php'; ?>
