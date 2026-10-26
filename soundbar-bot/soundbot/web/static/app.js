(function () {
  const statusText = document.getElementById('status-text');
  const footNext = document.getElementById('foot-next');
  const btnRun = document.getElementById('btn-run');
  const btnNotify = document.getElementById('btn-notify');
  let wasRunning = false;

  function fmt(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleString(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  }

  async function poll() {
    try {
      const s = await (await fetch('/api/status')).json();
      if (s.running) {
        statusText.textContent = 'Checking… ' + (s.progress || '');
        btnRun.disabled = true;
      } else {
        statusText.textContent = s.last_run_at ? ('Last check ' + fmt(s.last_run_at)) : 'No check yet';
        btnRun.disabled = false;
        if (wasRunning && location.pathname === '/') location.reload();
      }
      footNext.textContent = s.next_run_at ? ('next check ' + fmt(s.next_run_at)) : '';
      if (s.last_error) statusText.textContent += ' · error: ' + s.last_error;
      wasRunning = s.running;
    } catch (e) { statusText.textContent = 'server unreachable'; }
  }

  btnRun.addEventListener('click', async () => {
    btnRun.disabled = true;
    await fetch('/api/run', { method: 'POST' });
    wasRunning = true;
    poll();
  });
  btnNotify.addEventListener('click', async () => {
    btnNotify.disabled = true;
    const r = await (await fetch('/api/test-notify', { method: 'POST' })).json();
    btnNotify.textContent = r.sent && r.sent.length ? ('Sent: ' + r.sent.join(', ')) : 'Nothing sent';
    setTimeout(() => { btnNotify.textContent = 'Test notification'; btnNotify.disabled = false; }, 4000);
  });

  poll();
  setInterval(poll, 3000);
})();
