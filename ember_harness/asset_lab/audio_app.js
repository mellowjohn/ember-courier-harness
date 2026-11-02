(() => {
  'use strict';
  const audio = EmberAudio.create();
  const $ = selector => document.querySelector(selector);
  let parcels = 0, paused = false;
  audio.mountControls($('#mixer'));
  const message = value => { $('#event').textContent = value; };
  async function enable() {
    if (!await audio.unlock()) { message('Sound is unavailable. You can still try the controls.'); return false; }
    if (paused) { paused=false; audio.setPaused(false); $('#pause').textContent='Pause'; }
    return true;
  }
  function cue(name) {
    const played = audio.play(name);
    if (name === 'pickup') $('#score').textContent = 'Parcels delivered: '+(++parcels);
    message(played ? 'Playing: '+name : 'Cue: '+name+' · start or resume sound to hear it');
  }
  $('#start').addEventListener('click', async () => {
    if (!await enable()) return;
    $('#music').value='courier'; $('#ambience').value='wind';
    audio.startMusic('courier'); audio.startAmbience('wind'); audio.play('ui');
    message('Sound enabled · deliver a parcel or try a cue.');
  });
  for (const name of EmberAudio.effects) {
    const button=document.createElement('button'); button.textContent=name[0].toUpperCase()+name.slice(1);
    button.dataset.cue=name; button.addEventListener('click',async () => { if (await enable()) cue(name); });
    $('#effects').append(button);
  }
  for (const [selector,start,stop] of [['#music','startMusic','stopMusic'],['#ambience','startAmbience','stopAmbience']]) {
    $(selector).addEventListener('change',async event => {
      if (!event.target.value) { audio[stop](); return; }
      if (await enable()) { audio[start](event.target.value); message('Playing: '+event.target.selectedOptions[0].textContent); }
    });
  }
  $('#pause').addEventListener('click',() => {
    paused=!paused; audio.setPaused(paused); $('#pause').textContent=paused?'Resume':'Pause'; message(paused?'Sound paused':'Sound resumed');
  });
  $('#stop').addEventListener('click',() => {
    audio.stopAll(); $('#music').value=''; $('#ambience').value=''; message('All sounds stopped.');
  });
  document.addEventListener('keydown',event => {
    if (event.repeat || /^(INPUT|SELECT|TEXTAREA|BUTTON)$/.test(event.target.tagName)) return;
    const name={'Space':'jump','KeyP':'pickup','KeyH':'hit'}[event.code];
    if (name) { event.preventDefault(); cue(name); }
  });
  addEventListener('pagehide',() => audio.dispose(),{once:true});
  // Read-only diagnostics for browser checks; no simulated audio-success claim.
  globalThis.soundDemo=Object.freeze({diagnostics:audio.diagnostics});
})();
