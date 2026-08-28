(() => {
  const CONTROL_BY_ROLE_STICK = {
    'left:left': 'speed',
    'left:right': 'heading',
    'right:left': 'altitude',
    'right:right': 'vertical_speed',
  };
  const CONTROL_LABELS = {
    speed: 'SPD',
    heading: 'HDG',
    altitude: 'ALT',
    vertical_speed: 'V/S',
  };

  let sensitivityState = null;
  let sliderBusy = false;

  async function loadSensitivity() {
    const response = await fetch('/api/rotary-sensitivity');
    if (!response.ok) throw new Error(`Sensitivity API ${response.status}`);
    sensitivityState = await response.json();
    return sensitivityState;
  }

  function roleKeyFromCard(card) {
    const text = (card.querySelector('.role-name')?.textContent || '').trim().toUpperCase();
    if (text.startsWith('LEFT')) return 'left';
    if (text.startsWith('RIGHT')) return 'right';
    if (text.startsWith('CENTER')) return 'center';
    return null;
  }

  function tuningMarkup(control) {
    if (!sensitivityState) return '';
    const value = Number(sensitivityState.values?.[control] ?? 1);
    const base = Number(sensitivityState.defaults?.[control] ?? 1);
    const min = Number(sensitivityState.min ?? 0.5);
    const max = Number(sensitivityState.max ?? 3.0);
    return `
      <div class="rotary-tuning" data-control="${control}">
        <div class="rotary-tuning-head">
          <span class="rotary-tuning-title">Sensitivity / precision · ${CONTROL_LABELS[control]}</span>
          <span class="rotary-tuning-value">×${value.toFixed(2)}</span>
        </div>
        <input type="range" min="${min}" max="${max}" step="0.05" value="${value}"
          onpointerdown="beginRotarySensitivityDrag()"
          onpointerup="endRotarySensitivityDrag()"
          onpointercancel="endRotarySensitivityDrag()"
          oninput="previewRotarySensitivity(this)"
          onchange="saveRotarySensitivity('${control}', this.value)" />
        <div class="rotary-tuning-scale"><span>faster</span><span>finer / slower</span></div>
        <div class="rotary-tuning-note">Higher = more stick travel per FCU step. Base: ×${base.toFixed(2)}</div>
        <div class="rotary-tuning-actions"><button class="secondary" onclick="resetRotarySensitivity('${control}')">Reset</button></div>
      </div>`;
  }

  function installControls() {
    if (!sensitivityState) return;
    document.querySelectorAll('#controllers .card').forEach(card => {
      const role = roleKeyFromCard(card);
      if (!role) return;
      card.querySelectorAll('.stick-box').forEach((box, index) => {
        if (box.querySelector('.rotary-tuning')) return;
        const stick = index === 0 ? 'left' : 'right';
        const control = CONTROL_BY_ROLE_STICK[`${role}:${stick}`];
        if (!control) return;
        box.insertAdjacentHTML('beforeend', tuningMarkup(control));
      });
    });
  }

  window.beginRotarySensitivityDrag = () => { sliderBusy = true; };
  window.endRotarySensitivityDrag = () => {
    sliderBusy = false;
    setTimeout(installControls, 0);
  };
  window.previewRotarySensitivity = input => {
    sliderBusy = true;
    const root = input.closest('.rotary-tuning');
    if (root) root.querySelector('.rotary-tuning-value').textContent = `×${Number(input.value).toFixed(2)}`;
  };
  window.saveRotarySensitivity = async (control, rawValue) => {
    const precision = Number(rawValue);
    if (sensitivityState?.values) sensitivityState.values[control] = precision;
    try {
      const response = await fetch(`/api/rotary-sensitivity/${control}`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({precision}),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      sensitivityState = payload.sensitivity;
    } catch (error) {
      console.error('Failed to save rotary sensitivity', error);
      await loadSensitivity().catch(() => {});
    } finally {
      sliderBusy = false;
    }
  };
  window.resetRotarySensitivity = async control => {
    try {
      const response = await fetch(`/api/rotary-sensitivity/${control}/reset`, {method: 'POST'});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      sensitivityState = payload.sensitivity;
      const root = document.querySelector(`.rotary-tuning[data-control="${control}"]`);
      if (root) {
        root.querySelector('input[type=range]').value = sensitivityState.values[control];
        root.querySelector('.rotary-tuning-value').textContent = `×${Number(sensitivityState.values[control]).toFixed(2)}`;
      }
    } catch (error) {
      console.error('Failed to reset rotary sensitivity', error);
    }
  };

  const baseRender = render;
  render = function(state) {
    if (sliderBusy) return;
    baseRender(state);
    installControls();
  };

  loadSensitivity().then(installControls).catch(error => {
    console.error('Failed to load rotary sensitivity', error);
  });
})();
