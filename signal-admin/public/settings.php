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
        // Handle password change separately
        if (!empty($_POST['action']) && $_POST['action'] === 'change_password') {
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
            // Normal settings save
            $boolean_keys = ['bot_active', 'news_filter_enabled', 'telegram_enabled', 'cooloff_enabled'];

            $allowed_settings = [
                'bot_active', 'trading_mode', 'primary_timeframe', 'higher_timeframe', 'highest_timeframe',
                'max_daily_signals', 'max_open_positions', 'max_daily_loss_pct', 'max_drawdown_pct',
                'trading_start_utc', 'trading_end_utc', 'active_days',
                'min_confluence_score', 'risk_per_trade_pct', 'account_balance',
                'news_filter_enabled', 'news_avoid_minutes',
                'claude_model', 'ai_confidence_threshold',
                'telegram_enabled', 'telegram_bot_token', 'telegram_chat_id', 'daily_summary_time_utc',
                'cooloff_enabled', 'cooloff_losses_trigger', 'cooloff_hours',
            ];

            // Handle unchecked checkboxes (not sent in POST)
            foreach ($boolean_keys as $bk) {
                if (!isset($_POST[$bk])) {
                    $_POST[$bk] = 'false';
                }
            }

            // Handle active_days checkboxes -> JSON array
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

// Load all settings grouped by category
$settings_rows = db_query("SELECT * FROM settings ORDER BY category, setting_key");
$settings = [];
foreach ($settings_rows as $row) {
    $settings[$row['category']][$row['setting_key']] = $row;
}

$page_title = 'Settings';
require_once __DIR__ . '/../includes/header.php';
?>

<?php if ($message): ?>
<div class="alert alert-success"><?= htmlspecialchars($message) ?></div>
<?php endif; ?>
<?php if ($error): ?>
<div class="alert alert-danger"><?= htmlspecialchars($error) ?></div>
<?php endif; ?>

<form method="POST" action="/settings.php">
<input type="hidden" name="_csrf" value="<?= csrf_token() ?>">

<!-- ── General ──────────────────────────────────────────────────────────── -->
<div class="card">
    <div class="card-header">
        <h2>⚙️ General</h2>
        <button type="button" class="btn btn-outline btn-sm btn-reset-section" onclick="resetSection(this)">Reset Section</button>
    </div>
    <div class="card-body settings-grid">

        <div class="setting-row">
            <label>Bot Status</label>
            <div class="setting-control">
                <label class="toggle">
                    <input type="checkbox" name="bot_active" data-default="checked"
                           <?= get_setting('bot_active') ? 'checked' : '' ?>>
                    <span class="toggle-slider"></span>
                </label>
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default">&#8635;</button>
                <span class="setting-desc">Master on/off switch</span>
            </div>
        </div>

        <div class="setting-row">
            <label>Trading Mode</label>
            <div class="setting-control">
                <select name="trading_mode" class="form-select" data-default="hybrid">
                    <?php
                    $modes = [
                        'technical'             => 'Technical',
                        'news'                  => 'News',
                        'hybrid'                => 'Hybrid',
                        'ai'                    => 'AI',
                        'technical_news_filter' => 'Technical + News Filter',
                    ];
                    foreach ($modes as $val => $label): ?>
                    <option value="<?= $val ?>" <?= get_setting('trading_mode') === $val ? 'selected' : '' ?>>
                        <?= $label ?>
                    </option>
                    <?php endforeach; ?>
                </select>
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default">&#8635;</button>
                <span class="setting-desc">Technical | News | Hybrid | AI | Technical + News Filter</span>
            </div>
        </div>

        <div class="setting-row">
            <label>Primary Timeframe</label>
            <div class="setting-control">
                <select name="primary_timeframe" class="form-select" data-default="H1">
                    <?php foreach (['M15'=>'M15','M30'=>'M30','H1'=>'H1','H4'=>'H4'] as $v => $l): ?>
                    <option value="<?= $v ?>" <?= get_setting('primary_timeframe', 'H1') === $v ? 'selected' : '' ?>><?= $l ?></option>
                    <?php endforeach; ?>
                </select>
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default">&#8635;</button>
                <span class="setting-desc">Primary analysis timeframe (recommended: H1)</span>
            </div>
        </div>

        <div class="setting-row">
            <label>Higher Timeframe</label>
            <div class="setting-control">
                <select name="higher_timeframe" class="form-select" data-default="H4">
                    <?php foreach (['H1'=>'H1','H4'=>'H4','D1'=>'D1'] as $v => $l): ?>
                    <option value="<?= $v ?>" <?= get_setting('higher_timeframe', 'H4') === $v ? 'selected' : '' ?>><?= $l ?></option>
                    <?php endforeach; ?>
                </select>
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default">&#8635;</button>
                <span class="setting-desc">Multi-timeframe confirmation (recommended: H4)</span>
            </div>
        </div>

        <div class="setting-row">
            <label>Highest Timeframe</label>
            <div class="setting-control">
                <select name="highest_timeframe" class="form-select" data-default="D1">
                    <?php foreach (['H4'=>'H4','D1'=>'D1','W1'=>'W1'] as $v => $l): ?>
                    <option value="<?= $v ?>" <?= get_setting('highest_timeframe', 'D1') === $v ? 'selected' : '' ?>><?= $l ?></option>
                    <?php endforeach; ?>
                </select>
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default">&#8635;</button>
                <span class="setting-desc">Trend direction confirmation (recommended: D1)</span>
            </div>
        </div>

        <div class="setting-row">
            <label>Timezone</label>
            <div class="setting-control">
                <input type="text" name="timezone" class="form-input" data-default="Asia/Dhaka"
                       value="<?= htmlspecialchars(get_setting('timezone', 'Asia/Dhaka')) ?>">
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default">&#8635;</button>
            </div>
        </div>
    </div>
</div>

<!-- ── Limits ────────────────────────────────────────────────────────────── -->
<div class="card">
    <div class="card-header">
        <h2>🚧 Daily Limits</h2>
        <button type="button" class="btn btn-outline btn-sm btn-reset-section" onclick="resetSection(this)">Reset Section</button>
    </div>
    <div class="card-body settings-grid">
        <?php
        $limit_fields = [
            'max_daily_signals'  => ['Max Signals Per Day',  5,  'Maximum number of signals per day (recommended: 3-7)'],
            'max_open_positions' => ['Max Open Positions',   3,  'Maximum concurrent open signals'],
            'max_daily_loss_pct' => ['Max Daily Loss %',     3,  'Auto-stop when daily loss exceeds this %'],
            'max_drawdown_pct'   => ['Max Drawdown %',       10, 'Auto-stop when account drawdown exceeds this %'],
        ];
        foreach ($limit_fields as $key => [$label, $default, $desc]):
        ?>
        <div class="setting-row">
            <label><?= $label ?></label>
            <div class="setting-control">
                <input type="number" name="<?= $key ?>" class="form-input w-100" data-default="<?= $default ?>"
                       value="<?= htmlspecialchars(get_setting($key, $default)) ?>"
                       min="0" step="0.1">
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default (<?= $default ?>)">&#8635;</button>
                <span class="setting-desc"><?= $desc ?></span>
            </div>
        </div>
        <?php endforeach; ?>
    </div>
</div>

<!-- ── Risk ──────────────────────────────────────────────────────────────── -->
<div class="card">
    <div class="card-header">
        <h2>⚠️ Risk Management</h2>
        <button type="button" class="btn btn-outline btn-sm btn-reset-section" onclick="resetSection(this)">Reset Section</button>
    </div>
    <div class="card-body settings-grid">

        <div class="setting-row">
            <label>Account Balance ($)</label>
            <div class="setting-control">
                <input type="number" name="account_balance" class="form-input w-100" data-default="1000"
                       value="<?= htmlspecialchars(get_setting('account_balance', 1000)) ?>"
                       min="10" step="1">
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default ($1000)">&#8635;</button>
            </div>
        </div>

        <div class="setting-row">
            <label>Risk Per Trade (%)</label>
            <div class="setting-control">
                <input type="number" name="risk_per_trade_pct" class="form-input w-100" data-default="2"
                       value="<?= htmlspecialchars(get_setting('risk_per_trade_pct', 2.0)) ?>"
                       min="0.1" max="10" step="0.1">
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default (2%)">&#8635;</button>
                <span class="setting-desc">% of account balance to risk per trade (recommended: 1-2%)</span>
            </div>
        </div>

        <div class="setting-row">
            <label>Min Confluence Score</label>
            <div class="setting-control">
                <input type="number" name="min_confluence_score" class="form-input w-100" data-default="80"
                       value="<?= htmlspecialchars(get_setting('min_confluence_score', 80)) ?>"
                       min="50" max="100" step="1">
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default (80)">&#8635;</button>
                <span class="setting-desc">Minimum score (0-100) to generate a signal. Higher = fewer but better signals.</span>
            </div>
        </div>

        <div class="setting-row">
            <label>Cool-Off</label>
            <div class="setting-control">
                <label class="toggle">
                    <input type="checkbox" name="cooloff_enabled" data-default="checked"
                           <?= get_setting('cooloff_enabled') ? 'checked' : '' ?>>
                    <span class="toggle-slider"></span>
                </label>
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default">&#8635;</button>
                <span class="setting-desc">Pause bot after consecutive losses</span>
            </div>
        </div>

        <div class="setting-row">
            <label>Cool-Off Trigger (losses)</label>
            <div class="setting-control">
                <input type="number" name="cooloff_losses_trigger" class="form-input w-100" data-default="3"
                       value="<?= htmlspecialchars(get_setting('cooloff_losses_trigger', 3)) ?>"
                       min="1" max="10" step="1">
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default (3)">&#8635;</button>
            </div>
        </div>

        <div class="setting-row">
            <label>Cool-Off Duration (hours)</label>
            <div class="setting-control">
                <input type="number" name="cooloff_hours" class="form-input w-100" data-default="2"
                       value="<?= htmlspecialchars(get_setting('cooloff_hours', 2)) ?>"
                       min="0.5" max="48" step="0.5">
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default (2h)">&#8635;</button>
            </div>
        </div>
    </div>
</div>

<!-- ── Trading Hours ─────────────────────────────────────────────────────── -->
<div class="card">
    <div class="card-header">
        <h2>🕐 Trading Hours (UTC)</h2>
        <button type="button" class="btn btn-outline btn-sm btn-reset-section" onclick="resetSection(this)">Reset Section</button>
    </div>
    <div class="card-body settings-grid">
        <div class="setting-row">
            <label>Start Time (UTC)</label>
            <div class="setting-control">
                <input type="time" name="trading_start_utc" class="form-input" data-default="08:00"
                       value="<?= htmlspecialchars(get_setting('trading_start_utc', '08:00')) ?>">
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default (08:00)">&#8635;</button>
            </div>
        </div>
        <div class="setting-row">
            <label>End Time (UTC)</label>
            <div class="setting-control">
                <input type="time" name="trading_end_utc" class="form-input" data-default="22:00"
                       value="<?= htmlspecialchars(get_setting('trading_end_utc', '22:00')) ?>">
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default (22:00)">&#8635;</button>
            </div>
        </div>

        <div class="setting-row">
            <label>Active Trading Days</label>
            <div class="setting-control">
                <?php
                $active_days = get_setting('active_days', [1,2,3,4,5]);
                if (is_string($active_days)) $active_days = json_decode($active_days, true) ?: [1,2,3,4,5];
                $day_names = [1=>'Mon', 2=>'Tue', 3=>'Wed', 4=>'Thu', 5=>'Fri', 6=>'Sat', 7=>'Sun'];
                ?>
                <div class="days-group" data-default="1,2,3,4,5" style="display:flex;gap:.75rem;flex-wrap:wrap">
                    <?php foreach ($day_names as $num => $name): ?>
                    <label style="display:flex;align-items:center;gap:.3rem;cursor:pointer;font-size:.85rem">
                        <input type="checkbox" name="active_days[]" value="<?= $num ?>"
                               <?= in_array($num, $active_days) ? 'checked' : '' ?>>
                        <?= $name ?>
                    </label>
                    <?php endforeach; ?>
                </div>
                <button type="button" class="btn-reset" onclick="resetDays()" title="Reset to Mon-Fri">&#8635;</button>
                <span class="setting-desc">Days the bot is allowed to trade (Forex: Mon-Fri)</span>
            </div>
        </div>
    </div>
</div>

<!-- ── News Filter ───────────────────────────────────────────────────────── -->
<div class="card">
    <div class="card-header">
        <h2>📰 News Filter</h2>
        <button type="button" class="btn btn-outline btn-sm btn-reset-section" onclick="resetSection(this)">Reset Section</button>
    </div>
    <div class="card-body settings-grid">
        <div class="setting-row">
            <label>News Filter</label>
            <div class="setting-control">
                <label class="toggle">
                    <input type="checkbox" name="news_filter_enabled" data-default="checked"
                           <?= get_setting('news_filter_enabled') ? 'checked' : '' ?>>
                    <span class="toggle-slider"></span>
                </label>
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default">&#8635;</button>
                <span class="setting-desc">Pause trading before high-impact news events</span>
            </div>
        </div>
        <div class="setting-row">
            <label>Avoid Minutes</label>
            <div class="setting-control">
                <input type="number" name="news_avoid_minutes" class="form-input w-100" data-default="30"
                       value="<?= htmlspecialchars(get_setting('news_avoid_minutes', 30)) ?>"
                       min="5" max="120" step="5">
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default (30)">&#8635;</button>
                <span class="setting-desc">Minutes to pause before and after high-impact news</span>
            </div>
        </div>
    </div>
</div>

<!-- ── AI ────────────────────────────────────────────────────────────────── -->
<div class="card">
    <div class="card-header">
        <h2>🤖 AI Settings</h2>
        <button type="button" class="btn btn-outline btn-sm btn-reset-section" onclick="resetSection(this)">Reset Section</button>
    </div>
    <div class="card-body settings-grid">
        <div class="setting-row">
            <label>Claude Model</label>
            <div class="setting-control">
                <select name="claude_model" class="form-select" data-default="claude-haiku-4-5-20251001">
                    <?php foreach (['claude-haiku-4-5-20251001', 'claude-sonnet-4-6', 'claude-opus-4-6'] as $m): ?>
                    <option value="<?= $m ?>" <?= get_setting('claude_model') === $m ? 'selected' : '' ?>>
                        <?= $m ?>
                    </option>
                    <?php endforeach; ?>
                </select>
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default">&#8635;</button>
                <span class="setting-desc">Haiku is cheapest; Opus is most accurate</span>
            </div>
        </div>
        <div class="setting-row">
            <label>AI Confidence Threshold (%)</label>
            <div class="setting-control">
                <input type="number" name="ai_confidence_threshold" class="form-input w-100" data-default="70"
                       value="<?= htmlspecialchars(get_setting('ai_confidence_threshold', 70)) ?>"
                       min="50" max="95" step="5">
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default (70%)">&#8635;</button>
                <span class="setting-desc">Minimum AI confidence to use the AI sentiment signal</span>
            </div>
        </div>
    </div>
</div>

<!-- ── Telegram ──────────────────────────────────────────────────────────── -->
<div class="card">
    <div class="card-header">
        <h2>📱 Telegram</h2>
        <button type="button" class="btn btn-outline btn-sm btn-reset-section" onclick="resetSection(this)">Reset Section</button>
    </div>
    <div class="card-body settings-grid">
        <div class="setting-row">
            <label>Enable Telegram</label>
            <div class="setting-control">
                <label class="toggle">
                    <input type="checkbox" name="telegram_enabled" data-default="checked"
                           <?= get_setting('telegram_enabled') ? 'checked' : '' ?>>
                    <span class="toggle-slider"></span>
                </label>
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default">&#8635;</button>
            </div>
        </div>
        <div class="setting-row">
            <label>Bot Token</label>
            <div class="setting-control">
                <input type="password" name="telegram_bot_token" class="form-input"
                       value="<?= htmlspecialchars(get_setting('telegram_bot_token', '')) ?>"
                       autocomplete="off">
            </div>
        </div>
        <div class="setting-row">
            <label>Chat ID</label>
            <div class="setting-control">
                <input type="text" name="telegram_chat_id" class="form-input"
                       value="<?= htmlspecialchars(get_setting('telegram_chat_id', '')) ?>">
            </div>
        </div>
        <div class="setting-row">
            <label>Daily Summary Time (UTC)</label>
            <div class="setting-control">
                <input type="time" name="daily_summary_time_utc" class="form-input" data-default="23:00"
                       value="<?= htmlspecialchars(get_setting('daily_summary_time_utc', '23:00')) ?>">
                <button type="button" class="btn-reset" onclick="resetField(this)" title="Reset to default (23:00)">&#8635;</button>
            </div>
        </div>
    </div>
</div>

<div class="form-actions">
    <button type="submit" class="btn btn-primary btn-lg">💾 Save All Settings</button>
    <button type="button" class="btn btn-danger" onclick="resetAll()">🔄 Reset All to Defaults</button>
    <a href="/dashboard.php" class="btn btn-secondary">Cancel</a>
</div>

</form>

<!-- ── Password Change (separate form) ──────────────────────────────── -->
<div class="card" style="margin-top:1.5rem">
    <div class="card-header"><h2>🔐 Change Password</h2></div>
    <div class="card-body settings-grid">
        <form method="POST" action="/settings.php">
            <input type="hidden" name="_csrf" value="<?= csrf_token() ?>">
            <input type="hidden" name="action" value="change_password">

            <div class="setting-row">
                <label>Current Password</label>
                <div class="setting-control">
                    <input type="password" name="current_password" class="form-input" required autocomplete="current-password">
                </div>
            </div>
            <div class="setting-row">
                <label>New Password</label>
                <div class="setting-control">
                    <input type="password" name="new_password" class="form-input" required minlength="6" autocomplete="new-password">
                </div>
            </div>
            <div class="setting-row">
                <label>Confirm Password</label>
                <div class="setting-control">
                    <input type="password" name="confirm_password" class="form-input" required minlength="6" autocomplete="new-password">
                </div>
            </div>
            <div class="form-actions" style="margin-top:1rem">
                <button type="submit" class="btn btn-secondary">🔐 Change Password</button>
            </div>
        </form>
    </div>
</div>

<style>
.btn-reset {
    background: none;
    border: 1px solid var(--border);
    color: var(--text-muted);
    width: 28px;
    height: 28px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 1rem;
    line-height: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: all .15s;
}
.btn-reset:hover {
    background: var(--primary);
    color: #fff;
    border-color: var(--primary);
}
.card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.btn-reset-section {
    font-size: .75rem;
    padding: .2rem .6rem;
    opacity: .7;
}
.btn-reset-section:hover { opacity: 1; }
.setting-control {
    display: flex;
    align-items: center;
    gap: .5rem;
    flex-wrap: wrap;
}
.field-changed { outline: 2px solid var(--warning); border-radius: 4px; }
</style>

<script>
function resetField(btn) {
    // Find the input/select/checkbox in the same .setting-control
    var control = btn.closest('.setting-control');
    var input = control.querySelector('input[data-default], select[data-default]');
    if (!input) {
        // Try checkbox inside toggle
        input = control.querySelector('.toggle input[data-default]');
    }
    if (!input) return;

    var def = input.getAttribute('data-default');

    if (input.type === 'checkbox') {
        input.checked = (def === 'checked');
    } else if (input.tagName === 'SELECT') {
        input.value = def;
    } else {
        input.value = def;
    }

    // Flash effect
    input.classList.add('field-changed');
    setTimeout(function() { input.classList.remove('field-changed'); }, 800);
}

function resetDays() {
    var defaults = [1,2,3,4,5];
    var group = document.querySelector('.days-group');
    if (!group) return;
    group.querySelectorAll('input[type=checkbox]').forEach(function(cb) {
        cb.checked = defaults.includes(parseInt(cb.value));
    });
}

function resetSection(btn) {
    var card = btn.closest('.card');
    if (!card) return;
    if (!confirm('Reset this entire section to defaults?')) return;

    // Reset all data-default fields in this card
    card.querySelectorAll('[data-default]').forEach(function(input) {
        var def = input.getAttribute('data-default');
        if (input.type === 'checkbox') {
            input.checked = (def === 'checked');
        } else if (input.tagName === 'SELECT') {
            input.value = def;
        } else {
            input.value = def;
        }
    });

    // Reset days group if present
    var dg = card.querySelector('.days-group');
    if (dg) resetDays();
}

function resetAll() {
    if (!confirm('Reset ALL settings to factory defaults?\n\n(You still need to click Save to apply)')) return;

    document.querySelectorAll('[data-default]').forEach(function(input) {
        var def = input.getAttribute('data-default');
        if (input.type === 'checkbox') {
            input.checked = (def === 'checked');
        } else if (input.tagName === 'SELECT') {
            input.value = def;
        } else {
            input.value = def;
        }
    });

    resetDays();
    alert('All fields reset to defaults.\nClick "Save All Settings" to apply.');
}
</script>

<?php require_once __DIR__ . '/../includes/footer.php'; ?>
