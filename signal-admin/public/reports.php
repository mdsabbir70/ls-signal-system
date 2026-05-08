<?php
require_once __DIR__ . '/../includes/config.php';
require_once __DIR__ . '/../includes/db.php';
require_once __DIR__ . '/../includes/auth.php';

require_login();
$page_title = 'Reports';

// Filters
$period   = $_GET['period'] ?? '30';
$pair     = $_GET['pair']   ?? '';
$mode_f   = $_GET['mode']   ?? '';
$days     = in_array($period, ['7','14','30','60','90','all']) ? $period : '30';
$date_cond = $days === 'all' ? '1=1' : "created_at >= DATE_SUB(NOW(), INTERVAL {$days} DAY)";
$pair_cond = $pair   ? "AND pair = "  . get_db()->quote($pair)   : '';
$mode_cond = $mode_f ? "AND mode = "  . get_db()->quote($mode_f) : '';

// ── Overall summary ───────────────────────────────────────────────
$summary = db_one("SELECT
    COUNT(*) as total,
    SUM(status='CLOSED_TP') as wins,
    SUM(status='CLOSED_SL') as losses,
    SUM(status='OPEN') as open_count,
    SUM(status='CANCELLED') as cancelled,
    ROUND(SUM(CASE WHEN status='CLOSED_TP' THEN actual_pips ELSE 0 END),1) as pips_won,
    ROUND(SUM(CASE WHEN status='CLOSED_SL' THEN ABS(actual_pips) ELSE 0 END),1) as pips_lost,
    ROUND(SUM(CASE WHEN actual_profit > 0 THEN actual_profit ELSE 0 END),2) as gross_profit,
    ROUND(SUM(CASE WHEN actual_profit < 0 THEN ABS(actual_profit) ELSE 0 END),2) as gross_loss,
    ROUND(AVG(CASE WHEN status IN ('CLOSED_TP','CLOSED_SL') THEN duration_minutes END),0) as avg_duration,
    ROUND(AVG(risk_reward_ratio),2) as avg_rr
    FROM signals WHERE $date_cond $pair_cond $mode_cond", []);

$total    = $summary['total'] ?? 0;
$wins     = $summary['wins']  ?? 0;
$losses   = $summary['losses'] ?? 0;
$closed   = $wins + $losses;
$win_rate = $closed > 0 ? round($wins / $closed * 100, 1) : 0;
$net_pips = ($summary['pips_won'] ?? 0) - ($summary['pips_lost'] ?? 0);
$net_pnl  = ($summary['gross_profit'] ?? 0) - ($summary['gross_loss'] ?? 0);
$pf       = ($summary['gross_loss'] ?? 0) > 0
            ? round($summary['gross_profit'] / $summary['gross_loss'], 2) : 0;

// ── Mode breakdown (Pattern Engine performance) ───────────────────
$by_mode = db_query("SELECT
    mode,
    MAX(strategy) as strategy,
    COUNT(*) as total,
    SUM(status='CLOSED_TP') as wins,
    SUM(status='CLOSED_SL') as losses,
    SUM(status='OPEN') as open_cnt,
    ROUND(SUM(CASE WHEN status='CLOSED_TP' THEN actual_pips ELSE 0 END),1) as pips_won,
    ROUND(SUM(CASE WHEN status='CLOSED_SL' THEN ABS(actual_pips) ELSE 0 END),1) as pips_lost,
    ROUND(SUM(IFNULL(actual_profit,0)),2) as net_pnl,
    ROUND(AVG(CASE WHEN status IN ('CLOSED_TP','CLOSED_SL') THEN duration_minutes END),0) as avg_dur
    FROM signals WHERE $date_cond $pair_cond
    GROUP BY mode ORDER BY (SUM(status='CLOSED_TP')+SUM(status='CLOSED_SL')) DESC, total DESC", []);

// ── Per-pair breakdown ────────────────────────────────────────────
$by_pair = db_query("SELECT pair,
    COUNT(*) as total,
    SUM(status='CLOSED_TP') as wins,
    SUM(status='CLOSED_SL') as losses,
    SUM(status='OPEN') as open_cnt,
    ROUND(SUM(CASE WHEN status='CLOSED_TP' THEN actual_pips ELSE 0 END) -
          SUM(CASE WHEN status='CLOSED_SL' THEN ABS(actual_pips) ELSE 0 END),1) as net_pips,
    ROUND(SUM(IFNULL(actual_profit,0)),2) as net_pnl
    FROM signals WHERE $date_cond $mode_cond
    GROUP BY pair ORDER BY total DESC", []);

// ── Daily stats ───────────────────────────────────────────────────
$daily = db_query("SELECT stat_date, total_signals, closed_tp, closed_sl,
    win_rate, net_pips, net_pnl, profit_factor
    FROM daily_stats ORDER BY stat_date DESC LIMIT 30", []);

// ── Trade history (all closed signals) ───────────────────────────
$history = db_query("SELECT
    signal_id, pair, direction, mode, strategy, timeframe,
    entry_price, close_price, stop_loss, take_profit,
    status, actual_pips, actual_profit, sl_pips, tp_pips,
    risk_reward_ratio, duration_minutes, created_at, close_time
    FROM signals
    WHERE status IN ('CLOSED_TP','CLOSED_SL','CLOSED_MANUAL') $pair_cond $mode_cond
    ORDER BY close_time DESC LIMIT 50", []);

// ── Available filters ─────────────────────────────────────────────
$pairs_list = db_query("SELECT DISTINCT pair FROM signals ORDER BY pair", []);
$modes_list = db_query("SELECT DISTINCT mode FROM signals ORDER BY mode", []);

require_once __DIR__ . '/../includes/header.php';

function fmt_mins($m) {
    if (!$m) return '—';
    if ($m < 60) return $m . 'm';
    return round($m/60,1) . 'h';
}

// Mode color + full label map
$mode_colors = [
    // Hybrid engine modes
    'technical'            => '#0ea5e9',
    'news'                 => '#f59e0b',
    'hybrid'               => '#8b5cf6',
    'ai'                   => '#ec4899',
    'technical_news_filter' => '#10b981',
    // Pattern engine modes
    'Mode_1'=>'#3b82f6','Mode_2'=>'#f97316','Mode_3'=>'#22c55e','Mode_4'=>'#eab308',
    'Mode_5'=>'#a855f7','Mode_6'=>'#ef4444','Mode_7'=>'#d97706','Mode_8'=>'#0ea5e9',
    'Mode_9'=>'#b91c1c','Mode_10'=>'#1d4ed8','Mode_11'=>'#c2410c','Mode_12'=>'#6b7280',
    'Mode_13'=>'#db2777','Mode_14'=>'#0891b2','Mode_15'=>'#374151','Mode_16'=>'#7c3aed',
    'Mode_17'=>'#78350f','Mode_19'=>'#ea580c','Mode_20'=>'#dc2626','Mode_21'=>'#1e40af',
    'Mode_22'=>'#16a34a',
];
$mode_labels = [
    // Hybrid engine modes
    'technical'            => '🔧 Technical Analysis',
    'news'                 => '📰 News Sentiment',
    'hybrid'               => '⚡ Hybrid Confluence',
    'ai'                   => '🤖 AI Analysis',
    'technical_news_filter' => '🔗 Technical + News Filter',
    // Pattern engine modes
    'Mode_1'  => '🔵 Mode 1: Double_Bottom + RSI',
    'Mode_2'  => '🟠 Mode 2: Rising_Wedge + ADX',
    'Mode_3'  => '🟢 Mode 3: Double_Bottom + ADX',
    'Mode_4'  => '🟡 Mode 4: Falling_Wedge + EMA_Trend',
    'Mode_5'  => '🟣 Mode 5: Triple_Bottom + Alone',
    'Mode_6'  => '🔴 Mode 6: Double_Top + RSI',
    'Mode_7'  => '🔶 Mode 7: Ascending_Triangle + ADX',
    'Mode_8'  => '🔷 Mode 8: Rounding_Bottom + RSI',
    'Mode_9'  => '🟥 Mode 9: Descending_Triangle + ADX',
    'Mode_10' => '🟦 Mode 10: Three_White_Soldiers + EMA',
    'Mode_11' => '🟧 Mode 11: Mat_Hold + ADX',
    'Mode_12' => '🩶 Mode 12: Rickshaw_Man + RSI',
    'Mode_13' => '🩷 Mode 13: Shooting_Star + RSI',
    'Mode_14' => '🩵 Mode 14: Upside_Gap_Three + Alone',
    'Mode_15' => '🖤 Mode 15: Three_Line_Strike_Bear + EMA',
    'Mode_16' => '🤍 Mode 16: Symmetrical_Triangle + EMA',
    'Mode_17' => '🟫 Mode 17: Three_Outside_Down + RSI',
    'Mode_19' => '🧡 Mode 19: Belt_Hold_Bull + EMA',
    'Mode_20' => '❤️ Mode 20: Triple_Top + RSI',
    'Mode_21' => '💙 Mode 21: Tasuki_Gap_Bear + ADX',
    'Mode_22' => '💚 Mode 22: Tasuki_Gap_Bull + ADX',
];
function mode_badge($mode, $colors) {
    $color = $colors[$mode] ?? '#64748b';
    $label = str_replace('_',' ', $mode);
    return "<span class='badge' style='background:{$color}22;color:{$color};border:1px solid {$color}44'>{$label}</span>";
}
function mode_label_cell($mode, $colors, $labels) {
    $color = $colors[$mode] ?? '#64748b';
    $label = $labels[$mode] ?? str_replace('_',' ',$mode);
    return "<span style='color:{$color};font-weight:600;font-size:.85rem'>{$label}</span>";
}
?>

<!-- Filters -->
<div class="card" style="margin-bottom:1.25rem">
    <div class="card-body">
        <form method="GET" class="controls-row" style="flex-wrap:wrap;gap:.5rem">
            <label style="color:var(--text-muted);font-size:.85rem;align-self:center">Period:</label>
            <?php foreach (['7'=>'7d','14'=>'14d','30'=>'30d','60'=>'60d','90'=>'90d','all'=>'All'] as $v => $l): ?>
            <a href="?period=<?= $v ?>&pair=<?= urlencode($pair) ?>&mode=<?= urlencode($mode_f) ?>"
               class="btn btn-sm <?= $days===$v ? 'btn-primary':'btn-outline' ?>"><?= $l ?></a>
            <?php endforeach; ?>
            <select name="pair" class="form-select" style="max-width:120px" onchange="this.form.submit()">
                <option value="">All Pairs</option>
                <?php foreach ($pairs_list as $p): ?>
                <option value="<?= $p['pair'] ?>" <?= $pair===$p['pair']?'selected':'' ?>><?= $p['pair'] ?></option>
                <?php endforeach; ?>
            </select>
            <?php
            $filter_mode_labels = [
                'technical' => 'Technical', 'news' => 'News', 'hybrid' => 'Hybrid',
                'ai' => 'AI', 'technical_news_filter' => 'Tech+News',
            ];
            ?>
            <select name="mode" class="form-select" style="max-width:150px" onchange="this.form.submit()">
                <option value="">All Modes</option>
                <?php foreach ($modes_list as $m):
                    $mv = $m['mode'];
                    $ml = $filter_mode_labels[$mv] ?? str_replace('_',' ',$mv);
                ?>
                <option value="<?= htmlspecialchars($mv) ?>" <?= $mode_f===$mv?'selected':'' ?>>
                    <?= htmlspecialchars($ml) ?>
                </option>
                <?php endforeach; ?>
            </select>
            <input type="hidden" name="period" value="<?= htmlspecialchars($days) ?>">
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
        <div class="stat-label">Win Rate (<?= $wins ?>W / <?= $losses ?>L)</div>
    </div>
    <div class="stat-card <?= $net_pips >= 0 ? 'stat-profit' : 'stat-loss' ?>">
        <div class="stat-value"><?= $net_pips >= 0 ? '+' : '' ?><?= $net_pips ?></div>
        <div class="stat-label">Net Pips</div>
    </div>
    <div class="stat-card <?= $net_pnl >= 0 ? 'stat-profit' : 'stat-loss' ?>">
        <div class="stat-value"><?= $net_pnl >= 0 ? '+' : '' ?>$<?= number_format($net_pnl, 2) ?></div>
        <div class="stat-label">Net P&L</div>
    </div>
    <div class="stat-card <?= $pf >= 1.5 ? 'stat-profit' : ($pf >= 1 ? '' : 'stat-loss') ?>">
        <div class="stat-value"><?= $pf ?: '—' ?></div>
        <div class="stat-label">Profit Factor</div>
    </div>
    <div class="stat-card">
        <div class="stat-value"><?= $summary['open_count'] ?? 0 ?></div>
        <div class="stat-label">Open Signals</div>
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

<!-- Pattern Engine Mode Performance -->
<div class="card">
    <div class="card-header">
        <h2>🧩 Trading Mode Performance</h2>
        <span style="font-size:.8rem;color:var(--text-muted)">সব মোড — Pattern + Hybrid Engine পারফরম্যান্স</span>
    </div>
    <div class="table-wrapper">
        <table class="data-table">
            <thead><tr>
                <th>Mode</th>
                <th>Strategy</th>
                <th>Signals</th>
                <th style="color:var(--buy)">✅ TP</th>
                <th style="color:var(--sell)">🛑 SL</th>
                <th>Win%</th>
                <th>Pips Won</th>
                <th>Pips Lost</th>
                <th>Net Pips</th>
                <th>Net P&L</th>
                <th>Open</th>
                <th>Avg Dur</th>
            </tr></thead>
            <tbody>
            <?php
            // Index DB data by mode for quick lookup
            $mode_data = [];
            foreach ($by_mode as $row) {
                $mode_data[$row['mode']] = $row;
            }
            // Show ALL defined modes (including those with 0 signals)
            $all_modes = array_keys($mode_labels);
            foreach ($all_modes as $mode_key):
                $row = $mode_data[$mode_key] ?? null;
                $w  = (int)($row['wins'] ?? 0);
                $l  = (int)($row['losses'] ?? 0);
                $total_sigs = (int)($row['total'] ?? 0);
                $wr = ($w+$l) > 0 ? round($w/($w+$l)*100) : null;
                $net_p = round(($row['pips_won'] ?? 0) - ($row['pips_lost'] ?? 0), 1);
                $pnl   = (float)($row['net_pnl'] ?? 0);
                $open  = (int)($row['open_cnt'] ?? 0);
                $avg_d = $row['avg_dur'] ?? null;
                $no_data = ($total_sigs === 0);
            ?>
            <tr<?= $no_data ? ' style="opacity:.5"' : '' ?>>
                <td colspan="2"><?= mode_label_cell($mode_key, $mode_colors, $mode_labels) ?></td>
                <td><?= $total_sigs ?></td>
                <td style="color:var(--buy);font-weight:600"><?= $w ?></td>
                <td style="color:var(--sell);font-weight:600"><?= $l ?></td>
                <td>
                    <?php if ($wr !== null): ?>
                    <span style="color:<?= $wr >= 60 ? 'var(--buy)' : ($wr >= 40 ? 'var(--warning,#eab308)' : 'var(--sell)') ?>;font-weight:600">
                        <?= $wr ?>%
                    </span>
                    <?php else: ?>
                    <span style="color:var(--text-muted)">—</span>
                    <?php endif; ?>
                </td>
                <td style="color:var(--buy)"><?= ($row['pips_won'] ?? 0) > 0 ? '+'.($row['pips_won']) : '—' ?></td>
                <td style="color:var(--sell)"><?= ($row['pips_lost'] ?? 0) > 0 ? '-'.($row['pips_lost']) : '—' ?></td>
                <td style="color:<?= $net_p >= 0 ? 'var(--buy)' : 'var(--sell)' ?>;font-weight:600">
                    <?= $no_data ? '—' : ($net_p >= 0 ? '+'.$net_p : $net_p) ?>
                </td>
                <td style="color:<?= $pnl >= 0 ? 'var(--buy)' : 'var(--sell)' ?>;font-weight:600">
                    <?= $no_data ? '—' : ($pnl >= 0 ? '+' : '') . '$' . number_format($pnl, 2) ?>
                </td>
                <td style="color:var(--text-muted)"><?= $open ?></td>
                <td style="color:var(--text-muted);font-size:.8rem"><?= fmt_mins($avg_d) ?></td>
            </tr>
            <?php endforeach; ?>
            </tbody>
        </table>
    </div>
</div>

<!-- Trade History -->
<div class="card">
    <div class="card-header">
        <h2>📋 Trade History</h2>
        <span style="font-size:.8rem;color:var(--text-muted)">সব closed trade — TP ও SL</span>
    </div>
    <div class="table-wrapper">
        <table class="data-table">
            <thead><tr>
                <th>Time</th>
                <th>Pair</th>
                <th>Dir / TF</th>
                <th>Trading Mode</th>
                <th>Result</th>
                <th>Entry</th>
                <th>Close</th>
                <th>Pips</th>
                <th>P&L</th>
                <th>Duration</th>
            </tr></thead>
            <tbody>
            <?php if (empty($history)): ?>
            <tr><td colspan="10" style="text-align:center;color:var(--text-muted);padding:2rem">
                এখনো কোনো trade close হয়নি
            </td></tr>
            <?php endif; ?>
            <?php foreach ($history as $row):
                $is_tp = $row['status'] === 'CLOSED_TP';
                $is_sl = $row['status'] === 'CLOSED_SL';
                $rc    = $is_tp ? 'var(--buy)' : 'var(--sell)';
                $pips  = $row['actual_pips'];
                $pnl   = (float)($row['actual_profit'] ?? 0);
                $mcolor = $mode_colors[$row['mode']] ?? '#64748b';
                $mlabel = $mode_labels[$row['mode']] ?? str_replace('_',' ',$row['mode']);
            ?>
            <tr>
                <td style="font-size:.75rem;color:var(--text-muted);white-space:nowrap">
                    <?= $row['close_time'] ? date('d M, h:i A', strtotime($row['close_time'])) : '—' ?>
                </td>
                <td><strong style="font-size:.95rem"><?= $row['pair'] ?></strong></td>
                <td>
                    <span class="badge" style="background:<?= $row['direction']==='BUY'?'rgba(34,197,94,.2)':'rgba(239,68,68,.2)' ?>;color:<?= $row['direction']==='BUY'?'var(--buy)':'var(--sell)' ?>">
                        <?= $row['direction'] ?>
                    </span>
                    <span style="font-size:.75rem;color:var(--text-muted);margin-left:.25rem"><?= $row['timeframe'] ?></span>
                </td>
                <td>
                    <span style="color:<?= $mcolor ?>;font-weight:600;font-size:.88rem"><?= $mlabel ?></span>
                </td>
                <td>
                    <?php if ($is_tp): ?>
                    <span style="color:var(--buy);font-weight:700;font-size:.95rem">✅ PROFIT</span>
                    <?php elseif ($is_sl): ?>
                    <span style="color:var(--sell);font-weight:700;font-size:.95rem">🛑 LOSS</span>
                    <?php else: ?>
                    <span style="color:var(--text-muted)">Closed</span>
                    <?php endif; ?>
                </td>
                <td style="font-family:monospace;font-size:.8rem"><?= $row['entry_price'] ?></td>
                <td style="font-family:monospace;font-size:.8rem"><?= $row['close_price'] ?? '—' ?></td>
                <td style="color:<?= $rc ?>;font-weight:600">
                    <?= $pips !== null ? ($pips >= 0 ? '+' : '').$pips.'p' : '—' ?>
                </td>
                <td style="color:<?= $pnl >= 0 ? 'var(--buy)' : 'var(--sell)' ?>;font-weight:700;font-size:.95rem">
                    <?= $pnl >= 0 ? '+' : '' ?>$<?= number_format($pnl, 2) ?>
                </td>
                <td style="font-size:.8rem;color:var(--text-muted)"><?= fmt_mins($row['duration_minutes']) ?></td>
            </tr>
            <?php endforeach; ?>
            </tbody>
        </table>
    </div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:1.25rem">

<!-- Per-pair breakdown -->
<div class="card">
    <div class="card-header"><h2>💱 By Pair</h2></div>
    <div class="table-wrapper">
        <table class="data-table">
            <thead><tr>
                <th>Pair</th><th>Total</th><th>✅W</th><th>🛑L</th>
                <th>Win%</th><th>Net Pips</th><th>Net P&L</th><th>Open</th>
            </tr></thead>
            <tbody>
            <?php foreach ($by_pair as $row):
                $w = (int)$row['wins']; $l = (int)$row['losses'];
                $wr = ($w+$l) > 0 ? round($w/($w+$l)*100) : 0;
                $pip_color = $row['net_pips'] >= 0 ? 'var(--buy)' : 'var(--sell)';
                $pnl_color = $row['net_pnl']  >= 0 ? 'var(--buy)' : 'var(--sell)';
            ?>
            <tr>
                <td><strong><?= $row['pair'] ?></strong></td>
                <td><?= $row['total'] ?></td>
                <td style="color:var(--buy);font-weight:600"><?= $w ?></td>
                <td style="color:var(--sell);font-weight:600"><?= $l ?></td>
                <td style="color:<?= $wr >= 60 ? 'var(--buy)':($wr >= 40 ?'var(--warning,#eab308)':'var(--sell)') ?>"><?= ($w+$l)>0?$wr.'%':'—' ?></td>
                <td style="color:<?= $pip_color ?>"><?= $row['net_pips'] >= 0 ? '+':'' ?><?= $row['net_pips'] ?></td>
                <td style="color:<?= $pnl_color ?>"><?= $row['net_pnl'] >= 0 ? '+' : '' ?>$<?= number_format($row['net_pnl'],2) ?></td>
                <td style="color:var(--text-muted)"><?= $row['open_cnt'] ?></td>
            </tr>
            <?php endforeach; ?>
            <?php if (empty($by_pair)): ?>
            <tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:1.5rem">No data</td></tr>
            <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

<!-- Daily stats -->
<div class="card">
    <div class="card-header"><h2>📅 Daily Performance</h2></div>
    <div class="table-wrapper">
        <table class="data-table">
            <thead><tr>
                <th>Date</th><th>Signals</th><th>✅TP</th><th>🛑SL</th>
                <th>Win%</th><th>Net Pips</th><th>Net P&L</th>
            </tr></thead>
            <tbody>
            <?php foreach ($daily as $row):
                $pnl_color = $row['net_pnl'] >= 0 ? 'var(--buy)' : 'var(--sell)';
                $pip_color = $row['net_pips'] >= 0 ? 'var(--buy)' : 'var(--sell)';
                $wr_color  = $row['win_rate'] >= 60 ? 'var(--buy)' : ($row['win_rate'] >= 40 ? 'var(--warning,#eab308)' : 'var(--sell)');
            ?>
            <tr>
                <td><?= date('d M Y', strtotime($row['stat_date'])) ?></td>
                <td><?= $row['total_signals'] ?></td>
                <td style="color:var(--buy)"><?= $row['closed_tp'] ?></td>
                <td style="color:var(--sell)"><?= $row['closed_sl'] ?></td>
                <td style="color:<?= $wr_color ?>"><?= $row['win_rate'] ?>%</td>
                <td style="color:<?= $pip_color ?>"><?= $row['net_pips'] >= 0 ? '+':'' ?><?= $row['net_pips'] ?></td>
                <td style="color:<?= $pnl_color ?>"><?= $row['net_pnl'] >= 0 ? '+' : '' ?>$<?= number_format($row['net_pnl'],2) ?></td>
            </tr>
            <?php endforeach; ?>
            <?php if (empty($daily)): ?>
            <tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:1.5rem">No daily stats yet</td></tr>
            <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

</div>

<?php require_once __DIR__ . '/../includes/footer.php'; ?>
