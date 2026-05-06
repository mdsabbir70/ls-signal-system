<?php
require_once __DIR__ . '/../includes/config.php';
require_once __DIR__ . '/../includes/db.php';
require_once __DIR__ . '/../includes/auth.php';

require_login();
$page_title = 'Strategy Discovery';

// All pairs for dropdown
$pairs = db_query("SELECT symbol, category FROM pairs ORDER BY category, symbol", []);

require_once __DIR__ . '/../includes/header.php';
?>

<style>
/* ── Discovery Page Styles ───────────────────────────── */
.disc-grid { display:grid; grid-template-columns:340px 1fr; gap:1.25rem; align-items:start; }
@media(max-width:900px){ .disc-grid { grid-template-columns:1fr; } }

.tf-grid  { display:grid; grid-template-columns:repeat(3,1fr); gap:.5rem; }
.tf-check { display:flex; align-items:center; gap:.4rem; cursor:pointer; font-size:.88rem;
            padding:.35rem .6rem; border:1px solid var(--border); border-radius:6px;
            transition:all .15s; user-select:none; }
.tf-check:hover { border-color:var(--primary); background:rgba(99,102,241,.07); }
.tf-check input { accent-color:var(--primary); width:14px; height:14px; }
.tf-check.checked { border-color:var(--primary); background:rgba(99,102,241,.1); font-weight:600; }

.progress-bar { height:6px; background:var(--border); border-radius:3px; overflow:hidden; }
.progress-fill { height:100%; background:var(--primary); border-radius:3px;
                 transition:width .4s; animation:pulse-bar 1.5s ease-in-out infinite; }
@keyframes pulse-bar { 0%,100%{opacity:.7} 50%{opacity:1} }

.status-box { padding:1rem; border-radius:8px; border:1px solid var(--border);
              font-size:.88rem; line-height:1.7; color:#1a1a1a; }
.status-box.running  { border-color:#f59e0b; background:#fffbeb; color:#78350f; }
.status-box.done     { border-color:#10b981; background:#ecfdf5; color:#065f46; }
.status-box.error    { border-color:#ef4444; background:#fef2f2; color:#991b1b; }

.stat-row { display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:1rem; }
.stat-box { flex:1; min-width:100px; text-align:center; padding:.75rem 1rem;
            border:1px solid var(--border); border-radius:8px; background:var(--bg); }
.stat-box .num { font-size:1.5rem; font-weight:700; color:var(--primary); }
.stat-box .lbl { font-size:.75rem; color:var(--text-muted); margin-top:.1rem; }

.cat-badge { font-size:.7rem; padding:.15rem .5rem; border-radius:20px; font-weight:600;
             display:inline-block; text-transform:uppercase; letter-spacing:.03em; }
.cat-trend       { background:#dbeafe; color:#1d4ed8; }
.cat-reversal    { background:#fce7f3; color:#be185d; }
.cat-multi       { background:#f3e8ff; color:#7e22ce; }
.cat-breakout    { background:#d1fae5; color:#065f46; }
.cat-momentum    { background:#fef3c7; color:#92400e; }
.cat-volatility  { background:#ffe4e6; color:#9f1239; }
.cat-price_action{ background:#e0f2fe; color:#0369a1; }

.wr-bar { width:60px; height:8px; background:var(--border); border-radius:4px;
          display:inline-block; vertical-align:middle; margin-left:6px; overflow:hidden; }
.wr-fill { height:100%; border-radius:4px; background:#10b981; }

.pill-pf  { font-size:.75rem; padding:.1rem .45rem; border-radius:12px; font-weight:700; }
.pill-pos { background:#d1fae5; color:#065f46; }
.pill-neg { background:#fee2e2; color:#991b1b; }

.filter-row { display:flex; gap:.6rem; align-items:center; flex-wrap:wrap;
              padding:.75rem 0 .75rem; border-bottom:1px solid var(--border); margin-bottom:.75rem;
              color:#1a1a1a; }
.filter-row label { color:#1a1a1a; }
.filter-row select, .filter-row input[type=text] {
    padding:.3rem .6rem; font-size:.82rem; border:1px solid var(--border);
    border-radius:6px; background:#fff; color:#1a1a1a; }

#results-table th { white-space:nowrap; }
#results-table td { vertical-align:middle; }

#history-table { min-width:900px; }
#history-table th { white-space:nowrap; font-size:.78rem; padding:.5rem .6rem; }
#history-table td { font-size:.82rem; padding:.5rem .6rem; vertical-align:middle; white-space:nowrap; }
#history-table td:nth-child(7) { white-space:normal; min-width:140px; max-width:200px; }

.sort-btn { cursor:pointer; user-select:none; }
.sort-btn:after { content:' ↕'; opacity:.4; font-size:.8em; }
.sort-btn.asc:after  { content:' ↑'; opacity:1; }
.sort-btn.desc:after { content:' ↓'; opacity:1; }

/* Multi-TF badges */
.tf-pill { display:inline-block; font-size:.65rem; font-weight:700; padding:.1rem .35rem;
           border-radius:4px; margin:.1rem .1rem 0 0; letter-spacing:.02em; }
.tf-pill-active   { background:#6366f1; color:#fff; }
.tf-pill-inactive { background:var(--border); color:var(--text-muted); }
.multi-tf-badge { display:inline-block; font-size:.65rem; font-weight:700; padding:.15rem .4rem;
                  border-radius:10px; background:#f59e0b; color:#fff; margin-left:4px;
                  vertical-align:middle; }
</style>

<!-- ── Main Layout ─────────────────────────────────────────────── -->
<div class="disc-grid">

    <!-- Left: Form -->
    <div>
        <div class="card">
            <div class="card-header">
                <h2>🔍 Strategy Discovery</h2>
            </div>
            <div class="card-body" style="display:flex;flex-direction:column;gap:1rem">

                <!-- Pair -->
                <div class="form-group" style="margin:0">
                    <label>Pair</label>
                    <select id="disc-pair" class="form-control">
                        <?php
                        $last_cat = '';
                        foreach ($pairs as $p):
                            if ($p['category'] !== $last_cat):
                                if ($last_cat !== '') echo '</optgroup>';
                                $label = ucfirst(strtolower($p['category']));
                                echo "<optgroup label=\"{$label}\">";
                                $last_cat = $p['category'];
                            endif;
                            $sel = ($p['symbol'] === 'EURUSD') ? 'selected' : '';
                            echo "<option value=\"{$p['symbol']}\" {$sel}>{$p['symbol']}</option>";
                        endforeach;
                        if ($last_cat !== '') echo '</optgroup>';
                        ?>
                    </select>
                </div>

                <!-- Timeframes -->
                <div class="form-group" style="margin:0">
                    <label style="display:flex;justify-content:space-between">
                        <span>Timeframes</span>
                        <span style="font-size:.75rem;color:var(--text-muted)">
                            <a href="#" id="tf-all" style="text-decoration:none">All</a> /
                            <a href="#" id="tf-main" style="text-decoration:none">Main (H1 H4 D1)</a>
                        </span>
                    </label>
                    <div class="tf-grid">
                        <?php foreach (['M5','M15','M30','H1','H4','D1'] as $tf):
                            $checked = in_array($tf, ['H1','H4','D1']) ? 'checked' : '';
                            $cls = $checked ? 'checked' : '';
                        ?>
                        <label class="tf-check <?= $cls ?>" id="lbl-<?= $tf ?>">
                            <input type="checkbox" class="tf-cb" value="<?= $tf ?>" <?= $checked ?>>
                            <?= $tf ?>
                        </label>
                        <?php endforeach; ?>
                    </div>
                    <div style="font-size:.72rem;color:var(--text-muted);margin-top:.3rem">
                        M5/M15/M30 = ~60 days data &nbsp;|&nbsp; H1/H4 = ~2 years &nbsp;|&nbsp; D1 = ~10 years
                    </div>
                </div>

                <!-- Min Win Rate -->
                <div class="form-group" style="margin:0">
                    <label>Min Win Rate: <strong id="wr-val">60%</strong></label>
                    <input type="range" id="disc-wr" min="50" max="80" step="1" value="60"
                           style="width:100%;accent-color:var(--primary)"
                           oninput="document.getElementById('wr-val').textContent=this.value+'%'">
                    <div style="display:flex;justify-content:space-between;font-size:.72rem;color:var(--text-muted)">
                        <span>50% (more)</span><span>65% (balanced)</span><span>80% (strict)</span>
                    </div>
                </div>

                <!-- Min Trades -->
                <div class="form-group" style="margin:0">
                    <label>Min Trades (for validity)</label>
                    <select id="disc-mintrades" class="form-control">
                        <option value="5" selected>5 trades</option>
                        <option value="10">10 trades</option>
                        <option value="20">20 trades</option>
                        <option value="30">30 trades</option>
                    </select>
                </div>

                <!-- Data Period -->
                <div class="form-group" style="margin:0">
                    <label>Data Period <span style="font-size:.72rem;color:var(--text-muted)">(yfinance limit: M5/M15/M30 max 60d, H1/H4 max 2y)</span></label>
                    <select id="disc-lookback" class="form-control">
                        <option value="0">Default (auto per TF)</option>
                        <option value="30">30 Days</option>
                        <option value="60">60 Days</option>
                        <option value="90">3 Months</option>
                        <option value="180">6 Months</option>
                        <option value="365">1 Year</option>
                        <option value="730">2 Years</option>
                        <option value="1825">5 Years</option>
                        <option value="3650">10 Years</option>
                    </select>
                </div>

                <!-- Run Button -->
                <button id="run-btn" class="btn btn-primary" style="width:100%;font-size:1rem;padding:.7rem">
                    ▶ Run Discovery
                </button>

                <div style="font-size:.75rem;color:var(--text-muted);text-align:center;line-height:1.5">
                    Bot tests <strong>114 strategies × 9 SL/TP</strong> per timeframe.<br>
                    Estimated time: ~10s per TF (H1: 15s, D1: 5s)
                </div>

            </div><!-- card-body -->
        </div><!-- card -->

        <!-- Status box -->
        <div id="status-area" style="margin-top:1rem;display:none">
            <div class="progress-bar" id="progress-bar" style="display:none;margin-bottom:.75rem">
                <div class="progress-fill" id="progress-fill" style="width:30%"></div>
            </div>
            <div class="status-box" id="status-box"></div>
        </div>

    </div><!-- left -->

    <!-- Right: Results -->
    <div id="results-area">
        <div class="card" style="min-height:300px">
            <div class="card-header" style="gap:.75rem">
                <h2>Results</h2>
                <div id="results-header-stats" style="display:flex;gap:.5rem;flex-wrap:wrap"></div>
            </div>
            <div class="card-body">
                <div id="results-empty" style="text-align:center;padding:3rem;color:var(--text-muted)">
                    <div style="font-size:2.5rem;margin-bottom:.75rem">🔍</div>
                    <div>Configure settings and click <strong>Run Discovery</strong></div>
                    <div style="font-size:.8rem;margin-top:.5rem">
                        The bot will test every indicator combination and find strategies with your target win rate.
                    </div>
                </div>

                <!-- Filter row (hidden until results) -->
                <div id="filter-row" class="filter-row" style="display:none">
                    <label style="font-size:.82rem;color:#1a1a1a">Filter:</label>
                    <input type="text" id="filter-strategy" placeholder="Strategy name..." style="width:160px">
                    <select id="filter-tf">
                        <option value="">All TF</option>
                        <option>M5</option><option>M15</option><option>M30</option>
                        <option>H1</option><option>H4</option><option>D1</option>
                    </select>
                    <select id="filter-cat">
                        <option value="">All Categories</option>
                        <option value="trend">Trend</option>
                        <option value="reversal">Reversal</option>
                        <option value="multi">Multi-indicator</option>
                        <option value="breakout">Breakout</option>
                        <option value="momentum">Momentum</option>
                        <option value="price_action">Price Action</option>
                    </select>
                    <label style="font-size:.82rem;color:#1a1a1a;cursor:pointer"
                           title="Only show strategies profitable in 2+ timeframes">
                        <input type="checkbox" id="filter-multitf"> Multi-TF only ★
                    </label>
                    <label style="font-size:.82rem;color:#1a1a1a;margin-left:auto;cursor:pointer">
                        <input type="checkbox" id="filter-profitable" checked> Profitable only
                    </label>
                </div>

                <!-- Results Table -->
                <div id="results-table-wrap" style="display:none;overflow-x:auto">
                    <table class="table" id="results-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th class="sort-btn" data-col="strategy_name">Strategy</th>
                                <th class="sort-btn" data-col="timeframe">TF</th>
                                <th class="sort-btn" data-col="_tf_count" title="Number of timeframes this strategy is profitable in">TF Count ★</th>
                                <th>Category</th>
                                <th class="sort-btn" data-col="total_trades">Trades</th>
                                <th class="sort-btn asc" data-col="win_rate">Win%</th>
                                <th class="sort-btn" data-col="total_pips">Pips</th>
                                <th class="sort-btn" data-col="profit_factor">PF</th>
                                <th class="sort-btn" data-col="sharpe">Sharpe</th>
                                <th>SL/TP</th>
                            </tr>
                        </thead>
                        <tbody id="results-tbody"></tbody>
                    </table>
                    <div id="results-count" style="font-size:.8rem;color:var(--text-muted);padding:.5rem 0"></div>
                </div>

            </div><!-- card-body -->
        </div><!-- card -->
    </div><!-- right -->
</div><!-- grid -->


<script>
// ── Data Store ────────────────────────────────────────────────────────────────
let allResults  = [];
let multiTFMap  = {};   // key → Set of TFs where strategy is profitable
let sortCol     = 'win_rate';
let sortDir     = 'desc';
let pollTimer   = null;
let currentId   = null;

// ── TF Checkboxes ─────────────────────────────────────────────────────────────
document.querySelectorAll('.tf-cb').forEach(cb => {
    cb.addEventListener('change', () => {
        const lbl = document.getElementById('lbl-' + cb.value);
        lbl.classList.toggle('checked', cb.checked);
    });
});

document.getElementById('tf-all').addEventListener('click', e => {
    e.preventDefault();
    document.querySelectorAll('.tf-cb').forEach(cb => {
        cb.checked = true;
        document.getElementById('lbl-' + cb.value).classList.add('checked');
    });
});

document.getElementById('tf-main').addEventListener('click', e => {
    e.preventDefault();
    document.querySelectorAll('.tf-cb').forEach(cb => {
        const main = ['H1','H4','D1'].includes(cb.value);
        cb.checked = main;
        document.getElementById('lbl-' + cb.value).classList.toggle('checked', main);
    });
});

// ── Sort ─────────────────────────────────────────────────────────────────────
document.querySelectorAll('.sort-btn').forEach(th => {
    th.addEventListener('click', () => {
        const col = th.dataset.col;
        if (sortCol === col) {
            sortDir = sortDir === 'asc' ? 'desc' : 'asc';
        } else {
            sortCol = col;
            sortDir = 'desc';
        }
        document.querySelectorAll('.sort-btn').forEach(h => {
            h.classList.remove('asc','desc');
        });
        th.classList.add(sortDir);
        renderTable();
    });
});

// ── Filters ───────────────────────────────────────────────────────────────────
['filter-strategy','filter-tf','filter-cat','filter-profitable','filter-multitf'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', renderTable);
    if (el && el.tagName === 'INPUT' && el.type === 'text')
        el.addEventListener('input', renderTable);
});

// ── Run Button ───────────────────────────────────────────────────────────────
document.getElementById('run-btn').addEventListener('click', () => {
    const tfs = Array.from(document.querySelectorAll('.tf-cb:checked')).map(c => c.value);
    if (!tfs.length) { alert('Please select at least one timeframe.'); return; }

    const pair     = document.getElementById('disc-pair').value;
    const wr       = document.getElementById('disc-wr').value;
    const mintrd   = document.getElementById('disc-mintrades').value;
    const lookback = document.getElementById('disc-lookback').value;

    setRunning(true, `Starting discovery for ${pair}...`);

    const fd = new FormData();
    fd.append('pair', pair);
    tfs.forEach(tf => fd.append('timeframes[]', tf));
    fd.append('min_win_rate', wr);
    fd.append('min_trades', mintrd);
    fd.append('lookback_days', lookback);

    fetch('/actions/discovery_run.php', { method: 'POST', body: fd })
        .then(r => r.json())
        .then(data => {
            if (!data.success && !data.discovery_id) {
                showError(data.error || 'Failed to start discovery');
                setRunning(false);
                return;
            }
            currentId = data.discovery_id;
            const lbLabel = lookback === '0' ? 'default' : lookback + ' days';
            showStatus('running', `Discovery started for <strong>${pair}</strong> [${tfs.join(', ')}]<br>
                Data: <strong>${lbLabel}</strong> &nbsp;|&nbsp; ID: ${currentId}<br>
                Estimated time: ${tfs.length * 15}–${tfs.length * 30}s`);
            pollTimer = setInterval(pollStatus, 4000);
        })
        .catch(e => { showError(e.message); setRunning(false); });
});

// ── Poll Status ───────────────────────────────────────────────────────────────
function pollStatus() {
    fetch('/actions/discovery_status.php')
        .then(r => r.json())
        .then(data => {
            if (!data.discoveries) return;
            const disc = data.discoveries[currentId];
            if (!disc) return;

            if (disc.status === 'completed') {
                clearInterval(pollTimer);
                setRunning(false);
                const profitable = disc.total_profitable || 0;
                const tested     = disc.total_tested || 0;
                const winners    = disc.total_winners || 0;
                showStatus('done',
                    `✅ Discovery complete!<br>
                    Tested: <strong>${tested}</strong> strategies &nbsp;|&nbsp;
                    Winners (WR≥threshold): <strong>${winners}</strong> &nbsp;|&nbsp;
                    <strong style="color:#10b981">${profitable} profitable</strong> (positive pips + PF&gt;1)`
                );
                displayResults(disc.results || [], disc);
            }
            else if (disc.status === 'failed') {
                clearInterval(pollTimer);
                setRunning(false);
                showError(disc.error || 'Discovery failed');
            }
            else {
                // Still running — animate progress
                const fill = document.getElementById('progress-fill');
                const w = parseFloat(fill.style.width) || 30;
                fill.style.width = Math.min(w + 8, 90) + '%';
            }
        })
        .catch(() => {});
}

// ── Display Results ───────────────────────────────────────────────────────────
function buildMultiTFMap(results) {
    // key = strategy_name + '|' + params_label (same strategy, same params)
    const map = {};
    results.forEach(r => {
        if (r.total_pips > 0 && r.profit_factor > 1) {
            const key = (r.strategy_name || r.strategy) + '|' + (r.params_label || '');
            if (!map[key]) map[key] = new Set();
            map[key].add(r.timeframe);
        }
    });
    return map;
}

function displayResults(results, meta) {
    allResults = results;
    multiTFMap = buildMultiTFMap(results);

    // Count strategies profitable in 2+ TFs
    const multiTFCount = Object.values(multiTFMap).filter(s => s.size >= 2).length;

    document.getElementById('results-empty').style.display = 'none';
    document.getElementById('filter-row').style.display = 'flex';
    document.getElementById('results-table-wrap').style.display = 'block';

    // Header stats
    const stats = document.getElementById('results-header-stats');
    stats.innerHTML = `
        <div class="stat-box"><div class="num">${meta.total_tested||0}</div><div class="lbl">Tested</div></div>
        <div class="stat-box"><div class="num" style="color:#f59e0b">${meta.total_winners||0}</div><div class="lbl">Winners (WR%)</div></div>
        <div class="stat-box"><div class="num" style="color:#10b981">${meta.total_profitable||0}</div><div class="lbl">Profitable</div></div>
        <div class="stat-box"><div class="num" style="color:#f59e0b">${multiTFCount}</div><div class="lbl">Multi-TF ★</div></div>
    `;

    renderTable();
}

const ALL_TFS = ['M5','M15','M30','H1','H4','D1'];

function renderTable() {
    const qStr     = (document.getElementById('filter-strategy')?.value || '').toLowerCase();
    const qTF      = document.getElementById('filter-tf')?.value || '';
    const qCat     = document.getElementById('filter-cat')?.value || '';
    const onlyProf = document.getElementById('filter-profitable')?.checked ?? true;
    const onlyMTF  = document.getElementById('filter-multitf')?.checked ?? false;

    // Attach _tf_count to each row for sorting/filtering
    let rows = allResults.map(r => {
        const key = (r.strategy_name || r.strategy) + '|' + (r.params_label || '');
        const tfs = multiTFMap[key] || new Set();
        return { ...r, _tf_count: tfs.size, _tf_set: tfs };
    });

    rows = rows.filter(r => {
        if (onlyProf && (r.total_pips <= 0 || r.profit_factor <= 1)) return false;
        if (onlyMTF  && r._tf_count < 2) return false;
        if (qStr && !(r.strategy || '').toLowerCase().includes(qStr) &&
                    !(r.strategy_name || '').toLowerCase().includes(qStr)) return false;
        if (qTF  && r.timeframe !== qTF) return false;
        if (qCat && r.category !== qCat) return false;
        return true;
    });

    // Sort
    rows.sort((a,b) => {
        let va = a[sortCol] ?? 0, vb = b[sortCol] ?? 0;
        if (typeof va === 'string') va = va.toLowerCase();
        if (typeof vb === 'string') vb = vb.toLowerCase();
        return sortDir === 'asc' ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
    });

    const tbody = document.getElementById('results-tbody');
    tbody.innerHTML = rows.map((r, i) => {
        const pfCls  = r.profit_factor >= 1 ? 'pill-pos' : 'pill-neg';
        const pipCol = r.total_pips >= 0 ? '#10b981' : '#ef4444';
        const pipSign = r.total_pips >= 0 ? '+' : '';
        const catCls  = 'cat-' + (r.category || 'trend');
        const wrPct   = Math.min(r.win_rate, 100);
        const sltp    = r.sl_tp || '';

        // Build TF pills — show all 6 TFs, highlight those where this strategy is profitable
        const tfPills = ALL_TFS.map(tf => {
            const active = r._tf_set.has(tf);
            return `<span class="tf-pill ${active ? 'tf-pill-active' : 'tf-pill-inactive'}">${tf}</span>`;
        }).join('');

        // Multi-TF badge
        const mtfBadge = r._tf_count >= 2
            ? `<span class="multi-tf-badge" title="Profitable in ${r._tf_count} timeframes">★ ${r._tf_count}TF</span>`
            : '';

        // Row highlight for multi-TF
        const rowStyle = r._tf_count >= 2 ? 'background:rgba(245,158,11,.06)' : '';

        return `<tr style="${rowStyle}">
            <td style="color:var(--text-muted);font-size:.8rem">${i+1}</td>
            <td>
                <div style="font-size:.82rem;font-weight:600">
                    ${escHtml(r.strategy_name || r.strategy)} ${mtfBadge}
                </div>
                <div style="font-size:.72rem;color:var(--text-muted)">${escHtml(r.params_label || '')}</div>
            </td>
            <td><strong>${escHtml(r.timeframe)}</strong></td>
            <td style="white-space:nowrap">${tfPills}</td>
            <td><span class="cat-badge ${catCls}">${escHtml(r.category||'')}</span></td>
            <td style="text-align:center">${r.total_trades}</td>
            <td>
                <strong style="color:var(--primary)">${r.win_rate.toFixed(1)}%</strong>
                <div class="wr-bar"><div class="wr-fill" style="width:${wrPct}%"></div></div>
            </td>
            <td><strong style="color:${pipCol}">${pipSign}${r.total_pips.toFixed(1)}</strong></td>
            <td><span class="pill-pf ${pfCls}">${r.profit_factor.toFixed(2)}</span></td>
            <td style="font-size:.82rem">${r.sharpe.toFixed(2)}</td>
            <td style="font-size:.72rem;color:var(--text-muted)">${escHtml(sltp)}</td>
        </tr>`;
    }).join('');

    const multiCount = rows.filter(r => r._tf_count >= 2).length;
    document.getElementById('results-count').textContent =
        `Showing ${rows.length} of ${allResults.length} results` +
        (multiCount > 0 ? ` — ${multiCount} multi-TF strategies ★` : '');
}

function escHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── UI Helpers ────────────────────────────────────────────────────────────────
function setRunning(on, msg) {
    const btn = document.getElementById('run-btn');
    btn.disabled = on;
    btn.textContent = on ? '⏳ Running...' : '▶ Run Discovery';
    const area = document.getElementById('status-area');
    const pb   = document.getElementById('progress-bar');
    if (on) {
        area.style.display = 'block';
        pb.style.display   = 'block';
        document.getElementById('progress-fill').style.width = '15%';
    } else {
        pb.style.display = 'none';
    }
}

function showStatus(type, html) {
    const area = document.getElementById('status-area');
    const box  = document.getElementById('status-box');
    area.style.display = 'block';
    box.className = 'status-box ' + (type === 'running' ? 'running' : type === 'done' ? 'done' : 'error');
    box.innerHTML  = html;
}

function showError(msg) {
    showStatus('error', '❌ Error: ' + escHtml(msg));
}

// ── Load History on page load ─────────────────────────────────────────────
function loadHistory() {
    fetch('/actions/discovery_history.php')
        .then(r => r.json())
        .then(data => {
            const rows = data.history || [];
            renderHistory(rows);
        })
        .catch(() => {});
}

function renderHistory(rows) {
    const tbody  = document.getElementById('history-tbody');
    const empty  = document.getElementById('history-empty');
    const table  = document.getElementById('history-table-wrap');
    const count  = document.getElementById('history-count');

    if (!rows.length) {
        empty.style.display = 'block';
        table.style.display = 'none';
        return;
    }
    empty.style.display = 'none';
    table.style.display = 'block';

    tbody.innerHTML = rows.map(r => {
        const tfs     = escHtml(r.timeframes || '');
        const best    = escHtml(r.best_strategy || '—');
        const wr      = r.best_wr   ? r.best_wr.toFixed(1)  + '%' : '—';
        const pips    = r.best_pips != null ? (r.best_pips >= 0 ? '+' : '') + r.best_pips.toFixed(1) : '—';
        const pf      = r.best_pf   ? r.best_pf.toFixed(2)          : '—';
        const pipCol  = r.best_pips >= 0 ? '#10b981' : '#ef4444';
        const date    = escHtml(r.created_at || '');

        return `<tr id="hist-row-${escHtml(r.discovery_id)}">
            <td><strong>${escHtml(r.pair)}</strong></td>
            <td style="font-size:.78rem;color:var(--text-muted)">${tfs}</td>
            <td style="text-align:center">${r.min_win_rate}%</td>
            <td style="text-align:center">${r.total_tested}</td>
            <td style="text-align:center;color:#f59e0b;font-weight:600">${r.total_winners}</td>
            <td style="text-align:center;color:#10b981;font-weight:700">${r.total_profitable}</td>
            <td style="font-size:.78rem;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${best}">${best}</td>
            <td style="color:var(--primary);font-weight:600">${wr}</td>
            <td style="color:${pipCol};font-weight:600">${pips}</td>
            <td>${pf}</td>
            <td style="font-size:.75rem;color:var(--text-muted)">${date}</td>
            <td>
                <button class="btn btn-sm btn-outline"
                    style="color:#ef4444;border-color:#ef4444;padding:.2rem .6rem;font-size:.75rem"
                    onclick="deleteHistory('${escHtml(r.discovery_id)}')">
                    Delete
                </button>
            </td>
        </tr>`;
    }).join('');

    count.textContent = `${rows.length} run(s) saved`;
}

function deleteHistory(discId) {
    if (!confirm('এই Discovery result মুছে ফেলবেন?')) return;
    const fd = new FormData();
    fd.append('discovery_id', discId);
    fetch('/actions/discovery_delete.php', { method: 'POST', body: fd })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                const row = document.getElementById('hist-row-' + discId);
                if (row) row.remove();
                // Check if table is now empty
                const tbody = document.getElementById('history-tbody');
                if (!tbody.children.length) {
                    document.getElementById('history-empty').style.display = 'block';
                    document.getElementById('history-table-wrap').style.display = 'none';
                }
            } else {
                alert('Delete failed: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(e => alert('Error: ' + e.message));
}

// Reload history after discovery completes
const _origDisplayResults = displayResults;
displayResults = function(results, meta) {
    _origDisplayResults(results, meta);
    setTimeout(loadHistory, 1000); // refresh history after 1s
};

// Load history on page load
loadHistory();
</script>

<!-- ── Discovery History Section ──────────────────────────────────────── -->
<div class="card" style="margin-top:1.5rem">
    <div class="card-header">
        <h2>Discovery History</h2>
        <span id="history-count" style="font-size:.8rem;color:var(--text-muted)"></span>
    </div>
    <div class="card-body">

        <div id="history-empty" style="text-align:center;padding:2rem;color:var(--text-muted);display:none">
            No discovery runs saved yet. Run a discovery to see results here.
        </div>

        <div id="history-table-wrap" style="display:none;overflow-x:auto">
            <table class="table" id="history-table">
                <thead>
                    <tr>
                        <th>Pair</th>
                        <th>Timeframes</th>
                        <th>Min WR</th>
                        <th>Tested</th>
                        <th>Winners</th>
                        <th>Profitable</th>
                        <th>Best Strategy</th>
                        <th>Best WR%</th>
                        <th>Best Pips</th>
                        <th>Best PF</th>
                        <th>Date</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody id="history-tbody"></tbody>
            </table>
            <div id="history-count" style="font-size:.8rem;color:var(--text-muted);padding:.4rem 0"></div>
        </div>

    </div>
</div>

<?php require_once __DIR__ . '/../includes/footer.php'; ?>
