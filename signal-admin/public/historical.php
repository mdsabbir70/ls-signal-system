<?php
require_once __DIR__ . '/../includes/config.php';
require_once __DIR__ . '/../includes/db.php';
require_once __DIR__ . '/../includes/auth.php';

require_login();
$page_title = 'Historical Data';

// ── Check if tables exist ────────────────────────────────────────────────
$tables_exist = true;
try {
    db_query("SELECT 1 FROM historical_prices LIMIT 1");
} catch (Exception $e) {
    $tables_exist = false;
}

if ($tables_exist):

// ── Price data summary ───────────────────────────────────────────────────
$price_stats = db_query("SELECT pair, timeframe,
    COUNT(*) as bars,
    MIN(open_time) as date_from,
    MAX(open_time) as date_to
    FROM historical_prices
    GROUP BY pair, timeframe
    ORDER BY pair, FIELD(timeframe, 'W1','D1','H4','H1')");

$price_totals = db_one("SELECT
    COUNT(*) as total_bars,
    COUNT(DISTINCT pair) as total_pairs,
    COUNT(DISTINCT timeframe) as total_tf,
    MIN(open_time) as earliest,
    MAX(open_time) as latest
    FROM historical_prices") ?: ['total_bars'=>0,'total_pairs'=>0,'total_tf'=>0,'earliest'=>null,'latest'=>null];

// ── COT data summary ────────────────────────────────────────────────────
$cot_stats = db_query("SELECT currency,
    COUNT(*) as records,
    MIN(report_date) as date_from,
    MAX(report_date) as date_to
    FROM cot_data
    GROUP BY currency ORDER BY currency");

$cot_total = db_one("SELECT COUNT(*) as total FROM cot_data")['total'] ?? 0;

// ── Interest rate summary ────────────────────────────────────────────────
$rate_stats = db_query("SELECT currency, central_bank,
    COUNT(*) as records,
    MIN(rate_date) as date_from,
    MAX(rate_date) as date_to,
    (SELECT rate_value FROM interest_rates r2
     WHERE r2.currency = interest_rates.currency
     ORDER BY r2.rate_date DESC LIMIT 1) as current_rate
    FROM interest_rates
    GROUP BY currency, central_bank ORDER BY currency");

$rate_total = db_one("SELECT COUNT(*) as total FROM interest_rates")['total'] ?? 0;

// ── Recent collection logs ───────────────────────────────────────────────
$logs = db_query("SELECT * FROM data_collection_log ORDER BY created_at DESC LIMIT 20");

endif;

require_once __DIR__ . '/../includes/header.php';
?>

<?php if (!$tables_exist): ?>
<div class="card">
    <div class="card-body" style="text-align:center;padding:3rem">
        <h2 style="margin-bottom:1rem">Historical Data Tables Not Found</h2>
        <p style="color:var(--text-muted);margin-bottom:1.5rem">
            Run the data collector first to create tables and fetch data:
        </p>
        <pre style="background:var(--bg-input);padding:1rem;border-radius:var(--radius);text-align:left;display:inline-block">
cd /home/signal.lstrading.xyz/signal-bot
python3 collect_historical.py</pre>
    </div>
</div>
<?php else: ?>

<!-- Summary stats -->
<div class="stats-grid">
    <div class="stat-card">
        <div class="stat-value"><?= number_format($price_totals['total_bars']) ?></div>
        <div class="stat-label">Total Price Bars</div>
    </div>
    <div class="stat-card">
        <div class="stat-value"><?= $price_totals['total_pairs'] ?></div>
        <div class="stat-label">Pairs Collected</div>
    </div>
    <div class="stat-card">
        <div class="stat-value"><?= $cot_total ?></div>
        <div class="stat-label">COT Records</div>
    </div>
    <div class="stat-card">
        <div class="stat-value"><?= $rate_total ?></div>
        <div class="stat-label">Rate Records</div>
    </div>
    <div class="stat-card">
        <div class="stat-value"><?= $price_totals['earliest'] ? date('Y', strtotime($price_totals['earliest'])) : '—' ?></div>
        <div class="stat-label">Earliest Data</div>
    </div>
    <div class="stat-card">
        <div class="stat-value"><?= $price_totals['latest'] ? date('d M Y', strtotime($price_totals['latest'])) : '—' ?></div>
        <div class="stat-label">Latest Data</div>
    </div>
</div>

<!-- Price data table -->
<div class="card">
    <div class="card-header">
        <h2>Price Data (OHLCV)</h2>
        <span class="text-muted"><?= number_format($price_totals['total_bars']) ?> total bars</span>
    </div>
    <div class="table-wrapper">
        <table class="data-table">
            <thead><tr>
                <th>Pair</th><th>Timeframe</th><th>Bars</th>
                <th>From</th><th>To</th><th>Years</th>
            </tr></thead>
            <tbody>
            <?php
            $current_pair = '';
            foreach ($price_stats as $row):
                $from = $row['date_from'] ? strtotime($row['date_from']) : null;
                $to = $row['date_to'] ? strtotime($row['date_to']) : null;
                $years = ($from && $to) ? round(($to - $from) / (365.25 * 86400), 1) : 0;
                $is_new_pair = ($row['pair'] !== $current_pair);
                $current_pair = $row['pair'];
            ?>
            <tr<?= $is_new_pair ? ' style="border-top:2px solid var(--border)"' : '' ?>>
                <td><?= $is_new_pair ? '<strong>'.$row['pair'].'</strong>' : '' ?></td>
                <td><span class="badge"><?= $row['timeframe'] ?></span></td>
                <td><?= number_format($row['bars']) ?></td>
                <td style="font-size:.85rem"><?= $row['date_from'] ? date('d M Y', $from) : '—' ?></td>
                <td style="font-size:.85rem"><?= $row['date_to'] ? date('d M Y', $to) : '—' ?></td>
                <td>
                    <span class="badge <?= $years >= 5 ? 'badge-buy' : ($years >= 1 ? '' : 'badge-sell') ?>">
                        <?= $years ?>y
                    </span>
                </td>
            </tr>
            <?php endforeach; ?>
            <?php if (empty($price_stats)): ?>
            <tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:1.5rem">
                No price data collected yet. Run: <code>python3 collect_historical.py --prices</code>
            </td></tr>
            <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:1.25rem">

<!-- COT data -->
<div class="card">
    <div class="card-header">
        <h2>COT Data (CFTC)</h2>
        <span class="text-muted"><?= $cot_total ?> records</span>
    </div>
    <div class="table-wrapper">
        <table class="data-table">
            <thead><tr>
                <th>Currency</th><th>Records</th><th>From</th><th>To</th>
            </tr></thead>
            <tbody>
            <?php foreach ($cot_stats as $row): ?>
            <tr>
                <td><strong><?= $row['currency'] ?></strong></td>
                <td><?= number_format($row['records']) ?></td>
                <td style="font-size:.85rem"><?= date('d M Y', strtotime($row['date_from'])) ?></td>
                <td style="font-size:.85rem"><?= date('d M Y', strtotime($row['date_to'])) ?></td>
            </tr>
            <?php endforeach; ?>
            <?php if (empty($cot_stats)): ?>
            <tr><td colspan="4" style="text-align:center;color:var(--text-muted);padding:1.5rem">
                No COT data. Run: <code>python3 collect_historical.py --cot</code>
            </td></tr>
            <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

<!-- Interest rates -->
<div class="card">
    <div class="card-header">
        <h2>Interest Rates</h2>
        <span class="text-muted"><?= $rate_total ?> records</span>
    </div>
    <div class="table-wrapper">
        <table class="data-table">
            <thead><tr>
                <th>Currency</th><th>Central Bank</th><th>Current</th><th>Records</th><th>From</th>
            </tr></thead>
            <tbody>
            <?php foreach ($rate_stats as $row): ?>
            <tr>
                <td><strong><?= $row['currency'] ?></strong></td>
                <td style="font-size:.85rem"><?= $row['central_bank'] ?></td>
                <td><span class="badge"><?= $row['current_rate'] !== null ? $row['current_rate'].'%' : '—' ?></span></td>
                <td><?= $row['records'] ?></td>
                <td style="font-size:.85rem"><?= date('M Y', strtotime($row['date_from'])) ?></td>
            </tr>
            <?php endforeach; ?>
            <?php if (empty($rate_stats)): ?>
            <tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:1.5rem">
                No rate data. Set <code>FRED_API_KEY</code> env var and run: <code>python3 collect_historical.py --rates</code>
            </td></tr>
            <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

</div>

<!-- Collection log -->
<div class="card">
    <div class="card-header">
        <h2>Collection Log</h2>
    </div>
    <div class="table-wrapper">
        <table class="data-table">
            <thead><tr>
                <th>Time</th><th>Type</th><th>Pair</th><th>TF</th>
                <th>Status</th><th>Records</th><th>Duration</th><th>Error</th>
            </tr></thead>
            <tbody>
            <?php foreach ($logs as $log):
                $status_color = match($log['status']) {
                    'completed' => 'var(--buy)',
                    'failed'    => 'var(--sell)',
                    default     => 'var(--warning)',
                };
            ?>
            <tr>
                <td style="font-size:.8rem;color:var(--text-muted)">
                    <?= date('d M, h:i A', strtotime($log['created_at'])) ?>
                </td>
                <td><span class="badge"><?= strtoupper($log['data_type']) ?></span></td>
                <td><?= $log['pair'] ?: '—' ?></td>
                <td><?= $log['timeframe'] ?: '—' ?></td>
                <td style="color:<?= $status_color ?>;font-weight:600"><?= strtoupper($log['status']) ?></td>
                <td><?= $log['records_count'] ?: '—' ?></td>
                <td><?= $log['duration_sec'] ? $log['duration_sec'].'s' : '—' ?></td>
                <td style="font-size:.75rem;color:var(--sell);max-width:200px;overflow:hidden;text-overflow:ellipsis">
                    <?= $log['error_message'] ? htmlspecialchars(substr($log['error_message'], 0, 100)) : '' ?>
                </td>
            </tr>
            <?php endforeach; ?>
            <?php if (empty($logs)): ?>
            <tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:1.5rem">No collection logs yet</td></tr>
            <?php endif; ?>
            </tbody>
        </table>
    </div>
</div>

<!-- CLI Reference -->
<div class="card">
    <div class="card-header"><h2>CLI Commands</h2></div>
    <div class="card-body">
        <pre style="background:var(--bg-input);padding:1rem;border-radius:var(--radius);font-size:.85rem;overflow-x:auto">
# SSH into server first
cd /home/signal.lstrading.xyz/signal-bot

# Collect everything (prices + COT + rates)
python3 collect_historical.py

# Price data only (all pairs, all timeframes)
python3 collect_historical.py --prices

# Specific pair and timeframe
python3 collect_historical.py --prices --pair EURUSD GBPUSD --tf D1 W1

# COT data only (10 years of CFTC reports)
python3 collect_historical.py --cot

# Interest rates (requires FRED_API_KEY)
python3 collect_historical.py --rates --fred-key YOUR_KEY

# Check current status
python3 collect_historical.py --status</pre>
    </div>
</div>

<?php endif; ?>

<?php require_once __DIR__ . '/../includes/footer.php'; ?>
