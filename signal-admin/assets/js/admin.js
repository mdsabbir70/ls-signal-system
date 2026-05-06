/**
 * LS Signal Admin — JS
 * Auto-refresh, confirmations, AJAX bot toggle
 */

'use strict';

// ── Auto-refresh dashboard every 60 seconds ───────────────────────────────────
(function initAutoRefresh() {
    const refreshPages = ['dashboard.php', 'signals.php'];
    const current = window.location.pathname.split('/').pop();
    if (refreshPages.includes(current)) {
        setTimeout(() => location.reload(), 60_000);
    }
})();

// ── AJAX bot toggle ───────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    const toggleForms = document.querySelectorAll('form[action="/actions/toggle_bot.php"]');
    toggleForms.forEach(form => {
        form.addEventListener('submit', e => {
            const btn = form.querySelector('button[type="submit"]');
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Updating...';
            }
        });
    });

    // Confirm destructive actions
    document.querySelectorAll('[data-confirm]').forEach(el => {
        el.addEventListener('click', ev => {
            if (!confirm(el.dataset.confirm)) ev.preventDefault();
        });
    });

    // Flash messages auto-dismiss after 4s
    document.querySelectorAll('.alert').forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity .4s';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 400);
        }, 4000);
    });
});

// ── Signal close modal ─────────────────────────────────────────────────────────
function openCloseModal(signalId, entryPrice) {
    const modal = document.getElementById('close-modal');
    if (!modal) return;
    modal.dataset.signalId = signalId;
    document.getElementById('close-entry-price').textContent = entryPrice;
    modal.classList.add('open');
}

function closeModal() {
    const modal = document.getElementById('close-modal');
    if (modal) modal.classList.remove('open');
}

async function submitCloseSignal() {
    const modal    = document.getElementById('close-modal');
    const signalId = modal?.dataset.signalId;
    const price    = document.getElementById('close-price-input')?.value;
    const reason   = document.getElementById('close-reason-select')?.value;

    if (!signalId || !price) {
        alert('Please enter a close price.');
        return;
    }

    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';

    const resp = await fetch(`/actions/close_signal.php`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ signal_id: signalId, close_price: price, reason, _csrf: csrf }),
    });

    const data = await resp.json();
    if (data.success) {
        closeModal();
        location.reload();
    } else {
        alert('Error: ' + (data.error || 'Unknown error'));
    }
}
