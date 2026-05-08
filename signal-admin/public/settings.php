<?php
require_once __DIR__ . '/../includes/config.php';
require_once __DIR__ . '/../includes/db.php';
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/bot_api.php';

require_login();

$message = '';
$error   = '';

// Handle form submission
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!verify_csrf($_POST['_csrf'] ?? '')) {
        $error = 'Invalid request.';
    } else {
        if (!empty($_POST['action']) && $_POST['action'] === 'toggle_mode') {
            $mode_key = $_POST['mode_key'] ?? '';
            $mode_val = ($_POST['enabled'] === 'true') ? 'true' : 'false';
            $allowed_mode_keys = array_map(fn($i) => "mode_{$i}_active", range(1, 21));
            if (in_array($mode_key, $allowed_mode_keys)) {
                set_setting($mode_key, $mode_val);
                bot_post('/api/settings', [$mode_key => $mode_val]);
                header('Content-Type: application/json');
                echo json_encode(['success' => true, 'key' => $mode_key, 'value' => $mode_val]);
                exit;
            }
        } elseif (!empty($_POST['action']) && $_POST['action'] === 'change_password') {
            $current  = $_POST['current_password'] ?? '';
            $new_pass = $_POST['new_password'] ?? '';
            $confirm  = $_POST['confirm_password'] ?? '';

            if ($new_pass !== $confirm) {
                $error = 'New passwords do not match.';
            } elseif (strlen($new_pass) < 6) {
                $error = 'Password must be at least 6 characters.';
            } else {
                $user = db_one('SELECT * FROM admin_users WHERE id = ?', [$_SESSION['user_id']]);
                if (!$user || !password_verify($current, $user['password_hash'])) {
                    $error = 'Current password is incorrect.';
                } else {
                    $hash = password_hash($new_pass, PASSWORD_BCRYPT);
                    db_exec('UPDATE admin_users SET password_hash = ? WHERE id = ?', [$hash, $user['id']]);
                    $message = 'Password changed successfully.';
                }
            }
        } else {
            $mode_keys_all = array_map(fn($i) => "mode_{$i}_active", range(1, 21));
            $boolean_keys = array_merge(['bot_active', 'news_filter_enabled', 'telegram_enabled', 'cooloff_enabled'], $mode_keys_all);

            $allowed_settings = [
                'bot_active', 'trading_mode', 'primary_timeframe', 'higher_timeframe', 'highest_timeframe',
                'max_daily_signals', 'max_open_positions', 'max_daily_loss_pct', 'max_drawdown_pct',
                'trading_start_utc', 'trading_end_utc', 'active_days',
                'min_confluence_score', 'risk_per_trade_pct', 'account_balance',
                'news_filter_enabled', 'news_avoid_minutes',
                'claude_model', 'ai_confidence_threshold',
                'mode_1_active','mode_2_active','mode_3_active','mode_4_active','mode_5_active',
                'mode_6_active','mode_7_active','mode_8_active','mode_9_active','mode_10_active',
                'mode_11_active','mode_12_active','mode_13_active','mode_14_active','mode_15_active',
                'mode_16_active','mode_17_active','mode_18_active','mode_19_active','mode_20_active',
                'mode_21_active',
                'telegram_enabled', 'telegram_bot_token', 'telegram_chat_id', 'daily_summary_time_utc',
                'cooloff_enabled', 'cooloff_losses_trigger', 'cooloff_hours',
            ];

            foreach ($boolean_keys as $bk) {
                if (!isset($_POST[$bk])) $_POST[$bk] = 'false';
            }

            if (isset($_POST['active_days']) && is_array($_POST['active_days'])) {
                $_POST['active_days'] = json_encode(array_map('intval', $_POST['active_days']));
            } elseif (!isset($_POST['active_days'])) {
                $_POST['active_days'] = '[1,2,3,4,5]';
            }

            $updated = 0;
            foreach ($allowed_settings as $key) {
                if (isset($_POST[$key])) {
                    $val = $_POST[$key];
                    if (in_array($key, $boolean_keys)) {
                        $val = $val === 'on' || $val === '1' || $val === 'true' ? 'true' : 'false';
                    }
                    set_setting($key, $val);
                    $updated++;
                }
            }

            bot_post('/api/settings', $_POST);
            $message = "Settings saved ($updated updated).";
        }
    }
}

$settings_rows = db_query("SELECT * FROM settings ORDER BY category, setting_key");
$settings = [];
foreach ($settings_rows as $row) {
    $settings[$row['category']][$row['setting_key']] = $row;
}

$trading_modes_data = [
    ['id'=>1,  'key'=>'mode_1_active',  'emoji'=>'🔵', 'name'=>'Mode 1',  'label'=>'Double_Bottom + RSI',           'tf'=>'M15',      'dir'=>'BUY',  'wr'=>'71.6', 'pf'=>'5.91',   'trades'=>'8,942'],
    ['id'=>2,  'key'=>'mode_2_active',  'emoji'=>'🟠', 'name'=>'Mode 2',  'label'=>'Rising_Wedge + ADX',            'tf'=>'H4',       'dir'=>'SELL', 'wr'=>'74.0', 'pf'=>'18.82',  'trades'=>'959'],
    ['id'=>3,  'key'=>'mode_3_active',  'emoji'=>'🟢', 'name'=>'Mode 3',  'label'=>'Double_Bottom + ADX',           'tf'=>'H4+M15',   'dir'=>'BUY',  'wr'=>'70.4', 'pf'=>'76.99',  'trades'=>'6,554'],
    ['id'=>4,  'key'=>'mode_4_active',  'emoji'=>'🟡', 'name'=>'Mode 4',  'label'=>'Falling_Wedge + EMA_Trend',     'tf'=>'M30',      'dir'=>'BUY',  'wr'=>'76.3', 'pf'=>'110.39', 'trades'=>'520'],
    ['id'=>5,  'key'=>'mode_5_active',  'emoji'=>'🟣', 'name'=>'Mode 5',  'label'=>'Triple_Bottom + Alone',         'tf'=>'M15+H4',   'dir'=>'BUY',  'wr'=>'73.4', 'pf'=>'29.32',  'trades'=>'8,256'],
    ['id'=>6,  'key'=>'mode_6_active',  'emoji'=>'🔴', 'name'=>'Mode 6',  'label'=>'Double_Top + RSI',              'tf'=>'H1',       'dir'=>'SELL', 'wr'=>'73.0', 'pf'=>'4.59',   'trades'=>'111,570'],
    ['id'=>7,  'key'=>'mode_7_active',  'emoji'=>'🔶', 'name'=>'Mode 7',  'label'=>'Ascending_Triangle + ADX',      'tf'=>'H4',       'dir'=>'BUY',  'wr'=>'71.6', 'pf'=>'2.21',   'trades'=>'41,723'],
    ['id'=>8,  'key'=>'mode_8_active',  'emoji'=>'🔷', 'name'=>'Mode 8',  'label'=>'Rounding_Bottom + RSI',         'tf'=>'H4',       'dir'=>'BUY',  'wr'=>'69.3', 'pf'=>'5.19',   'trades'=>'33,688'],
    ['id'=>9,  'key'=>'mode_9_active',  'emoji'=>'🟥', 'name'=>'Mode 9',  'label'=>'Descending_Triangle + ADX',     'tf'=>'M30',      'dir'=>'SELL', 'wr'=>'69.7', 'pf'=>'2.13',   'trades'=>'33,847'],
    ['id'=>10, 'key'=>'mode_10_active', 'emoji'=>'🟦', 'name'=>'Mode 10', 'label'=>'Three_White_Soldiers + EMA',    'tf'=>'H4',       'dir'=>'BUY',  'wr'=>'72.3', 'pf'=>'2.56',   'trades'=>'31,781'],
    ['id'=>11, 'key'=>'mode_11_active', 'emoji'=>'🟧', 'name'=>'Mode 11', 'label'=>'Mat_Hold + ADX',                'tf'=>'H4',       'dir'=>'BUY',  'wr'=>'72.9', 'pf'=>'2.89',   'trades'=>'29,464'],
    ['id'=>12, 'key'=>'mode_12_active', 'emoji'=>'🩶', 'name'=>'Mode 12', 'label'=>'Rickshaw_Man + RSI',            'tf'=>'M30',      'dir'=>'SELL', 'wr'=>'67.4', 'pf'=>'2.47',   'trades'=>'33,191'],
    ['id'=>13, 'key'=>'mode_13_active', 'emoji'=>'🩷', 'name'=>'Mode 13', 'label'=>'Shooting_Star + RSI',           'tf'=>'M30',      'dir'=>'SELL', 'wr'=>'68.3', 'pf'=>'3.62',   'trades'=>'28,890'],
    ['id'=>14, 'key'=>'mode_14_active', 'emoji'=>'🩵', 'name'=>'Mode 14', 'label'=>'Upside_Gap_Three + Alone',      'tf'=>'M15',      'dir'=>'BUY',  'wr'=>'71.2', 'pf'=>'3.25',   'trades'=>'16,499'],
    ['id'=>15, 'key'=>'mode_15_active', 'emoji'=>'🖤', 'name'=>'Mode 15', 'label'=>'Three_Line_Strike_Bear + EMA',  'tf'=>'H1',       'dir'=>'SELL', 'wr'=>'70.2', 'pf'=>'1.82',   'trades'=>'14,124'],
    ['id'=>16, 'key'=>'mode_16_active', 'emoji'=>'🤍', 'name'=>'Mode 16', 'label'=>'Symmetrical_Triangle + EMA',    'tf'=>'H1',       'dir'=>'BUY',  'wr'=>'69.0', 'pf'=>'3.12',   'trades'=>'53,011'],
    ['id'=>17, 'key'=>'mode_17_active', 'emoji'=>'🟫', 'name'=>'Mode 17', 'label'=>'Three_Outside_Down + RSI',      'tf'=>'M30',      'dir'=>'SELL', 'wr'=>'66.9', 'pf'=>'3.38',   'trades'=>'93,859'],
    ['id'=>18, 'key'=>'mode_18_active', 'emoji'=>'💚', 'name'=>'Mode 18', 'label'=>'Bull_Flag + Alone',             'tf'=>'H1',       'dir'=>'BUY',  'wr'=>'62.1', 'pf'=>'1.60',   'trades'=>'2,680'],
    ['id'=>19, 'key'=>'mode_19_active', 'emoji'=>'🧡', 'name'=>'Mode 19', 'label'=>'Belt_Hold_Bull + EMA_Trend',    'tf'=>'D1',       'dir'=>'BUY',  'wr'=>'69.1', 'pf'=>'3.18',   'trades'=>'66,366'],
    ['id'=>20, 'key'=>'mode_20_active', 'emoji'=>'❤️', 'name'=>'Mode 20', 'label'=>'Triple_Top + RSI',              'tf'=>'H1',       'dir'=>'SELL', 'wr'=>'73.0', 'pf'=>'3.20',   'trades'=>'74,391'],
    ['id'=>21, 'key'=>'mode_21_active', 'emoji'=>'💙', 'name'=>'Mode 21', 'label'=>'Tasuki_Gap_Bear + ADX',         'tf'=>'M15',      'dir'=>'SELL', 'wr'=>'69.1', 'pf'=>'2.83',   'trades'=>'52,977'],
];

$modes_api = bot_get('/api/trading-modes');
$mode_counts = [];
if ($modes_api['success'] && !empty($modes_api['data']['modes'])) {
    foreach ($modes_api['data']['modes'] as $m) {
        $mode_counts[$m['id']] = $m['signals_24h'] ?? 0;
    }
}

$active_days_raw = get_setting('active_days', [1,2,3,4,5]);
if (is_string($active_days_raw)) $active_days_raw = json_decode($active_days_raw, true) ?: [1,2,3,4,5];

$page_title = 'Settings';
require_once __DIR__ . '/../includes/header.php';
?>

<style>
/* ── Tab nav ────────────────────────────────────────────── */
.settings-wrap { max-width: 100%; }

.stabs-sticky {
    position: sticky;
    top: 0;
    z-index: 100;
    background: var(--bg, #f9fafb);
    padding: .5rem 0 0;
    margin-bottom: 1.5rem;
    border-bottom: 2px solid var(--border, #e5e7eb);
}
.stabs {
    display: flex;
    gap: .15rem;
    overflow-x: auto;
    scrollbar-width: none;
    padding-bottom: 0;
}
.stabs::-webkit-scrollbar { display: none; }
.stab {
    flex-shrink: 0;
    padding: .55rem 1.1rem;
    font-size: .82rem;
    font-weight: 600;
    border: none;
    background: none;
    color: var(--text-muted, #6b7280);
    cursor: pointer;
    border-bottom: 3px solid transparent;
    margin-bottom: -2px;
    border-radius: 6px 6px 0 0;
    transition: all .15s;
    white-space: nowrap;
}
.stab:hover { color: var(--primary, #6366f1); background: var(--primary-10, #eef2ff); }
.stab.active { color: var(--primary, #6366f1); border-bottom-color: var(--primary, #6366f1); background: var(--card-bg, #fff); }

/* ── Tab panels ─────────────────────────────────────────── */
.tab-panel { display: none; }
.tab-panel.active { display: block; }

/* ── Settings row ───────────────────────────────────────── */
.scard {
    background: var(--card-bg, #fff);
    border: 1px solid var(--border, #e5e7eb);
    border-radius: 12px;
    margin-bottom: 1.25rem;
    overflow: hidden;
}
.scard-head {
    display: flex;
    align-items: center;
    gap: .6rem;
    padding: .85rem 1.25rem;
    background: var(--bg-secondary, #f8fafc);
    border-bottom: 1px solid var(--border, #e5e7eb);
}
.scard-head h3 { margin: 0; font-size: 1rem; font-weight: 700; flex: 1; }
.scard-body { padding: .25rem 0; }

.srow {
    display: grid;
    grid-template-columns: 220px 1fr;
    align-items: center;
    gap: 1rem;
    padding: .75rem 1.25rem;
    border-bottom: 1px solid var(--border-light, #f1f5f9);
    transition: background .1s;
}
.srow:last-child { border-bottom: none; }
.srow:hover { background: var(--bg-secondary, #f8fafc); }
.srow-label {
    font-size: .85rem;
    font-weight: 600;
    color: var(--text, #1f2937);
}

.srow-ctrl {
    display: flex;
    align-items: center;
    gap: .6rem;
    flex-wrap: wrap;
}
.srow-ctrl .form-input,
.srow-ctrl .form-select {
    min-width: 160px;
    max-width: 280px;
    flex: 1;
}
.srow-ctrl .form-input.w-sm { max-width: 120px; }

/* ── Day chips ──────────────────────────────────────────── */
.day-chips { display: flex; gap: .4rem; flex-wrap: wrap; }
.day-chip input { display: none; }
.day-chip span {
    display: inline-block;
    padding: .3rem .75rem;
    border-radius: 20px;
    font-size: .8rem;
    font-weight: 600;
    border: 1.5px solid var(--border, #e5e7eb);
    background: var(--bg-secondary, #f8fafc);
    color: var(--text-muted, #6b7280);
    cursor: pointer;
    transition: all .15s;
    user-select: none;
}
.day-chip input:checked + span {
    background: var(--primary, #6366f1);
    border-color: var(--primary, #6366f1);
    color: #fff;
    box-shadow: 0 2px 6px rgba(99,102,241,.3);
}

/* ── Mode cards ─────────────────────────────────────────── */
.modes-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: .9rem;
    padding: 1rem;
}
.mc {
    border: 1.5px solid var(--border, #e5e7eb);
    border-radius: 10px;
    padding: .9rem 1rem;
    background: var(--card-bg, #fff);
    transition: all .2s;
    position: relative;
}
.mc.mc-on  { border-color: #22c55e; box-shadow: 0 0 0 1px #22c55e1a; }
.mc.mc-off { opacity: .6; }
.mc-head { display: flex; align-items: flex-start; gap: .6rem; }
.mc-emoji { font-size: 1.4rem; line-height: 1; flex-shrink: 0; margin-top: .1rem; }
.mc-info { flex: 1; min-width: 0; }
.mc-title { font-size: .85rem; font-weight: 700; line-height: 1.3; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mc-sub { font-size: .75rem; color: var(--text-muted, #6b7280); display: flex; align-items: center; gap: .4rem; margin-top: .2rem; }
.mc-toggle { flex-shrink: 0; }
.mc-stats {
    display: flex; gap: .4rem; flex-wrap: wrap; margin-top: .6rem;
}
.mc-stat {
    font-size: .72rem;
    background: var(--bg-secondary, #f8fafc);
    color: var(--text-muted, #6b7280);
    padding: .15rem .45rem;
    border-radius: 4px;
    border: 1px solid var(--border-light, #f1f5f9);
}
.mc-stat.wr { background: #dcfce7; color: #16a34a; border-color: #bbf7d0; }
.mc-stat.pf { background: #dbeafe; color: #1d4ed8; border-color: #bfdbfe; }
.mc-footer {
    display: flex; align-items: center; gap: .4rem; margin-top: .55rem;
    font-size: .73rem; color: var(--text-muted, #6b7280);
}
.mc-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.mc-dot.on  { background: #22c55e; box-shadow: 0 0 4px #22c55e; }
.mc-dot.off { background: #94a3b8; }

.badge-buy  { background:#dcfce7;color:#16a34a;padding:.1rem .45rem;border-radius:4px;font-size:.72rem;font-weight:700; }
.badge-sell { background:#fee2e2;color:#dc2626;padding:.1rem .45rem;border-radius:4px;font-size:.72rem;font-weight:700; }

/* ── Modes info bar ─────────────────────────────────────── */
.modes-info {
    margin: 0 1rem 1rem;
    background: var(--bg-secondary, #f8fafc);
    border-left: 3px solid var(--primary, #6366f1);
    padding: .7rem 1rem;
    border-radius: 0 8px 8px 0;
    display: flex; flex-wrap: wrap; gap: .4rem .75rem;
}
.modes-info span { font-size: .78rem; color: var(--text-muted, #6b7280); }
.modes-info strong { color: var(--text, #1f2937); }

/* ── Mode controls bar ──────────────────────────────────── */
.modes-controls {
    display: flex; align-items: center; gap: .75rem; padding: .75rem 1rem;
    border-bottom: 1px solid var(--border, #e5e7eb); flex-wrap: wrap;
}
.modes-controls .btn-sm { font-size: .78rem; padding: .3rem .8rem; }
.modes-count { font-size: .82rem; color: var(--text-muted); margin-left: auto; }

/* ── Sticky save ─────────────────────────────────────────── */
.sticky-save {
    position: sticky;
    bottom: 0;
    z-index: 90;
    background: var(--card-bg, #fff);
    border-top: 1px solid var(--border, #e5e7eb);
    padding: .85rem 1.25rem;
    margin: 0 -1px;
    display: flex;
    align-items: center;
    gap: .75rem;
    box-shadow: 0 -4px 12px rgba(0,0,0,.06);
    border-radius: 0 0 12px 12px;
}
.sticky-save .save-hint { font-size: .78rem; color: var(--text-muted); flex: 1; }

/* ── Alert tweaks ────────────────────────────────────────── */
.s-alert { padding: .7rem 1rem; border-radius: 8px; margin-bottom: 1rem; font-size: .88rem; }
.s-alert.success { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
.s-alert.danger  { background: #fee2e2; color: #b91c1c; border: 1px solid #fecaca; }

/* ── Misc ────────────────────────────────────────────────── */
.btn-reset-field {
    background: none; border: 1px solid var(--border); color: var(--text-muted);
    width: 28px; height: 28px; border-radius: 5px; cursor: pointer;
    font-size: 1rem; display: inline-flex; align-items: center; justify-content: center;
    flex-shrink: 0; transition: all .15s;
}
.btn-reset-field:hover { background: var(--primary); color: #fff; border-color: var(--primary); }
</style>

<div class="settings-wrap">

<?php if ($message): ?>
<div class="s-alert success"><?= htmlspecialchars($message) ?></div>
<?php endif; ?>
<?php if ($error): ?>
<div class="s-alert danger"><?= htmlspecialchars($error) ?></div>
<?php endif; ?>

<!-- ── Tab navigation ────────────────────────────────────── -->
<div class="stabs-sticky">
    <div class="stabs" id="settingsTabs">
        <button class="stab active" onclick="showTab('general',this)">⚙️ General</button>
        <button class="stab" onclick="showTab('limits',this)">🚧 Limits</button>
        <button class="stab" onclick="showTab('risk',this)">⚠️ Risk</button>
        <button class="stab" onclick="showTab('hours',this)">🕐 Hours</button>
        <button class="stab" onclick="showTab('news',this)">📰 News</button>
        <button class="stab" onclick="showTab('modes',this)">🎯 Modes</button>
        <button class="stab" onclick="showTab('ai',this)">🤖 AI</button>
        <button class="stab" onclick="showTab('telegram',this)">📱 Telegram</button>
        <button class="stab" onclick="showTab('security',this)">🔐 Security</button>
    </div>
</div>

<!-- Main settings form -->
<form method="POST" action="/settings.php" id="settingsForm">
<input type="hidden" name="_csrf" value="<?= csrf_token() ?>">

<!-- ══ TAB: General ══════════════════════════════════════════ -->
<div class="tab-panel active" id="tab-general">
<div class="scard">
    <div class="scard-head">
        <span>⚙️</span>
        <h3>General Settings</h3>
    </div>
    <div class="scard-body">

        <div class="srow">
            <div class="srow-label">
                Bot Status
            </div>
            <div class="srow-ctrl">
                <label class="toggle">
                    <input type="checkbox" name="bot_active" data-default="checked"
                           <?= get_setting('bot_active') ? 'checked' : '' ?>>
                    <span class="toggle-slider"></span>
                </label>
            </div>
        </div>

        <div class="srow">
            <div class="srow-label">
                Trading Mode
            </div>
            <div class="srow-ctrl">
                <select name="trading_mode" class="form-select" data-default="hybrid">
                    <?php foreach ([
                        'hybrid'                => 'Hybrid (recommended)',
                        'technical'             => 'Technical Only',
                        'news'                  => 'News Only',
                        'ai'                    => 'AI Enhanced',
                        'technical_news_filter' => 'Technical + News Filter',
                    ] as $val => $label): ?>
                    <option value="<?= $val ?>" <?= get_setting('trading_mode') === $val ? 'selected' : '' ?>><?= $label ?></option>
                    <?php endforeach; ?>
                </select>
                <button type="button" class="btn-reset-field" onclick="resetField(this)" title="Reset">&#8635;</button>
            </div>
        </div>

        <div class="srow">
            <div class="srow-label">
                Primary Timeframe
            </div>
            <div class="srow-ctrl">
                <select name="primary_timeframe" class="form-select" data-default="H1">
                    <?php foreach (['M15'=>'M15','M30'=>'M30','H1'=>'H1 (recommended)','H4'=>'H4'] as $v=>$l): ?>
                    <option value="<?= $v ?>" <?= get_setting('primary_timeframe','H1')===$v?'selected':'' ?>><?= $l ?></option>
                    <?php endforeach; ?>
                </select>
                <button type="button" class="btn-reset-field" onclick="resetField(this)" title="Reset">&#8635;</button>
            </div>
        </div>

        <div class="srow">
            <div class="srow-label">
                Higher Timeframe
            </div>
            <div class="srow-ctrl">
                <select name="higher_timeframe" class="form-select" data-default="H4">
                    <?php foreach (['H1'=>'H1','H4'=>'H4 (recommended)','D1'=>'D1'] as $v=>$l): ?>
                    <option value="<?= $v ?>" <?= get_setting('higher_timeframe','H4')===$v?'selected':'' ?>><?= $l ?></option>
                    <?php endforeach; ?>
                </select>
                <button type="button" class="btn-reset-field" onclick="resetField(this)" title="Reset">&#8635;</button>
            </div>
        </div>

        <div class="srow">
            <div class="srow-label">
                Highest Timeframe
            </div>
            <div class="srow-ctrl">
                <select name="highest_timeframe" class="form-select" data-default="D1">
                    <?php foreach (['H4'=>'H4','D1'=>'D1 (recommended)','W1'=>'W1'] as $v=>$l): ?>
                    <option value="<?= $v ?>" <?= get_setting('highest_timeframe','D1')===$v?'selected':'' ?>><?= $l ?></option>
                    <?php endforeach; ?>
                </select>
                <button type="button" class="btn-reset-field" onclick="resetField(this)" title="Reset">&#8635;</button>
            </div>
        </div>

    </div>
    <div class="sticky-save">
        <button type="submit" class="btn btn-primary">💾 Save Settings</button>
        <span class="save-hint">Changes saved across all tabs at once</span>
    </div>
</div>
</div>

<!-- ══ TAB: Limits ══════════════════════════════════════════ -->
<div class="tab-panel" id="tab-limits">
<div class="scard">
    <div class="scard-head">
        <span>🚧</span>
        <h3>Daily Limits</h3>
    </div>
    <div class="scard-body">
        <?php
        $limit_fields = [
            'max_daily_signals'  => ['Max Signals Per Day',  5,  'number', 'Signals generated per day — recommended 3-7'],
            'max_open_positions' => ['Max Open Positions',   3,  'number', 'Max concurrent open trades'],
            'max_daily_loss_pct' => ['Max Daily Loss %',     3,  'number', 'Bot pauses when daily loss hits this %'],
            'max_drawdown_pct'   => ['Max Drawdown %',       10, 'number', 'Bot pauses when account drawdown hits this %'],
        ];
        foreach ($limit_fields as $key => [$label, $default, $type, $desc]): ?>
        <div class="srow">
            <div class="srow-label"><?= $label ?></div>
            <div class="srow-ctrl">
                <input type="number" name="<?= $key ?>" class="form-input w-sm" data-default="<?= $default ?>"
                       value="<?= htmlspecialchars(get_setting($key, $default)) ?>" min="0" step="0.1">
                <button type="button" class="btn-reset-field" onclick="resetField(this)" title="Reset to <?= $default ?>">&#8635;</button>
            </div>
        </div>
        <?php endforeach; ?>
    </div>
    <div class="sticky-save">
        <button type="submit" class="btn btn-primary">💾 Save Settings</button>
        <span class="save-hint">Changes saved across all tabs at once</span>
    </div>
</div>
</div>

<!-- ══ TAB: Risk ════════════════════════════════════════════ -->
<div class="tab-panel" id="tab-risk">
<div class="scard">
    <div class="scard-head">
        <span>⚠️</span>
        <h3>Risk Management</h3>
    </div>
    <div class="scard-body">

        <div class="srow">
            <div class="srow-label">Account Balance ($)</div>
            <div class="srow-ctrl">
                <input type="number" name="account_balance" class="form-input w-sm" data-default="1000"
                       value="<?= htmlspecialchars(get_setting('account_balance', 1000)) ?>" min="10" step="1">
                <button type="button" class="btn-reset-field" onclick="resetField(this)" title="Reset to $1000">&#8635;</button>
            </div>
        </div>

        <div class="srow">
            <div class="srow-label">Risk Per Trade (%)</div>
            <div class="srow-ctrl">
                <input type="number" name="risk_per_trade_pct" class="form-input w-sm" data-default="2"
                       value="<?= htmlspecialchars(get_setting('risk_per_trade_pct', 2.0)) ?>" min="0.1" max="10" step="0.1">
                <button type="button" class="btn-reset-field" onclick="resetField(this)" title="Reset to 2%">&#8635;</button>
            </div>
        </div>

        <div class="srow">
            <div class="srow-label">Min Confluence Score</div>
            <div class="srow-ctrl">
                <input type="number" name="min_confluence_score" class="form-input w-sm" data-default="80"
                       value="<?= htmlspecialchars(get_setting('min_confluence_score', 80)) ?>" min="50" max="100" step="1">
                <button type="button" class="btn-reset-field" onclick="resetField(this)" title="Reset to 80">&#8635;</button>
            </div>
        </div>

        <div class="srow">
            <div class="srow-label">Cool-Off Mode</div>
            <div class="srow-ctrl">
                <label class="toggle">
                    <input type="checkbox" name="cooloff_enabled" data-default="checked"
                           <?= get_setting('cooloff_enabled') ? 'checked' : '' ?>>
                    <span class="toggle-slider"></span>
                </label>
            </div>
        </div>

        <div class="srow">
            <div class="srow-label">Cool-Off Trigger</div>
            <div class="srow-ctrl">
                <input type="number" name="cooloff_losses_trigger" class="form-input w-sm" data-default="3"
                       value="<?= htmlspecialchars(get_setting('cooloff_losses_trigger', 3)) ?>" min="1" max="10" step="1">
                <button type="button" class="btn-reset-field" onclick="resetField(this)" title="Reset to 3">&#8635;</button>
            </div>
        </div>

        <div class="srow">
            <div class="srow-label">Cool-Off Duration (hours)</div>
            <div class="srow-ctrl">
                <input type="number" name="cooloff_hours" class="form-input w-sm" data-default="2"
                       value="<?= htmlspecialchars(get_setting('cooloff_hours', 2)) ?>" min="0.5" max="48" step="0.5">
                <button type="button" class="btn-reset-field" onclick="resetField(this)" title="Reset to 2h">&#8635;</button>
            </div>
        </div>

    </div>
    <div class="sticky-save">
        <button type="submit" class="btn btn-primary">💾 Save Settings</button>
        <span class="save-hint">Changes saved across all tabs at once</span>
    </div>
</div>
</div>

<!-- ══ TAB: Hours ════════════════════════════════════════════ -->
<div class="tab-panel" id="tab-hours">
<div class="scard">
    <div class="scard-head">
        <span>🕐</span>
        <h3>Trading Hours (UTC)</h3>
    </div>
    <div class="scard-body">

        <div class="srow">
            <div class="srow-label">Start Time (UTC)</div>
            <div class="srow-ctrl">
                <input type="time" name="trading_start_utc" class="form-input" data-default="08:00"
                       value="<?= htmlspecialchars(get_setting('trading_start_utc', '08:00')) ?>">
                <button type="button" class="btn-reset-field" onclick="resetField(this)" title="Reset to 08:00">&#8635;</button>
            </div>
        </div>

        <div class="srow">
            <div class="srow-label">End Time (UTC)</div>
            <div class="srow-ctrl">
                <input type="time" name="trading_end_utc" class="form-input" data-default="22:00"
                       value="<?= htmlspecialchars(get_setting('trading_end_utc', '22:00')) ?>">
                <button type="button" class="btn-reset-field" onclick="resetField(this)" title="Reset to 22:00">&#8635;</button>
            </div>
        </div>

        <div class="srow" style="align-items:flex-start;padding-top:1rem;padding-bottom:1rem">
            <div class="srow-label">Active Trading Days</div>
            <div class="srow-ctrl">
                <div class="day-chips">
                    <?php
                    $day_names = [1=>'Mon', 2=>'Tue', 3=>'Wed', 4=>'Thu', 5=>'Fri', 6=>'Sat', 7=>'Sun'];
                    foreach ($day_names as $num => $name): ?>
                    <label class="day-chip">
                        <input type="checkbox" name="active_days[]" value="<?= $num ?>"
                               <?= in_array($num, $active_days_raw) ? 'checked' : '' ?>>
                        <span><?= $name ?></span>
                    </label>
                    <?php endforeach; ?>
                </div>
                <button type="button" class="btn-reset-field" onclick="resetDays()" title="Reset to Mon-Fri">&#8635;</button>
            </div>
        </div>

    </div>
    <div class="sticky-save">
        <button type="submit" class="btn btn-primary">💾 Save Settings</button>
        <span class="save-hint">Changes saved across all tabs at once</span>
    </div>
</div>
</div>

<!-- ══ TAB: News ═════════════════════════════════════════════ -->
<div class="tab-panel" id="tab-news">
<div class="scard">
    <div class="scard-head">
        <span>📰</span>
        <h3>News Filter</h3>
    </div>
    <div class="scard-body">

        <div class="srow">
            <div class="srow-label">Enable News Filter</div>
            <div class="srow-ctrl">
                <label class="toggle">
                    <input type="checkbox" name="news_filter_enabled" data-default="checked"
                           <?= get_setting('news_filter_enabled') ? 'checked' : '' ?>>
                    <span class="toggle-slider"></span>
                </label>
            </div>
        </div>

        <div class="srow">
            <div class="srow-label">Avoid Window (minutes)</div>
            <div class="srow-ctrl">
                <input type="number" name="news_avoid_minutes" class="form-input w-sm" data-default="30"
                       value="<?= htmlspecialchars(get_setting('news_avoid_minutes', 30)) ?>" min="5" max="120" step="5">
                <button type="button" class="btn-reset-field" onclick="resetField(this)" title="Reset to 30 min">&#8635;</button>
            </div>
        </div>

    </div>
    <div class="sticky-save">
        <button type="submit" class="btn btn-primary">💾 Save Settings</button>
        <span class="save-hint">Changes saved across all tabs at once</span>
    </div>
</div>
</div>

<!-- ══ TAB: Modes ════════════════════════════════════════════ -->
<div class="tab-panel" id="tab-modes">
<div class="scard">
    <div class="scard-head">
        <span>🎯</span>
        <h3>Trading Modes (Pattern Engine)</h3>
        <span style="margin-left:auto;font-size:.78rem;background:var(--primary,#6366f1);color:#fff;padding:.2rem .7rem;border-radius:20px;">
            21 Modes · 576,180 backtests
        </span>
    </div>

    <div class="modes-controls">
        <button type="button" class="btn btn-sm btn-outline" onclick="toggleAllModes(true)">✅ Enable All</button>
        <button type="button" class="btn btn-sm btn-outline" onclick="toggleAllModes(false)">❌ Disable All</button>
        <span class="modes-count" id="modesCountLabel"><?= count(array_filter($trading_modes_data, fn($m) => get_setting($m['key'],'true') !== 'false')) ?> / 21 active</span>
    </div>

    <div class="modes-grid">
    <?php foreach ($trading_modes_data as $mode):
        $is_active = get_setting($mode['key'], 'true') !== 'false';
        $count_24h = $mode_counts[$mode['id']] ?? 0;
    ?>
    <div class="mc <?= $is_active ? 'mc-on' : 'mc-off' ?>" id="mc-<?= $mode['id'] ?>">
        <div class="mc-head">
            <span class="mc-emoji"><?= $mode['emoji'] ?></span>
            <div class="mc-info">
                <div class="mc-title"><?= $mode['name'] ?>: <?= htmlspecialchars($mode['label']) ?></div>
                <div class="mc-sub">
                    <span><?= htmlspecialchars($mode['tf']) ?></span>
                    <?= $mode['dir']==='BUY' ? '<span class="badge-buy">BUY</span>' : '<span class="badge-sell">SELL</span>' ?>
                    <?php if($count_24h > 0): ?>
                    <span style="color:var(--primary,#6366f1)">📤 <?= $count_24h ?>h</span>
                    <?php endif; ?>
                </div>
            </div>
            <label class="toggle mc-toggle">
                <input type="checkbox" class="mode-cb"
                       data-key="<?= $mode['key'] ?>"
                       data-mode-id="<?= $mode['id'] ?>"
                       <?= $is_active ? 'checked' : '' ?>>
                <span class="toggle-slider"></span>
            </label>
        </div>
        <div class="mc-stats">
            <span class="mc-stat wr">WR <?= $mode['wr'] ?>%</span>
            <span class="mc-stat pf">PF <?= $mode['pf'] ?></span>
            <span class="mc-stat"><?= $mode['trades'] ?> trades</span>
        </div>
        <div class="mc-footer">
            <span class="mc-dot <?= $is_active ? 'on' : 'off' ?>" id="mc-dot-<?= $mode['id'] ?>"></span>
            <span id="mc-status-<?= $mode['id'] ?>"><?= $is_active ? 'Running — checks every 60 sec' : 'Disabled' ?></span>
        </div>
    </div>
    <?php endforeach; ?>
    </div>

    <div class="modes-info">
        <span>⏱ <strong>Cooldown:</strong> M15=1h | M30=90min | H4=8h</span>
        <span>📅 <strong>News Gate:</strong> High-impact events blocked ±30 min</span>
        <span>📐 <strong>SL/TP:</strong> ATR×2.0 (SL) | ATR×1.0 (TP)</span>
    </div>
</div>
</div>

<!-- ══ TAB: AI ═══════════════════════════════════════════════ -->
<div class="tab-panel" id="tab-ai">
<div class="scard">
    <div class="scard-head"><span>🤖</span><h3>AI Settings</h3></div>
    <div class="scard-body">

        <div class="srow">
            <div class="srow-label">Claude Model</div>
            <div class="srow-ctrl">
                <select name="claude_model" class="form-select" data-default="claude-haiku-4-5-20251001">
                    <?php foreach ([
                        'claude-haiku-4-5-20251001' => 'Haiku 4.5 (cheapest)',
                        'claude-sonnet-4-6'          => 'Sonnet 4.6 (balanced)',
                        'claude-opus-4-6'            => 'Opus 4.6 (most accurate)',
                    ] as $m => $l): ?>
                    <option value="<?= $m ?>" <?= get_setting('claude_model')===$m?'selected':'' ?>><?= $l ?></option>
                    <?php endforeach; ?>
                </select>
                <button type="button" class="btn-reset-field" onclick="resetField(this)" title="Reset">&#8635;</button>
            </div>
        </div>

        <div class="srow">
            <div class="srow-label">AI Confidence Threshold (%)</div>
            <div class="srow-ctrl">
                <input type="number" name="ai_confidence_threshold" class="form-input w-sm" data-default="70"
                       value="<?= htmlspecialchars(get_setting('ai_confidence_threshold', 70)) ?>" min="50" max="95" step="5">
                <button type="button" class="btn-reset-field" onclick="resetField(this)" title="Reset to 70%">&#8635;</button>
            </div>
        </div>

    </div>
    <div class="sticky-save">
        <button type="submit" class="btn btn-primary">💾 Save Settings</button>
        <span class="save-hint">Changes saved across all tabs at once</span>
    </div>
</div>
</div>

<!-- ══ TAB: Telegram ═════════════════════════════════════════ -->
<div class="tab-panel" id="tab-telegram">
<div class="scard">
    <div class="scard-head"><span>📱</span><h3>Telegram Settings</h3></div>
    <div class="scard-body">

        <div class="srow">
            <div class="srow-label">Enable Telegram</div>
            <div class="srow-ctrl">
                <label class="toggle">
                    <input type="checkbox" name="telegram_enabled" data-default="checked"
                           <?= get_setting('telegram_enabled') ? 'checked' : '' ?>>
                    <span class="toggle-slider"></span>
                </label>
            </div>
        </div>

        <div class="srow">
            <div class="srow-label">Bot Token</div>
            <div class="srow-ctrl">
                <input type="password" name="telegram_bot_token" class="form-input"
                       value="<?= htmlspecialchars(get_setting('telegram_bot_token', '')) ?>"
                       autocomplete="off" placeholder="123456:ABC-DEF...">
            </div>
        </div>

        <div class="srow">
            <div class="srow-label">Chat ID</div>
            <div class="srow-ctrl">
                <input type="text" name="telegram_chat_id" class="form-input"
                       value="<?= htmlspecialchars(get_setting('telegram_chat_id', '')) ?>"
                       placeholder="-100...">
            </div>
        </div>

        <div class="srow">
            <div class="srow-label">Daily Summary Time (UTC)</div>
            <div class="srow-ctrl">
                <input type="time" name="daily_summary_time_utc" class="form-input" data-default="23:00"
                       value="<?= htmlspecialchars(get_setting('daily_summary_time_utc', '23:00')) ?>">
                <button type="button" class="btn-reset-field" onclick="resetField(this)" title="Reset to 23:00">&#8635;</button>
            </div>
        </div>

    </div>
    <div class="sticky-save">
        <button type="submit" class="btn btn-primary">💾 Save Settings</button>
        <span class="save-hint">Changes saved across all tabs at once</span>
    </div>
</div>
</div>

<!-- ══ TAB: Security ═════════════════════════════════════════ -->
<div class="tab-panel" id="tab-security">
</form><!-- close main form before password form -->

<div class="scard">
    <div class="scard-head"><span>🔐</span><h3>Change Password</h3></div>
    <div class="scard-body">
        <form method="POST" action="/settings.php">
            <input type="hidden" name="_csrf" value="<?= csrf_token() ?>">
            <input type="hidden" name="action" value="change_password">

            <div class="srow">
                <div class="srow-label">Current Password</div>
                <div class="srow-ctrl">
                    <input type="password" name="current_password" class="form-input" required autocomplete="current-password">
                </div>
            </div>
            <div class="srow">
                <div class="srow-label">New Password</div>
                <div class="srow-ctrl">
                    <input type="password" name="new_password" class="form-input" required minlength="6" autocomplete="new-password">
                </div>
            </div>
            <div class="srow">
                <div class="srow-label">Confirm New Password</div>
                <div class="srow-ctrl">
                    <input type="password" name="confirm_password" class="form-input" required minlength="6" autocomplete="new-password">
                </div>
            </div>
            <div class="sticky-save">
                <button type="submit" class="btn btn-secondary">🔐 Change Password</button>
                <span class="save-hint">Enter current password to confirm change</span>
            </div>
        </form>
    </div>
</div>

</div><!-- end tab-security -->

<script>
// ── Tab switching ────────────────────────────────────────────
function showTab(name, btn) {
    document.querySelectorAll('.tab-panel').forEach(function(p) { p.classList.remove('active'); });
    document.querySelectorAll('.stab').forEach(function(b) { b.classList.remove('active'); });
    var panel = document.getElementById('tab-' + name);
    if (panel) panel.classList.add('active');
    if (btn) btn.classList.add('active');
    // Save active tab in sessionStorage so refresh stays on same tab
    try { sessionStorage.setItem('settings_tab', name); } catch(e) {}
}

// Restore tab on load
(function() {
    try {
        var saved = sessionStorage.getItem('settings_tab');
        if (saved) {
            var btn = Array.from(document.querySelectorAll('.stab')).find(function(b) {
                return b.getAttribute('onclick') && b.getAttribute('onclick').includes("'" + saved + "'");
            });
            if (btn) showTab(saved, btn);
        }
    } catch(e) {}
})();

// ── Reset helpers ────────────────────────────────────────────
function resetField(btn) {
    var ctrl = btn.closest('.srow-ctrl') || btn.closest('.setting-control');
    if (!ctrl) return;
    var input = ctrl.querySelector('[data-default]');
    if (!input) return;
    var def = input.getAttribute('data-default');
    if (input.type === 'checkbox') input.checked = (def === 'checked');
    else input.value = def;
    input.style.outline = '2px solid var(--warning, #f59e0b)';
    setTimeout(function() { input.style.outline = ''; }, 700);
}

function resetDays() {
    var defaults = [1,2,3,4,5];
    document.querySelectorAll('.day-chip input[type=checkbox]').forEach(function(cb) {
        cb.checked = defaults.includes(parseInt(cb.value));
    });
}

// ── Mode toggle — AJAX ───────────────────────────────────────
function updateModeCount() {
    var active = document.querySelectorAll('.mode-cb:checked').length;
    var label = document.getElementById('modesCountLabel');
    if (label) label.textContent = active + ' / 21 active';
}

function toggleAllModes(enable) {
    document.querySelectorAll('.mode-cb').forEach(function(cb) {
        if (cb.checked !== enable) {
            cb.checked = enable;
            cb.dispatchEvent(new Event('change'));
        }
    });
}

document.querySelectorAll('.mode-cb').forEach(function(cb) {
    cb.addEventListener('change', function() {
        var key    = this.dataset.key;
        var modeId = this.dataset.modeId;
        var enabled = this.checked;
        var card   = document.getElementById('mc-' + modeId);
        var dot    = document.getElementById('mc-dot-' + modeId);
        var status = document.getElementById('mc-status-' + modeId);

        // Optimistic UI
        if (enabled) {
            card.classList.remove('mc-off'); card.classList.add('mc-on');
            if (dot) { dot.classList.remove('off'); dot.classList.add('on'); }
            if (status) status.textContent = 'Saving…';
        } else {
            card.classList.remove('mc-on'); card.classList.add('mc-off');
            if (dot) { dot.classList.remove('on'); dot.classList.add('off'); }
            if (status) status.textContent = 'Saving…';
        }
        updateModeCount();

        // AJAX save
        var fd = new FormData();
        fd.append('_csrf', '<?= csrf_token() ?>');
        fd.append('action', 'toggle_mode');
        fd.append('mode_key', key);
        fd.append('enabled', enabled ? 'true' : 'false');

        fetch('/settings.php', { method: 'POST', body: fd })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (status) {
                    status.textContent = data.success
                        ? (enabled ? 'Running — checks every 60 sec' : 'Disabled')
                        : '❌ Save failed — refresh and retry';
                }
            })
            .catch(function() {
                if (status) status.textContent = '❌ Network error';
            });
    });
});
</script>

</div><!-- .settings-wrap -->

<?php require_once __DIR__ . '/../includes/footer.php'; ?>
