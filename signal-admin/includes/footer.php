</main>

<footer class="admin-footer">
    <span><?= APP_NAME ?> v<?= APP_VERSION ?></span>
    <span>signal.lstrading.xyz</span>
    <span id="footer-time"></span>
</footer>

<script src="/assets/js/admin.js"></script>
<script>
// Live clock
function updateClock() {
    const now = new Date();
    const opts = {
        timeZone: '<?= TIMEZONE ?>',
        weekday: 'short', year: 'numeric', month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
    };
    const timeStr = now.toLocaleString('en-US', opts);
    const el = document.getElementById('server-time');
    if (el) el.textContent = timeStr + ' (<?= TIMEZONE ?>)';
    const ft = document.getElementById('footer-time');
    if (ft) ft.textContent = timeStr;
}
setInterval(updateClock, 1000);
updateClock();
</script>
</body>
</html>
