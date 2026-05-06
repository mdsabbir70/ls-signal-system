<?php
require_once __DIR__ . '/../includes/config.php';
require_once __DIR__ . '/../includes/db.php';
require_once __DIR__ . '/../includes/auth.php';

require_login();

$page_title = 'News & Sentiment';

// Filters
$filter_sentiment = $_GET['sentiment'] ?? '';
$filter_currency  = $_GET['currency']  ?? '';
$filter_impact    = $_GET['impact']    ?? '';
$page = max(1, intval($_GET['page'] ?? 1));
$per_page = 20;
$offset   = ($page - 1) * $per_page;

// Build query
$where   = ['1=1'];
$params  = [];

if ($filter_sentiment) {
    $where[]  = 'sentiment = ?';
    $params[] = $filter_sentiment;
}
if ($filter_impact) {
    $where[]  = 'impact_level = ?';
    $params[] = $filter_impact;
}
if ($filter_currency) {
    $where[]  = 'affected_currencies LIKE ?';
    $params[] = '%' . $filter_currency . '%';
}

$where_sql = implode(' AND ', $where);

$total = db_one("SELECT COUNT(*) as cnt FROM news_archive WHERE $where_sql", $params)['cnt'] ?? 0;

$params_paged = array_merge($params, [$per_page, $offset]);
$news = db_query(
    "SELECT * FROM news_archive WHERE $where_sql ORDER BY published_at DESC LIMIT ? OFFSET ?",
    $params_paged
);

// Summary stats
$stats = db_one("SELECT
    COUNT(*) as total,
    SUM(sentiment='bullish') as bullish,
    SUM(sentiment='bearish') as bearish,
    SUM(sentiment='neutral') as neutral,
    SUM(impact_level='high') as high_impact,
    SUM(processed=1) as processed
    FROM news_archive WHERE fetched_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)", []);

$total_pages = ceil($total / $per_page);

require_once __DIR__ . '/../includes/header.php';

// "X minutes ago" helper — DB stores UTC, so compare against UTC
function time_ago(string $datetime): string {
    $utc_now = new DateTime('now', new DateTimeZone('UTC'));
    $dt      = new DateTime($datetime, new DateTimeZone('UTC'));
    $diff    = $utc_now->getTimestamp() - $dt->getTimestamp();
    if ($diff < 0)         return 'Just now';
    if ($diff < 60)        return 'Just now';
    if ($diff < 3600)      return floor($diff / 60) . ' min ago';
    if ($diff < 86400)     return floor($diff / 3600) . 'h ago';
    return floor($diff / 86400) . 'd ago';
}
?>

<!-- Stats -->
<div class="stats-grid" style="grid-template-columns:repeat(auto-fill,minmax(150px,1fr))">
    <div class="stat-card">
        <div class="stat-value"><?= $stats['total'] ?? 0 ?></div>
        <div class="stat-label">Last 24h News</div>
    </div>
    <div class="stat-card stat-profit">
        <div class="stat-value" style="color:var(--buy)"><?= $stats['bullish'] ?? 0 ?></div>
        <div class="stat-label">Bullish</div>
    </div>
    <div class="stat-card stat-loss">
        <div class="stat-value" style="color:var(--sell)"><?= $stats['bearish'] ?? 0 ?></div>
        <div class="stat-label">Bearish</div>
    </div>
    <div class="stat-card">
        <div class="stat-value" style="color:var(--text-muted)"><?= $stats['neutral'] ?? 0 ?></div>
        <div class="stat-label">Neutral</div>
    </div>
    <div class="stat-card">
        <div class="stat-value" style="color:var(--warning)"><?= $stats['high_impact'] ?? 0 ?></div>
        <div class="stat-label">High Impact</div>
    </div>
    <div class="stat-card">
        <div class="stat-value"><?= $stats['processed'] ?? 0 ?></div>
        <div class="stat-label">AI Processed</div>
    </div>
</div>

<!-- Filters -->
<div class="card">
    <div class="card-body">
        <form method="GET" class="controls-row">
            <select name="sentiment" class="form-select" style="max-width:140px" onchange="this.form.submit()">
                <option value="">All Sentiment</option>
                <option value="bullish"  <?= $filter_sentiment==='bullish'  ? 'selected':'' ?>>Bullish</option>
                <option value="bearish"  <?= $filter_sentiment==='bearish'  ? 'selected':'' ?>>Bearish</option>
                <option value="neutral"  <?= $filter_sentiment==='neutral'  ? 'selected':'' ?>>Neutral</option>
            </select>
            <select name="impact" class="form-select" style="max-width:140px" onchange="this.form.submit()">
                <option value="">All Impact</option>
                <option value="high"   <?= $filter_impact==='high'   ? 'selected':'' ?>>High</option>
                <option value="medium" <?= $filter_impact==='medium' ? 'selected':'' ?>>Medium</option>
                <option value="low"    <?= $filter_impact==='low'    ? 'selected':'' ?>>Low</option>
            </select>
            <select name="currency" class="form-select" style="max-width:140px" onchange="this.form.submit()">
                <option value="">All Pairs</option>
                <?php foreach (['EUR','USD','GBP','JPY','XAU','AUD','CAD','CHF'] as $c): ?>
                <option value="<?= $c ?>" <?= $filter_currency===$c ? 'selected':'' ?>><?= $c ?></option>
                <?php endforeach; ?>
            </select>
            <?php if ($filter_sentiment || $filter_currency || $filter_impact): ?>
            <a href="/news.php" class="btn btn-secondary btn-sm">Clear</a>
            <?php endif; ?>
            <span style="color:var(--text-muted);font-size:.8rem;margin-left:auto">
                <?= number_format($total) ?> articles
            </span>
        </form>
    </div>
</div>

<!-- News List -->
<div class="card">
    <div class="card-header">
        <h2>📰 News Feed</h2>
    </div>
    <div class="card-body" style="padding:0">
        <?php if (empty($news)): ?>
        <div style="padding:2rem;text-align:center;color:var(--text-muted)">
            No news articles found.
        </div>
        <?php else: ?>
        <div class="news-list">
        <?php foreach ($news as $item):
            $sentiment   = $item['sentiment'] ?? 'neutral';
            $impact      = $item['impact_level'] ?? 'low';
            $currencies  = json_decode($item['affected_currencies'] ?? '[]', true) ?: [];
            $sent_color  = $sentiment === 'bullish' ? 'var(--buy)' : ($sentiment === 'bearish' ? 'var(--sell)' : 'var(--text-muted)');
            $sent_icon   = $sentiment === 'bullish' ? '▲' : ($sentiment === 'bearish' ? '▼' : '●');
            $impact_color= $impact === 'high' ? 'var(--danger)' : ($impact === 'medium' ? 'var(--warning)' : 'var(--text-muted)');
            $strength    = round(($item['impact_strength'] ?? 0) * 100);
        ?>
        <div class="news-item">
            <div class="news-meta">
                <span class="news-sentiment" style="color:<?= $sent_color ?>">
                    <?= $sent_icon ?> <?= ucfirst($sentiment) ?>
                </span>
                <span class="badge" style="background:<?= $impact_color ?>20;color:<?= $impact_color ?>;border:1px solid <?= $impact_color ?>40">
                    <?= ucfirst($impact) ?> Impact
                </span>
                <?php foreach (array_slice($currencies, 0, 4) as $cur): ?>
                <span class="badge" style="background:rgba(59,130,246,.15);color:var(--primary)"><?= htmlspecialchars($cur) ?></span>
                <?php endforeach; ?>
                <span class="news-time" title="<?= date('d M Y, h:i A', strtotime($item['published_at'])) ?> BDT">
                    🕐 <?= time_ago($item['published_at']) ?>
                    · <?= htmlspecialchars($item['source']) ?>
                </span>
            </div>
            <div class="news-title">
                <?php if ($item['link']): ?>
                <a href="<?= htmlspecialchars($item['link']) ?>" target="_blank" rel="noopener">
                    <?= htmlspecialchars($item['title']) ?>
                </a>
                <?php else: ?>
                <?= htmlspecialchars($item['title']) ?>
                <?php endif; ?>
            </div>
            <?php if ($item['ai_summary']): ?>
            <div class="news-ai-summary">
                🤖 <?= htmlspecialchars($item['ai_summary']) ?>
                <?php if ($item['ai_recommendation']): ?>
                <span class="badge" style="background:<?= $item['ai_recommendation']==='BUY' ? 'rgba(34,197,94,.2)' : ($item['ai_recommendation']==='SELL' ? 'rgba(239,68,68,.2)' : 'rgba(148,163,184,.15)') ?>;color:<?= $item['ai_recommendation']==='BUY' ? 'var(--buy)' : ($item['ai_recommendation']==='SELL' ? 'var(--sell)' : 'var(--text-muted)') ?>">
                    <?= $item['ai_recommendation'] ?>
                </span>
                <?php endif; ?>
            </div>
            <?php elseif ($item['summary']): ?>
            <div class="news-summary"><?= htmlspecialchars(mb_substr($item['summary'], 0, 200)) ?>...</div>
            <?php endif; ?>
        </div>
        <?php endforeach; ?>
        </div>
        <?php endif; ?>
    </div>
</div>

<!-- Pagination -->
<?php if ($total_pages > 1): ?>
<div style="display:flex;gap:.5rem;justify-content:center;margin-bottom:1.5rem;flex-wrap:wrap">
    <?php if ($page > 1): ?>
    <a href="?page=<?= $page-1 ?>&sentiment=<?= urlencode($filter_sentiment) ?>&currency=<?= urlencode($filter_currency) ?>&impact=<?= urlencode($filter_impact) ?>" class="btn btn-outline btn-sm">← Prev</a>
    <?php endif; ?>
    <?php
    $start = max(1, $page - 2);
    $end   = min($total_pages, $page + 2);
    for ($i = $start; $i <= $end; $i++):
    ?>
    <a href="?page=<?= $i ?>&sentiment=<?= urlencode($filter_sentiment) ?>&currency=<?= urlencode($filter_currency) ?>&impact=<?= urlencode($filter_impact) ?>"
       class="btn btn-sm <?= $i === $page ? 'btn-primary' : 'btn-outline' ?>"><?= $i ?></a>
    <?php endfor; ?>
    <?php if ($page < $total_pages): ?>
    <a href="?page=<?= $page+1 ?>&sentiment=<?= urlencode($filter_sentiment) ?>&currency=<?= urlencode($filter_currency) ?>&impact=<?= urlencode($filter_impact) ?>" class="btn btn-outline btn-sm">Next →</a>
    <?php endif; ?>
</div>
<?php endif; ?>

<style>
.news-list { display:flex; flex-direction:column; }
.news-item {
    padding: 1rem 1.25rem;
    border-bottom: 1px solid var(--border);
    transition: background .15s;
}
.news-item:last-child { border-bottom: none; }
.news-item:hover { background: rgba(255,255,255,.02); }
.news-meta {
    display: flex;
    align-items: center;
    gap: .5rem;
    margin-bottom: .4rem;
    flex-wrap: wrap;
}
.news-sentiment { font-size: .8rem; font-weight: 600; }
.news-title { font-size: .9rem; font-weight: 500; line-height: 1.4; margin-bottom: .35rem; }
.news-title a { color: var(--text); }
.news-title a:hover { color: var(--primary); }
.news-ai-summary {
    font-size: .8rem;
    color: var(--text-muted);
    background: rgba(59,130,246,.06);
    border-left: 2px solid var(--primary);
    padding: .4rem .75rem;
    border-radius: 0 4px 4px 0;
    display: flex;
    align-items: center;
    gap: .5rem;
    flex-wrap: wrap;
}
.news-summary { font-size: .8rem; color: var(--text-muted); }
.news-time { font-size: .75rem; color: var(--text-muted); margin-left: auto; white-space: nowrap; }
</style>

<?php require_once __DIR__ . '/../includes/footer.php'; ?>
