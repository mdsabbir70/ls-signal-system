<?php
require_once __DIR__ . '/../includes/config.php';
require_once __DIR__ . '/../includes/db.php';
require_once __DIR__ . '/../includes/auth.php';

require_login();
$page_title = 'Reports';

// Period filter
$period = $_GET['period'] ?? '30';
$pair   = $_GET['pair']   ?? '';
$days   = in_array($period, ['7','14','30','60','90','all']) ? $period : '30';
$date_cond = $days === 'all' ? '1=1' : "created_at >= DATE_SUB(NOW(), INTERVAL {$days} DAY)";
$pair_cond  = $pair ? "AND pair = " . get_db()->quote($pair) : '';

// ── Overall summary ───────────────────────────────────────────────
$summary = db_one("SELECT
    COUNT(*) as total,
    SUM(status='CLOSED_TP') as wins,
    SUM(status='CLOSED_SL') as losses,
    SUM(status='OPEN') as open_count,
    SUM(status='CANCELLED') as cancelled,
    ROUND(AVG(confluence_score),1) as avg_score,
    ROUND(SUM(CASE WHEN status='CLOSED_TP' THEN actual_pips ELSE 0 END),1) as pips_won,
    ROUND(SUM(CASE WHEN status='CLOSED_SL' THEN ABS(actual_pips) ELSE 0 END),1) as pips_lost,
    ROUND(SUM(CASE WHEN actual_profit > 0 THEN actual_profit ELSE 0 END),2) as gross_profit,
    ROUND(SUM(CASE WHEN actual_profit < 0 THEN ABS(actual_profit) ELSE 0 END),2) as gross_loss,
    ROUND(AVG(CASE WHEN status IN ('CLOSED_TP','CLOSED_SL') THEN duration_minutes END),0) as avg_duration,
    ROUND(AVG(risk_reward_ratio),2) as avg_rr
    FROM signals WHERE $date_cond $pair_cond", []);

$total    = $summary['total'] ?? 0;
$wins     = $summary['wins']  ?? 0;
$losses   = $summary['losses'] ?? 0;
$closed   = $wins + $losses;
$win_rate = $closed > 0 ? round($wins / $closed * 100, 1) : 0;
$net_pips = ($summary['pips_won'] ?? 0) - ($summary['pips_lost'] ?? 0);
$net_pnl  = ($summary['gross_profit'] ?? 0) - ($summary['gross_loss'] ?? 0);
$pf       = ($summary['gross_loss'] ?? 0) > 0
            ? round($summary['gross_profit'] / $summary['gross_loss'], 2) : 0;

// ── Per-pair breakdown ────────────────────────────────────────────
$by_pair = db_query("SELECT pair,
    COUNT(*) as total,
    SUM(status='CLOSED_TP') as wins,
    SUM(status='CLOSED_SL') as losses,
    ROUND(SUM(CASE WHEN status='CLOSED_TP' THEN actual_pips ELSE 0 END) -
          SUM(CASE WHEN status='CLOSED_SL' THEN ABS(actual_pips) ELSE 0 END),1) as net_pips,
    ROUND(SUM(IFNULL(actual_profit,0)),2) as net_pnl,
    ROUND(AVG(confluence_score),1) as avg_score
    FROM signals WHERE $date_cond
    GROUP BY pair ORDER BY total DESC", []);

// ── Daily stats (last 30 rows) ────────────────────────────────────
$daily = db_query("SELECT stat_date, total_signals, closed_tp, closed_sl,
    win_rate, net_pips, net_pnl, profit_factor
    FROM daily_stats
    ORDER BY stat_date DESC LIMIT 30", []);

// ── Mode breakdown ────────────────────────────────────────────────
$by_mode = db_query("SELECT mode,
    COUNT(*) as total,
    SUM(status='CLOSED_TP') as wins,
    SUM(status='CLOSED_SL') as losses,
    ROUND(AVG(confluence_score),1) as avg_score
    FROM signals WHERE $date_cond $pair_cond
    GROUP BY mode ORDER BY total DESC", []);

// ── Recent closed signals ─────────────────────────────────────────
$recent = db_query("SELECT signal_id, pair, direction, status,
    actual_pips, actual_profit, confluence_score, created_at, close_time, duration_minutes
    FROM signals
    WHERE status IN ('CLOSED_TP','CLOSED_SL','CLOSED_MANUAL') $pair_cond
    ORDER BY close_time DESC LIMIT 15", []);

// ── Available pairs ───────────────────────────────────────────────
$pairs_list = db_query("SELECT DISTINCT pair FROM signals ORDER BY pair", []);

require_once __DIR__ . '/../includes/header.php';

// Helper
function fmt_mins($m) {
    if (!$m) return '—';
    if ($m < 60) return $m . 'm';
    return round($m/60,1) . 'h';
}
?>

<!-- Period + Pair filter -->
<div class="card" style="margin-bottom:1.25rem">
    <div class="card-body">
        <form method="GET" class="controls-row">
            <label style="color:var(--text-muted);font-size:.85rem">Period:</label>
            <?php foreach (['7'=>'7 Days','14'=>'14 Days','30'=>'30 Days','60'=>'60 Days','90'=>'90 Days','all'=>'All Time'] as $v => $l): ?>
            <a href="?period=<?= $v ?>&pair=<?= urlencode($pair) ?>"
               class="btn btn-sm <?= $days===$v ? 'btn-primary':'btn-outline' ?>"><?= $l ?></a>
            <?php endforeach; ?>
            <select name="pair" class="form-select" style="max-width:130px;margin-left:.5rem" onchange="this.form.submit()">
                <option value="">All Pairs</option>
                <?php foreach ($pairs_list as $p): ?>
                <option value="<?= $p['pair'] ?>" <?= $pair===$p['pair']?'selected':'' ?>><?= $p['pair'] ?></option>
                <?php endforeach; ?>
            </select>
        </form>
    </div>
</div>

<!-- Summary stats -->
<div class="stats-grid">
    <div class="stat-card">
        <div class="stat-value"><?= $total ?></div>
        <div class="stat-label">Total Signals</div>
    </div>
    <div class="stat-card <?= $win_rate >= 60 ? 'stat-profit' : ($win_rate >= 40 ? '' : 'stat-loss') ?>">
        <div class="stat-value"><?= $win_rate ?>%</div>
        <div class="stat-label">Win Rate (<?= $closed ?> closed)</div>
    </div>
    <div class="stat-card <?= $net_pips >= 0 ? 'stat-profit' : 'stat-loss' ?>">
        <div class="stat-value"><?= $net_pips >= 0 ? '+' : '' ?><?= $net_pips ?></div>
        <div class="stat-label">Net Pips</div>
    </div>
    <div class="stat-card <?= $net_pnl >= 0 ? 'stat-profit' : 'stat-loss' ?>">
        <div class="stat-value">$<?= number_format($net_pnl, 2) ?></div>
        <div class="stat-label">Net P&L</div>
    </div>
    <div class="stat-card <?= $pf >= 1.5 ? 'stat-profit' : ($pf >= 1 ? '' : 'stat-loss') ?>">
        <div class="stat-value"><?= $pf ?></div>
        <div class="stat-label">Profit Factor</div>
    </div>
    <div class="stat-card">
        <div class="stat-value"><?= $summary['avg_score'] ?? '—' ?></div>
        <div class="stat-label">Avg Confluence</div>
    </div>
    <div class="stat-card">
        <div class="stat-value"><?= fmt_mins($summary['avg_duration'] ?? 0) ?></div>
        <div class="stat-label">Avg Duration</div>
    </div>
    <div class="stat-card">
        <div class="stat-value"><?= $summary['avg_rr'] ?? '—' ?></div>
        <div class="stat-label">Avg R:R</div>
    </div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:1.25rem">

<!-- Per-pair breakdown -->
<div class="card">
    <div class="card-header"><h2>💱 By Pair</h2></div>
    <div class="table-wrapper">
        <table class="data-table">
            <thead><tr>
                <th>Pair</th><th>Total</th><th>W</th><th>L</th>
                <th>Win%</th><th>Net Pips</th><th>Net P&L</th><th>Score</th>
            </tr></thead>
            <tbody>
            <?php foreach ($by_pair as $row):
                $w = $row['wins']; $l = $row['losses'];
                $wr = ($w+$l) > 0 ? round($w/($w+$l)*100) : 0;
                $pip_color = $row['net_pips'] >= 0 ? 'var(--buy)' : 'var(--sell)';
                $pnl_color = $row['net_pnl']  >= 0 ? 'var(--buy)' : 'var(--sell)';
            ?>
            <tr>
                <td><strong><?= $row['pair'] ?></strong></td>
                <td><?= $row['total'] ?></td>
                <td style="color:var(--buy)"><?= $w ?></td>
                <td style="color:var(--sell)"><?= $l ?></td>
                <td><?= $wr ?>%</td>
                <td style="color:<?= $pip_color ?>"><?= $row['net_pips'] >= 0 ? '+':'' ?><?= $row['net_pips'] ?></td>
                <td style="color:<?= $pnl_color ?>">$<?= number_format($row['net_pnl'],2) ?></td>
                <td><?= $row['avg_score'] ?></td>
            </tr>
            <?php endforeach; ?>
            <?php if (empty($by_pair)): ?>
            <tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:1.5rem">No data</td></tr>
            <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

<!-- By mode -->
<div class="card">
    <div class="card-header"><h2>⚙️ By Strategy Mode</h2></div>
    <div class="table-wrapper">
        <table class="data-table">
            <thead><tr>
                <th>Mode</th><th>Total</th><th>Wins</th><th>Losses</th><th>Win%</th><th>Avg Score</th>
            </tr></thead>
            <tbody>
            <?php foreach ($by_mode as $row):
                $w = $row['wins']; $l = $row['losses'];
                $wr = ($w+$l) > 0 ? round($w/($w+$l)*100) : 0;
            ?>
            <tr>
                <td><span class="badge" style="background:rgba(59,130,246,.15);color:var(--primary)"><?= strtoupper($row['mode']) ?></span></td>
                <td><?= $row['total'] ?></td>
                <td style="color:var(--buy)"><?= $w ?></td>
                <td style="color:var(--sell)"><?= $l ?></td>
                <td><?= $wr ?>%</td>
                <td><?= $row['avg_score'] ?></td>
            </tr>
            <?php endforeach; ?>
            <?php if (empty($by_mode)): ?>
            <tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:1.5rem">No data</td></tr>
            <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

</div>

<!-- Daily stats table -->
<div class="card">
    <div class="card-header">
        <h2>📅 Daily Performance</h2>
    </div>
    <div class="table-wrapper">
        <table class="data-table">
            <thead><tr>
                <th>Date</th><th>Signals</th><th>TP</th><th>SL</th>
                <th>Win Rate</th><th>Net Pips</th><th>Net P&L</th><th>Prof. Factor</th>
            </tr></thead>
            <tbody>
            <?php foreach ($daily as $row):
                $pnl_color = $row['net_pnl'] >= 0 ? 'var(--buy)' : 'var(--sell)';
                $pip_color = $row['net_pips'] >= 0 ? 'var(--buy)' : 'var(--sell)';
                $wr_color  = $row['win_rate'] >= 60 ? 'var(--buy)' : ($row['win_rate'] >= 40 ? 'var(--warning)' : 'var(--sell)');
            ?>
            <tr>
                <td><?= date('d M Y', strtotime($row['stat_date'])) ?></td>
                <td><?= $row['total_signals'] ?></td>
                <td style="color:var(--buy)"><?= $row['closed_tp'] ?></td>
                <td style="color:var(--sell)"><?= $row['closed_sl'] ?></td>
                <td style="color:<?= $wr_color ?>"><?= $row['win_rate'] ?>%</td>
                <td style="color:<?= $pip_color ?>"><?= $row['net_pips'] >= 0 ? '+':'' ?><?= $row['net_pips'] ?></td>
                <td style="color:<?= $pnl_color ?>">$<?= number_format($row['net_pnl'],2) ?></td>
                <td><?= $row['profit_factor'] ?? '—' ?></td>
            </tr>
            <?php endforeach; ?>
            <?php if (empty($daily)): ?>
            <tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:1.5rem">No daily stats yet</td></tr>
            <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

<!-- Recent closed signals -->
<div class="card">
    <div class="card-header"><h2>🕐 Recent Closed Signals</h2></div>
    <div class="table-wrapper">
        <table class="data-table">
            <thead><tr>
                <th>ID</th><th>Pair</th><th>Dir</th><th>Result</th>
                <th>Pips</th><th>P&L</th><th>Score</th><th>Duration</th><th>Closed</th>
            </tr></thead>
            <tbody>
            <?php foreach ($recent as $row):
                $is_win  = $row['status'] === 'CLOSED_TP';
                $res_color = $is_win ? 'var(--buy)' : 'var(--sell)';
                $pips    = $row['actual_pips'];
                $pnl     = $row['actual_profit'];
            ?>
            <tr>
                <td style="font-family:monospace;font-size:.75rem"><?= substr($row['signal_id'],0,12) ?>…</td>
                <td><strong><?= $row['pair'] ?></strong></td>
                <td>
                    <span class="badge" style="background:<?= $row['direction']==='BUY'?'rgba(34,197,94,.2)':'rgba(239,68,68,.2)' ?>;color:<?= $row['direction']==='BUY'?'var(--buy)':'var(--sell)' ?>">
                        <?= $row['direction'] ?>
                    </span>
                </td>
                <td style="color:<?= $res_color ?>;font-weight:600">
                    <?= $is_win ? '✓ TP' : '✗ SL' ?>
                </td>
                <td style="color:<?= $res_color ?>"><?= $pips !== null ? ($pips >= 0 ? '+':'').$pips : '—' ?></td>
                <td style="color:<?= ($pnl??0) >= 0 ? 'var(--buy)':'var(--sell)' ?>">
                    <?= $pnl !== null ? '$'.number_format($pnl,2) : '—' ?>
                </td>
                <td><?= $row['confluence_score'] ?></td>
                <td><?= fmt_mins($row['duration_minutes']) ?></td>
                <td style="color:var(--text-muted);font-size:.8rem">
                    <?= $row['close_time'] ? date('d M, h:i A', strtotime($row['close_time'])) : '—' ?>
                </td>
            </tr>
            <?php endforeach; ?>
            <?php if (empty($recent)): ?>
            <tr><td colspan="9" style="text-align:center;color:var(--text-muted);padding:1.5rem">No closed signals yet</td></tr>
            <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

<?php require_once __DIR__ . '/../includes/footer.php'; ?>
