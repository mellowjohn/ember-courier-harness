/* Browser dictation is user-started and only edits the chosen text field. */
window.EmberVoice = (() => {
  'use strict';
  let active = null;
  const widgets = new Set();
  const supported = () => window.SpeechRecognition || window.webkitSpeechRecognition;
  function stop() { if (active) active.finish(); }
  function attach(input, parent, name, getSession = () => null) {
    const row = document.createElement('div'); row.className = 'voice-input'; parent.append(row);
    const button = document.createElement('button'); button.type = 'button'; button.className = 'button voice-button';
    button.textContent = 'Dictate'; button.setAttribute('aria-label', 'Dictate ' + name); button.setAttribute('aria-pressed', 'false'); row.append(button);
    const status = document.createElement('small'); status.setAttribute('role', 'status'); row.append(status);
    const widget = { input, row, update() { const disabled = !supported() || input.disabled || input.readOnly; if (button.disabled !== disabled) button.disabled = disabled; } };
    widgets.add(widget);
    status.textContent = supported() ? 'Browser dictation · review before sending. Your browser may process audio online.' : 'Dictation is unavailable in this browser. You can still type.';
    button.onclick = () => {
      if (active?.widget === widget) { stop(); return; }
      stop();
      if (!supported() || input.disabled || !input.isConnected) return;
      const Recognition = supported();
      let recognition;
      try { recognition = new Recognition(); }
      catch { status.textContent = 'Dictation could not start. You can still type.'; return; }
      const sid = getSession(), controller = new AbortController();
      const start = input.selectionStart ?? input.value.length, end = input.selectionEnd ?? start;
      const original = input.value, before = original.slice(0, start), after = original.slice(end);
      let spoken = '', lastValue = original, finished = false, heard = false;
      const render = () => {
        const prefix = spoken && before && !/\s$/.test(before) ? ' ' : '';
        const suffix = spoken && after && !/^\s/.test(after) ? ' ' : '';
        let value = before + prefix + spoken + suffix + after;
        if (input.maxLength >= 0 && value.length > input.maxLength) {
          const room = Math.max(0, input.maxLength - before.length - after.length - prefix.length - suffix.length);
          value = room ? before + prefix + spoken.slice(0, room) + suffix + after : original;
          status.textContent = 'Text limit reached. Review your text before sending.';
        }
        input.value = lastValue = value;
        input.dispatchEvent(new Event('input', { bubbles: true }));
      };
      const finish = () => {
        if (finished) return; finished = true; controller.abort();
        if (active?.widget === widget) active = null;
        button.textContent = 'Dictate'; button.setAttribute('aria-label', 'Dictate ' + name); button.setAttribute('aria-pressed', 'false');
        row.classList.remove('listening');
        if (status.textContent.startsWith('Listening') || status.textContent.startsWith('Starting'))
          status.textContent = heard ? 'Dictation added. Review before sending.' : 'No speech heard. Try again or type.';
        try { recognition.abort(); } catch {}
      };
      active = { widget, finish };
      recognition.lang = navigator.language || 'en-US'; recognition.continuous = true; recognition.interimResults = true;
      recognition.onstart = () => { if (!finished) status.textContent = 'Listening… click Stop when finished.'; };
      recognition.onresult = event => {
        if (finished) return;
        if (!input.isConnected || input.disabled || input.value !== lastValue ||
            sid !== getSession()) { finish(); return; }
        spoken = Array.from(event.results, result => result[0].transcript).join(' ').trim();
        if (!spoken) return;
        heard ||= !!spoken; render();
      };
      recognition.onerror = event => {
        if (finished) return;
        const messages = { 'not-allowed': 'Microphone permission was denied. Allow it in your browser or type instead.',
          'service-not-allowed': 'Browser dictation is unavailable. You can still type.',
          'audio-capture': 'No microphone is available. Check your microphone or type instead.',
          'network': 'Dictation could not connect. Check your connection or type instead.',
          'no-speech': 'No speech heard. Try again or type.' };
        status.textContent = messages[event.error] || 'Dictation stopped. Your text is still here.'; finish();
      };
      recognition.onend = finish;
      input.addEventListener('input', () => { if (input.value !== lastValue) finish(); }, { signal: controller.signal });
      button.textContent = 'Stop dictation'; button.setAttribute('aria-label', 'Stop dictating ' + name); button.setAttribute('aria-pressed', 'true');
      row.classList.add('listening'); status.textContent = 'Starting microphone…';
      try { recognition.start(); } catch { status.textContent = 'Dictation could not start. You can still type.'; finish(); }
    };
    widget.update(); return widget;
  }
  new MutationObserver(() => {
    for (const widget of widgets) {
      if (!widget.row.isConnected) { if (active?.widget === widget) stop(); widgets.delete(widget); }
      else widget.update();
    }
    if (active && (active.widget.input.disabled || !active.widget.input.isConnected)) stop();
  }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['disabled', 'readonly'] });
  addEventListener('pagehide', stop);
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
  return { attach, stop };
})();
