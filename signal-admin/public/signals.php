<?php
require_once __DIR__ . '/../includes/config.php';
require_once __DIR__ . '/../includes/db.php';
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/bot_api.php';

require_login();

// ── Signal Detail View ────────────────────────────────────────────────────
$view_id = $_GET['id'] ?? '';
if ($view_id) {
    $signal = db_one("SELECT * FROM signals WHERE signal_id = ?", [$view_id]);
    if (!$signal) {
        header('Location: /signals.php');
        exit;
    }
    $page_title = $signal['signal_id'];
    require_once __DIR__ . '/../includes/header.php';

    $bd = json_decode($signal['score_breakdown'] ?? '{}', true);
    $detail = $bd['detail'] ?? [];
    $snap = json_decode($signal['indicator_snapshot'] ?? '{}', true);
    $is_buy = $signal['direction'] === 'BUY';
    $dir_color = $is_buy ? 'var(--buy)' : 'var(--sell)';
    $status_class = match($signal['status']) {
        'OPEN' => 'badge-info', 'CLOSED_TP' => 'badge-success',
        'CLOSED_SL' => 'badge-danger', default => ''
    };
    $pips = $signal['actual_pips'];
    ?>

    <a href="/signals.php" class="btn btn-sm btn-secondary" style="margin-bottom:1rem">&larr; Back to Signals</a>

    <!-- Header -->
    <div class="card">
        <div class="card-body" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:1rem">
            <div>
                <h2 style="margin:0;color:<?= $dir_color ?>">
                    <?= $is_buy ? '🟢' : '🔴' ?> <?= $signal['direction'] ?> <?= htmlspecialchars($signal['pair']) ?>
                </h2>
                <p class="text-muted" style="margin:.25rem 0 0"><code><?= htmlspecialchars($signal['signal_id']) ?></code></p>
            </div>
            <div style="text-align:right">
                <span class="badge <?= $status_class ?>" style="font-size:1rem;padding:.4rem .8rem">
                    <?= htmlspecialchars($signal['status']) ?>
                </span>
                <br>
                <small class="text-muted"><?= date('d M Y, h:i A', strtotime($signal['created_at'])) ?></small>
            </div>
        </div>
    </div>

    <!-- Trade Details -->
    <div class="stats-grid" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr))">
        <div class="stat-card">
            <div class="stat-value"><?= number_format((float)$signal['entry_price'], 5) ?></div>
            <div class="stat-label">Entry Price</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color:var(--sell)"><?= number_format((float)$signal['stop_loss'], 5) ?></div>
            <div class="stat-label">Stop Loss (<?= $signal['sl_pips'] ?> pips)</div>
        </div>
        <div class="stat-card">
            <div class="stat-value" style="color:var(--buy)"><?= number_format((float)$signal['take_profit'], 5) ?></div>
            <div class="stat-label">Take Profit (<?= $signal['tp_pips'] ?> pips)</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">1:<?= $signal['risk_reward_ratio'] ?></div>
            <div class="stat-label">Risk:Reward</div>
        </div>
        <div class="stat-card">
            <div class="stat-value"><?= $signal['suggested_lot'] ?></div>
            <div class="stat-label">Lot Size ($<?= number_format((float)$signal['risk_amount'], 2) ?> risk)</div>
        </div>
        <div class="stat-card">
            <div class="stat-value"><?= $signal['confluence_score'] ?>/100</div>
            <div class="stat-label">Score (<?= htmlspecialchars($signal['quality_label']) ?>)</div>
        </div>
    </div>

    <?php if ($signal['status'] !== 'OPEN'): ?>
    <!-- Result -->
    <div class="card">
        <div class="card-header"><h2>Result</h2></div>
        <div class="card-body">
            <div class="stats-grid" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr))">
                <div class="stat-card">
                    <div class="stat-value"><?= $signal['close_price'] ? number_format((float)$signal['close_price'], 5) : '—' ?></div>
                    <div class="stat-label">Close Price</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color:<?= ($pips ?? 0) >= 0 ? 'var(--buy)' : 'var(--sell)' ?>">
                        <?= $pips !== null ? (($pips >= 0 ? '+' : '') . number_format((float)$pips, 1) . ' pips') : '—' ?>
                    </div>
                    <div class="stat-label">Pips</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color:<?= ($signal['actual_profit'] ?? 0) >= 0 ? 'var(--buy)' : 'var(--sell)' ?>">
                        <?= $signal['actual_profit'] !== null ? (($signal['actual_profit'] >= 0 ? '+' : '') . '$' . number_format(abs((float)$signal['actual_profit']), 2)) : '—' ?>
                    </div>
                    <div class="stat-label">Profit/Loss</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value"><?= $signal['duration_minutes'] ? $signal['duration_minutes'] . 'min' : '—' ?></div>
                    <div class="stat-label">Duration</div>
                </div>
            </div>
        </div>
    </div>
    <?php endif; ?>

    <!-- Score Breakdown -->
    <div class="card">
        <div class="card-header"><h2>Confluence Score Breakdown</h2></div>
        <div class="card-body">
            <?php
            $has_liquidity = isset($bd['liquidity']);
            $categories = $has_liquidity
                ? ['Technical' => ['max' => 30, 'val' => $bd['technical'] ?? 0, 'items' => [
                        'EMA Alignment' => [$detail['ema_alignment'] ?? 0, 10],
                        'MACD Cross' => [$detail['macd_cross'] ?? 0, 8],
                        'RSI Condition' => [$detail['rsi_condition'] ?? 0, 6],
                        'ADX Strength' => [$detail['adx_strength'] ?? 0, 6],
                    ]],
                    'Multi-Timeframe' => ['max' => 15, 'val' => $bd['multi_tf'] ?? 0, 'items' => [
                        'HTF (D1) Trend' => [$detail['htf_trend'] ?? 0, 8],
                        'MTF (H4) Trend' => [$detail['mtf_trend'] ?? 0, 7],
                    ]],
                    'News/Sentiment' => ['max' => 15, 'val' => $bd['news'] ?? 0, 'items' => [
                        'News Sentiment' => [$detail['news_sentiment'] ?? 0, 8],
                        'AI Confidence' => [$detail['ai_confidence'] ?? 0, 7],
                    ]],
                    'Liquidity/SMC' => ['max' => 20, 'val' => $bd['liquidity'] ?? 0, 'items' => [
                        'Order Block' => [$detail['order_block'] ?? 0, 6],
                        'Fair Value Gap' => [$detail['fvg'] ?? 0, 5],
                        'Market Structure' => [$detail['market_structure'] ?? 0, 5],
                        'Liquidity Sweep' => [$detail['liquidity_sweep'] ?? 0, 4],
                    ]],
                    'Conditions' => ['max' => 20, 'val' => $bd['conditions'] ?? 0, 'items' => [
                        'Market Regime' => [$detail['market_regime'] ?? 0, 10],
                        'Volatility' => [$detail['volatility'] ?? 0, 5],
                        'Stochastic' => [$detail['stochastic'] ?? 0, 5],
                    ]]]
                : ['Technical' => ['max' => 40, 'val' => $bd['technical'] ?? 0, 'items' => [
                        'EMA Alignment' => [$detail['ema_alignment'] ?? 0, 15],
                        'MACD Cross' => [$detail['macd_cross'] ?? 0, 10],
                        'RSI Condition' => [$detail['rsi_condition'] ?? 0, 8],
                        'ADX Strength' => [$detail['adx_strength'] ?? 0, 7],
                    ]],
                    'Multi-Timeframe' => ['max' => 20, 'val' => $bd['multi_tf'] ?? 0, 'items' => [
                        'HTF (D1) Trend' => [$detail['htf_trend'] ?? 0, 10],
                        'MTF (H4) Trend' => [$detail['mtf_trend'] ?? 0, 10],
                    ]],
                    'News/Sentiment' => ['max' => 20, 'val' => $bd['news'] ?? 0, 'items' => [
                        'News Sentiment' => [$detail['news_sentiment'] ?? 0, 10],
                        'AI Confidence' => [$detail['ai_confidence'] ?? 0, 10],
                    ]],
                    'Conditions' => ['max' => 20, 'val' => $bd['conditions'] ?? 0, 'items' => [
                        'Market Regime' => [$detail['market_regime'] ?? 0, 10],
                        'Volatility' => [$detail['volatility'] ?? 0, 5],
                        'Stochastic' => [$detail['stochastic'] ?? 0, 5],
                    ]]];

            foreach ($categories as $cat_name => $cat): ?>
            <div style="margin-bottom:1.25rem">
                <div style="display:flex;justify-content:space-between;margin-bottom:.4rem">
                    <strong><?= $cat_name ?></strong>
                    <span><?= round($cat['val'], 1) ?> / <?= $cat['max'] ?></span>
                </div>
                <div style="background:var(--bg-input);border-radius:6px;height:10px;overflow:hidden">
                    <div style="background:var(--primary);height:100%;width:<?= $cat['max'] > 0 ? round(($cat['val'] / $cat['max']) * 100) : 0 ?>%;border-radius:6px;transition:width .3s"></div>
                </div>
                <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:.25rem .5rem;margin-top:.35rem;font-size:.85rem;color:var(--text-muted)">
                    <?php foreach ($cat['items'] as $label => [$val, $max]): ?>
                    <span><?= $label ?>: <strong style="color:var(--text)"><?= round($val, 1) ?></strong>/<?= $max ?></span>
                    <?php endforeach; ?>
                </div>
            </div>
            <?php endforeach; ?>
        </div>
    </div>

    <!-- Context -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.25rem">
        <div class="card">
            <div class="card-header"><h2>Market Context</h2></div>
            <div class="table-wrapper">
                <table class="data-table">
                    <tbody>
                        <tr><td>Mode</td><td><span class="badge"><?= strtoupper($signal['mode']) ?></span></td></tr>
                        <tr><td>Timeframe</td><td><?= htmlspecialchars($signal['timeframe']) ?></td></tr>
                        <tr><td>HTF Trend</td><td><?= htmlspecialchars($signal['htf_trend'] ?? 'N/A') ?></td></tr>
                        <tr><td>MTF Trend</td><td><?= htmlspecialchars($signal['mtf_trend'] ?? 'N/A') ?></td></tr>
                        <tr><td>LTF Signal</td><td><?= htmlspecialchars($signal['ltf_signal'] ?? 'N/A') ?></td></tr>
                        <tr><td>Market Regime</td><td><?= htmlspecialchars(str_replace('_', ' ', $signal['market_regime'] ?? 'N/A')) ?></td></tr>
                        <tr><td>News Sentiment</td><td><?= htmlspecialchars($signal['news_sentiment'] ?? 'neutral') ?></td></tr>
                        <tr><td>AI Confidence</td><td><?= $signal['ai_confidence'] ? $signal['ai_confidence'] . '%' : '—' ?></td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <div class="card">
            <div class="card-header"><h2>Reasoning</h2></div>
            <div class="card-body">
                <pre style="white-space:pre-wrap;font-size:.85rem;color:var(--text-muted);margin:0"><?= htmlspecialchars($signal['reasoning'] ?? 'No reasoning recorded') ?></pre>
            </div>
        </div>
    </div>

    <?php if ($snap): ?>
    <div class="card">
        <div class="card-header"><h2>Indicator Snapshot</h2></div>
        <div class="card-body">
            <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:.5rem;font-size:.85rem">
                <?php foreach ($snap as $key => $val):
                    if (is_array($val)) continue;
                    $display = is_numeric($val) ? round((float)$val, 5) : $val;
                ?>
                <div style="display:flex;justify-content:space-between;padding:.35rem .5rem;background:var(--bg-input);border-radius:4px">
                    <span class="text-muted"><?= htmlspecialchars(str_replace('_', ' ', $key)) ?></span>
                    <strong><?= htmlspecialchars($display) ?></strong>
                </div>
                <?php endforeach; ?>
            </div>
        </div>
    </div>
    <?php endif; ?>

    <?php
    require_once __DIR__ . '/../includes/footer.php';
    exit;
}

// ── Filters ────────────────────────────────────────────────────────────────
$status = $_GET['status'] ?? '';
$pair   = $_GET['pair']   ?? '';
$page   = max(1, (int)($_GET['page'] ?? 1));
$per    = 25;
$offset = ($page - 1) * $per;

$where  = [];
$params = [];

if ($status) { $where[] = "status = ?"; $params[] = $status; }
if ($pair)   { $where[] = "pair = ?";   $params[] = $pair; }

$where_sql = $where ? ('WHERE ' . implode(' AND ', $where)) : '';

$total = (int)(db_one(
    "SELECT COUNT(*) as cnt FROM signals $where_sql",
    $params
)['cnt'] ?? 0);

$pages = (int)ceil($total / $per);

$signals = db_query(
    "SELECT * FROM signals $where_sql ORDER BY created_at DESC LIMIT ? OFFSET ?",
    array_merge($params, [$per, $offset])
);

// Filters data
$all_pairs = db_query("SELECT symbol FROM pairs ORDER BY symbol");
$statuses  = ['OPEN', 'CLOSED_TP', 'CLOSED_SL', 'CLOSED_MANUAL', 'EXPIRED', 'CANCELLED'];

$page_title = 'Signals';
require_once __DIR__ . '/../includes/header.php';
?>

<!-- ── Filter Bar ─────────────────────────────────────────────────────────── -->
<div class="card">
    <div class="card-body">
        <form method="GET" action="/signals.php" class="filter-bar">
            <select name="status" class="form-select w-auto">
                <option value="">All Statuses</option>
                <?php foreach ($statuses as $s): ?>
                <option value="<?= $s ?>" <?= $status === $s ? 'selected' : '' ?>><?= $s ?></option>
                <?php endforeach; ?>
            </select>

            <select name="pair" class="form-select w-auto">
                <option value="">All Pairs</option>
                <?php foreach ($all_pairs as $p): ?>
                <option value="<?= $p['symbol'] ?>" <?= $pair === $p['symbol'] ? 'selected' : '' ?>>
                    <?= $p['symbol'] ?>
                </option>
                <?php endforeach; ?>
            </select>

            <button type="submit" class="btn btn-primary btn-sm">Filter</button>
            <a href="/signals.php" class="btn btn-secondary btn-sm">Clear</a>

            <span class="text-muted" style="margin-left:auto">
                <?= number_format($total) ?> signals found
            </span>
        </form>
    </div>
</div>

<!-- ── Signals Table ──────────────────────────────────────────────────────── -->
<div class="card">
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
                    <th>Status</th>
                    <th>P&L (pips)</th>
                    <th>Time</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>
            <?php if (empty($signals)): ?>
            <tr><td colspan="11" style="text-align:center;padding:2rem;color:var(--text-muted)">
                No signals found.
            </td></tr>
            <?php endif; ?>
            <?php foreach ($signals as $s): ?>
                <?php
                $status_class = match($s['status']) {
                    'OPEN'          => 'badge-info',
                    'CLOSED_TP'     => 'badge-success',
                    'CLOSED_SL'     => 'badge-danger',
                    default         => ''
                };
                $pips = $s['actual_pips'] ?? null;
                ?>
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
                    <td>
                        <span class="badge <?= $status_class ?>">
                            <?= htmlspecialchars($s['status']) ?>
                        </span>
                    </td>
                    <td class="<?= ($pips ?? 0) >= 0 ? 'text-success' : 'text-danger' ?>">
                        <?php if ($pips !== null): ?>
                            <?= ($pips >= 0 ? '+' : '') . number_format((float)$pips, 1) ?>
                        <?php else: ?>
                            <span class="text-muted">—</span>
                        <?php endif; ?>
                    </td>
                    <td>
                        <small><?= date('m/d h:i A', strtotime($s['created_at'])) ?></small>
                    </td>
                    <td>
                        <?php if ($s['status'] === 'OPEN'): ?>
                        <button class="btn btn-xs btn-danger"
                                onclick="openCloseModal('<?= htmlspecialchars($s['signal_id']) ?>',
                                         '<?= $s['entry_price'] ?>')">
                            Close
                        </button>
                        <?php else: ?>
                        <a href="/signals.php?id=<?= urlencode($s['signal_id']) ?>"
                           class="btn btn-xs">View</a>
                        <?php endif; ?>
                    </td>
                </tr>
            <?php endforeach; ?>
            </tbody>
        </table>
    </div>

    <!-- Pagination -->
    <?php if ($pages > 1): ?>
    <div class="card-body pagination">
        <?php for ($i = 1; $i <= $pages; $i++): ?>
        <a href="?page=<?= $i ?>&status=<?= urlencode($status) ?>&pair=<?= urlencode($pair) ?>"
           class="btn btn-sm <?= $i === $page ? 'btn-primary' : 'btn-secondary' ?>">
            <?= $i ?>
        </a>
        <?php endfor; ?>
    </div>
    <?php endif; ?>
</div>

<!-- ── Close Signal Modal ─────────────────────────────────────────────────── -->
<div id="close-modal" class="modal-overlay" onclick="if(event.target===this)closeModal()">
    <div class="modal-box">
        <h3>Close Signal</h3>
        <p>Entry price: <strong id="close-entry-price"></strong></p>
        <div class="form-group" style="margin-top:1rem">
            <label>Close Price</label>
            <input type="number" id="close-price-input" class="form-input"
                   step="0.00001" placeholder="e.g. 1.09250">
        </div>
        <div class="form-group">
            <label>Reason</label>
            <select id="close-reason-select" class="form-select">
                <option value="MANUAL">Manual</option>
                <option value="TP">Take Profit</option>
                <option value="SL">Stop Loss</option>
            </select>
        </div>
        <meta name="csrf-token" content="<?= csrf_token() ?>">
        <div class="modal-actions">
            <button class="btn btn-danger" onclick="submitCloseSignal()">Close Signal</button>
            <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
        </div>
    </div>
</div>

<style>
.filter-bar { display:flex; gap:.75rem; align-items:center; flex-wrap:wrap; }
.w-auto { width:auto; min-width:120px; }
.pagination { display:flex; gap:.5rem; flex-wrap:wrap; }
.modal-overlay {
    display:none; position:fixed; inset:0;
    background:rgba(0,0,0,.6); z-index:999;
    align-items:center; justify-content:center;
}
.modal-overlay.open { display:flex; }
.modal-box {
    background:var(--bg-card); border:1px solid var(--border);
    border-radius:var(--radius); padding:1.5rem; min-width:320px;
    box-shadow:var(--shadow);
}
.modal-box h3 { margin-bottom:.75rem; }
.modal-actions { display:flex; gap:.75rem; margin-top:1rem; }
.badge-info    { background:rgba(6,182,212,.15); color:var(--info); }
.badge-success { background:rgba(34,197,94,.15); color:var(--success); }
.badge-danger  { background:rgba(239,68,68,.15); color:var(--danger); }
</style>

<?php require_once __DIR__ . '/../includes/footer.php'; ?>
