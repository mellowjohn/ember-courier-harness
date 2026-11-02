/* Original procedural game audio. No network, samples, microphone or dependencies. */
(() => {
  'use strict';
  const buses = ['master', 'sfx', 'music', 'ambience'];
  const effects = Object.freeze({
    jump: [220, 660, .16, 'square', .17], land: [110, 45, .12, 'triangle', .3],
    pickup: [660, 1320, .18, 'sine', .32], hit: [180, 35, .2, 'sawtooth', .2],
    attack: [520, 80, .1, 'sawtooth', .16], footstep: [80, 40, .045, 'triangle', .23],
    win: [523, 1046, .65, 'triangle', .25], lose: [330, 82, .7, 'triangle', .25],
    ui: [600, 800, .065, 'sine', .18]
  });
  const tracks = Object.freeze({
    courier: {bpm:112, steps:[[60,64,67],null,[72],[67],[62,65,69],null,[74],[69],
      [57,60,64],null,[72],[64],[55,59,62],null,[67],null]},
    explore: {bpm:72, steps:[[48,55,62],null,null,[67],null,[62],null,null,
      [53,60,67],null,null,[72],null,[67],null,null]},
    tension: {bpm:136, steps:[[45],[57],null,[46],[45],null,[57],null,
      [41],[53],null,[46],[44],null,[56],null]}
  });
  const range = (n, min, max, name) => {
    if (!Number.isFinite(n) || n < min || n > max) throw new RangeError(name);
    return n;
  };
  function create() {
    let context = null, master = null, limiter = null, noise = null, disposed = false;
    let muted = false, paused = false, hidden = Boolean(globalThis.document?.hidden);
    let unlocked = false, pendingUnlock = null, timer = null, music = null, ambience = null;
    let sequence = 0, nextNote = 0, error = null;
    const levels = {master:.6, sfx:.65, music:.3, ambience:.2};
    const gains = {}, voices = new Set(), cooldowns = new Map(), controls = new Set();
    const ready = () => !disposed && unlocked && !paused && !hidden && context?.state === 'running';
    const updateControls = () => { for (const refresh of controls) refresh(); };
    function syncGain() {
      if (master) master.gain.setTargetAtTime(muted || paused || hidden ? 0 : levels.master, context.currentTime, .015);
      for (const bus of buses.slice(1)) if (gains[bus]) gains[bus].gain.setTargetAtTime(levels[bus], context.currentTime, .015);
      updateControls();
    }
    function release(voice, stop = false) {
      if (!voices.delete(voice)) return;
      if (stop) { try { voice.source.stop(); } catch {} }
      for (const node of voice.nodes) { try { node.disconnect(); } catch {} }
    }
    function clearBus(bus) {
      for (const voice of [...voices]) if (!bus || voice.bus === bus) release(voice, true);
    }
    function route(source, envelope, bus, pan, extra = []) {
      if (voices.size >= 32) release(voices.values().next().value, true);
      const panner = context.createStereoPanner(); panner.pan.value = pan;
      source.connect(envelope); envelope.connect(panner); panner.connect(gains[bus]);
      const voice = {source, bus, nodes:[source, envelope, panner, ...extra]};
      voices.add(voice); source.onended = () => release(voice);
      return voice;
    }
    function note(options, bus = 'sfx', when) {
      const frequency = range(options.frequency ?? 440, 20, 20000, 'frequency');
      const end = range(options.endFrequency ?? frequency, 20, 20000, 'endFrequency');
      const duration = range(options.duration ?? .15, .02, 4, 'duration');
      const gain = range(options.gain ?? .2, 0, 1, 'gain');
      const pan = range(options.pan ?? 0, -1, 1, 'pan');
      const type = options.type ?? 'sine';
      if (!['sine','triangle','square','sawtooth'].includes(type)) throw new RangeError('type');
      if (!ready()) return false;
      const time = when ?? context.currentTime;
      const oscillator = context.createOscillator(), envelope = context.createGain();
      oscillator.type = type; oscillator.frequency.setValueAtTime(frequency, time);
      oscillator.frequency.exponentialRampToValueAtTime(end, time + duration);
      envelope.gain.setValueAtTime(0, time);
      envelope.gain.linearRampToValueAtTime(gain, time + .008);
      envelope.gain.exponentialRampToValueAtTime(.0001, time + duration);
      route(oscillator, envelope, bus, pan);
      oscillator.start(time); oscillator.stop(time + duration + .01);
      return true;
    }
    function schedule() {
      if (!music || !ready()) return;
      const stepTime = 30 / music.bpm;
      // A throttled timer skips elapsed notes instead of replaying a backlog.
      if (nextNote < context.currentTime - .15) {
        const skip = Math.ceil((context.currentTime - nextNote) / stepTime);
        sequence = (sequence + skip) % music.steps.length; nextNote += skip * stepTime;
      }
      while (nextNote < context.currentTime + .12) {
        const chord = music.steps[sequence];
        if (chord) for (const midi of chord) note({frequency:440 * 2 ** ((midi-69)/12),
          duration:Math.min(2, stepTime * 1.7), type:'triangle', gain:.16 / Math.sqrt(chord.length)}, 'music', nextNote);
        sequence = (sequence + 1) % music.steps.length; nextNote += stepTime;
      }
    }
    async function unlock() {
      if (disposed) return false;
      if (pendingUnlock) return pendingUnlock;
      pendingUnlock = (async () => {
        try {
          if (!context) {
            const Constructor = globalThis.AudioContext || globalThis.webkitAudioContext;
            if (!Constructor) { error = 'Audio is unavailable in this browser'; return false; }
            context = new Constructor(); master = context.createGain(); limiter = context.createDynamicsCompressor();
            limiter.threshold.value = -8; limiter.ratio.value = 12;
            master.connect(limiter); limiter.connect(context.destination);
            for (const bus of buses.slice(1)) { gains[bus] = context.createGain(); gains[bus].connect(master); }
            context.addEventListener('statechange', updateControls);
            syncGain();
          }
          await context.resume();
          if (disposed) return false;
          unlocked = context.state === 'running';
          error = unlocked ? null : 'Use Enable sound to try again';
          syncGain(); return unlocked;
        } catch { error = 'Sound could not start. Use Enable sound to try again'; return false; }
      })();
      try { return await pendingUnlock; } finally { pendingUnlock = null; updateControls(); }
    }
    function stopMusic() {
      if (timer !== null) clearInterval(timer);
      timer = null; music = null; clearBus('music');
    }
    function stopAmbience() { ambience = null; clearBus('ambience'); }
    function stopAll() { stopMusic(); stopAmbience(); clearBus(); cooldowns.clear(); }
    function startMusic(track = 'courier') {
      const value = typeof track === 'string' ? tracks[track] : track;
      if (!value || !Array.isArray(value.steps) || !value.steps.length || value.steps.length > 64) throw new RangeError('music track');
      range(value.bpm, 40, 240, 'bpm');
      const steps = value.steps.map(chord => {
        if (chord === null) return null;
        if (!Array.isArray(chord) || !chord.length || chord.length > 3) throw new RangeError('music chord');
        return chord.map(midi => { range(midi,24,96,'MIDI note'); if (!Number.isInteger(midi)) throw new RangeError('MIDI note'); return midi; });
      });
      if (!ready()) return false;
      stopMusic(); music = {bpm:value.bpm,steps}; sequence = 0; nextNote = context.currentTime + .01;
      schedule(); timer = setInterval(schedule, 40); return true;
    }
    function startAmbience(kind = 'wind') {
      if (!['wind','embers'].includes(kind)) throw new RangeError('ambience');
      if (!ready()) return false;
      stopAmbience();
      if (!noise) {
        noise = context.createBuffer(1, context.sampleRate * 2, context.sampleRate);
        const data = noise.getChannelData(0); let previous = 0, seed = 123456789;
        for (let i=0; i<data.length; i++) {
          seed = (Math.imul(seed,1664525) + 1013904223) >>> 0;
          previous = (previous + (seed / 2147483648 - 1) * .04) / 1.04; data[i] = previous * 3;
        }
        // Join the loop without an abrupt waveform discontinuity.
        const seam = Math.min(1024, data.length / 2);
        for (let i=0; i<seam; i++) {
          const blend=(i+1)/seam;
          data[data.length-seam+i] = data[data.length-seam+i]*(1-blend)+data[0]*blend;
        }
      }
      const source = context.createBufferSource(), filter = context.createBiquadFilter(), envelope = context.createGain();
      source.buffer = noise; source.loop = true;
      filter.type = 'lowpass'; filter.frequency.value = kind === 'wind' ? 450 : 1500;
      source.connect(filter);
      envelope.gain.setValueAtTime(0,context.currentTime);
      envelope.gain.linearRampToValueAtTime(kind === 'wind' ? .7 : .4,context.currentTime+.6);
      // Route the filter output while retaining the real source for stop/onended.
      const voice = route(filter,envelope,'ambience',0,[source]);
      voice.source = source; source.onended = () => release(voice);
      source.start(); ambience = kind; return true;
    }
    function visibility() {
      hidden = Boolean(globalThis.document?.hidden); syncGain();
      if (!context || !unlocked || disposed) return;
      // Stop the clock in background tabs; keep the musical position on return.
      const operation = hidden || paused ? context.suspend() : context.resume();
      operation.catch(() => { error = 'Use Enable sound to resume'; updateControls(); });
    }
    globalThis.document?.addEventListener('visibilitychange', visibility);
    function diagnostics() {
      return {supported:Boolean(globalThis.AudioContext || globalThis.webkitAudioContext),
        state:disposed ? 'disposed' : !context ? 'locked' : context.state,
        muted, paused, hidden, volumes:{...levels}, activeVoices:voices.size,
        music:music !== null, ambience, error};
    }
    function mountControls(container) {
      const doc = container.ownerDocument;
      const group = doc.createElement('fieldset'), legend = doc.createElement('legend');
      legend.textContent = 'Sound'; group.append(legend);
      const enable = doc.createElement('button'), mute = doc.createElement('button'), status = doc.createElement('span');
      enable.type = mute.type = 'button'; enable.textContent = 'Enable sound'; status.setAttribute('role','status');
      enable.addEventListener('click', () => { void unlock(); });
      mute.addEventListener('click', () => api.setMuted(!muted));
      group.append(enable, mute, status);
      const sliders = {};
      for (const bus of buses) {
        const label = doc.createElement('label'), input = doc.createElement('input');
        label.textContent = bus[0].toUpperCase()+bus.slice(1)+' volume ';
        input.type = 'range'; input.min = '0'; input.max = '1'; input.step = '.01';
        input.addEventListener('input', () => api.setVolume(bus, Number(input.value)));
        label.append(input); group.append(label); sliders[bus] = input;
      }
      const refresh = () => {
        const state = diagnostics();
        status.textContent = disposed ? 'Sound closed' : error || (paused || hidden ? 'Sound paused' : ready() ? 'Sound enabled' : 'Sound off');
        enable.disabled = disposed || !state.supported || ready(); mute.disabled = disposed;
        mute.textContent = muted ? 'Unmute' : 'Mute'; mute.setAttribute('aria-pressed',String(muted));
        for (const bus of buses) { sliders[bus].value = levels[bus]; sliders[bus].disabled = disposed; }
      };
      controls.add(refresh); container.append(group); refresh();
      return () => { controls.delete(refresh); group.remove(); };
    }
    const api = {
      unlock, startMusic, stopMusic, startAmbience, stopAmbience, stopAll, diagnostics, mountControls,
      tone:options => note(options),
      play(name, options = {}) {
        const preset = effects[name]; if (!preset) throw new RangeError('Unknown sound: '+name);
        const pan = range(options.pan ?? 0,-1,1,'pan');
        if (!ready()) return false;
        const now = context.currentTime, cooldown = name === 'footstep' ? .12 : .055;
        if (now - (cooldowns.get(name) ?? -Infinity) < cooldown) return false;
        cooldowns.set(name,now);
        return note({frequency:preset[0],endFrequency:preset[1],duration:preset[2],type:preset[3],gain:preset[4],pan});
      },
      setMuted(value) { if (typeof value !== 'boolean') throw new TypeError('muted'); muted = value; syncGain(); },
      setVolume(bus,value) { if (!buses.includes(bus)) throw new RangeError('bus'); levels[bus]=range(value,0,1,'volume'); syncGain(); },
      setPaused(value) { if (typeof value !== 'boolean') throw new TypeError('paused'); paused=value; visibility(); },
      dispose() {
        if (disposed) return;
        disposed=true; stopAll(); globalThis.document?.removeEventListener('visibilitychange',visibility);
        if (context) {
          context.removeEventListener('statechange',updateControls);
          for (const node of [master,limiter,...Object.values(gains)]) node.disconnect();
          void context.close().catch(() => {});
        }
        updateControls(); controls.clear(); noise=null;
      }
    };
    return Object.freeze(api);
  }
  globalThis.EmberAudio = Object.freeze({create, effects:Object.freeze(Object.keys(effects)), tracks:Object.freeze(Object.keys(tracks))});
})();
