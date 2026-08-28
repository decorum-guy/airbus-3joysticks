(() => {
  function ensurePill() {
    let pill = document.getElementById('aircraftBackendPill');
    if (pill) return pill;
    const row = document.querySelector('.status-row');
    if (!row) return null;
    pill = document.createElement('span');
    pill.id = 'aircraftBackendPill';
    pill.className = 'pill';
    pill.innerHTML = '<span id="aircraftBackendDot" class="dot"></span><span id="aircraftBackendText">Aircraft backend…</span>';
    row.appendChild(pill);
    return pill;
  }

  function update() {
    const pill = ensurePill();
    if (!pill) return;
    let state = null;
    try {
      state = currentState;
    } catch (_) {
      state = null;
    }
    const sim = state?.simconnect || {};
    const dot = document.getElementById('aircraftBackendDot');
    const text = document.getElementById('aircraftBackendText');
    if (!dot || !text) return;
    dot.className = 'dot';
    if (!sim.connected) {
      text.textContent = 'Aircraft backend offline';
      return;
    }
    if (sim.aircraft_family === 'flybywire_a32nx') {
      dot.classList.add('ok');
      text.textContent = 'A32NX · FULL CONTROLS';
      return;
    }
    dot.classList.add('warn');
    text.textContent = 'Generic controls only';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensurePill, { once: true });
  } else {
    ensurePill();
  }
  update();
  setInterval(update, 300);
})();
