(() => {
  'use strict';
  const s = EMBER_ASSET.spec;
  const canvas = document.querySelector('#stage'), ctx = canvas.getContext('2d');
  const status = document.querySelector('#status'), slider = document.querySelector('#frame');
  const paused = document.querySelector('#paused'), menu = document.querySelector('#animation');
  const playback = document.querySelector('#playback-state'), keys = new Set(), pointers = new Map();
  document.querySelector('#title').textContent = s.display_name;
  document.querySelector('#description').textContent = s.art_direction;
  EmberSprites.load(EMBER_ASSET).then(atlas => {
    const player = atlas.createPlayer(), names = Object.keys(atlas.animations);
    let last = null, x = 210, facingLeft = false;
    for (const name of names) {
      const option = document.createElement('option'); option.value = name; option.textContent = name; menu.append(option);
    }
    menu.value = player.animation;
    const sync = () => {
      slider.max = atlas.animations[player.animation].frames.length - 1;
      slider.value = player.clipFrame; menu.value = player.animation;
      document.querySelector('#animation-state').textContent = player.animation;
      playback.textContent = paused.checked ? 'Paused' : player.completed ? 'Finished' : 'Playing';
    };
    const replay = () => { player.play(menu.value, {restart: true}); paused.checked = false; sync(); };
    const action = () => {
      const name = Object.hasOwn(atlas.animations, 'attack') ? 'attack' : menu.value;
      if (player.animation === name && !atlas.animations[name].loop && !player.completed) return;
      player.play(name, {restart: true}); paused.checked = false; sync();
    };
    document.querySelector('#replay').onclick = replay;
    document.querySelector('#action').onclick = action;
    menu.onchange = replay;
    slider.oninput = () => { player.seek(Number(slider.value)); paused.checked = true; sync(); };
    paused.onchange = sync;
    window.addEventListener('keydown', e => {
      if (/INPUT|SELECT|BUTTON|TEXTAREA/.test(e.target.tagName)) return;
      if (['ArrowLeft', 'ArrowRight', 'a', 'd', ' '].includes(e.key)) {
        e.preventDefault(); keys.add(e.key);
        if (e.key === ' ' && !e.repeat) action();
      }
    });
    window.addEventListener('keyup', e => keys.delete(e.key));
    window.addEventListener('blur', () => { keys.clear(); pointers.clear(); });
    for (const [id, direction] of [['left', -1], ['right', 1]]) {
      const button = document.getElementById(id);
      button.onpointerdown = e => { e.preventDefault(); button.setPointerCapture(e.pointerId); pointers.set(e.pointerId, direction); };
      button.onpointerup = button.onpointercancel = button.onlostpointercapture = e => pointers.delete(e.pointerId);
    }
    document.querySelectorAll('button,input,select').forEach(el => el.disabled = false);
    document.querySelector('#load-state').textContent = 'Asset ready';
    function render(now) {
      const dt = last === null ? 0 : Math.min((now - last) / 1000, .1); last = now;
      if (!paused.checked) {
        const direction = Math.sign((keys.has('ArrowRight') || keys.has('d') ? 1 : 0) -
          (keys.has('ArrowLeft') || keys.has('a') ? 1 : 0) + Array.from(pointers.values()).reduce((a, b) => a + b, 0));
        const clip = atlas.animations[player.animation], actionLocked = !clip.loop && !player.completed;
        if (direction && !actionLocked) {
          x = Math.max(85, Math.min(335, x + direction * 160 * dt)); facingLeft = direction < 0;
          if (Object.hasOwn(atlas.animations, 'walk')) player.play('walk');
        } else if (!direction && player.animation === 'walk' && Object.hasOwn(atlas.animations, 'idle')) player.play('idle');
        player.update(dt);
      }
      const [w, h] = s.frame_size;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      player.draw(ctx, x, 280, {scale: Math.min(1, 160 / w, 160 / h), flipX: facingLeft});
      player.draw(ctx, 600, 280, {scale: Math.min(3, 330 / w, 260 / h), flipX: facingLeft});
      ctx.fillStyle = '#c4d6e4'; ctx.font = '16px system-ui';
      ctx.fillText('Gameplay scale', 140, 380); ctx.fillText('Enlarged inspection', 520, 380);
      status.textContent = `Frame ${player.frame + 1} / ${s.frames} · ${atlas.animations[player.animation].fps} fps · ${s.blend}`;
      document.querySelector('#position').textContent = Math.round(x);
      sync(); requestAnimationFrame(render);
    }
    sync(); requestAnimationFrame(render);
  }).catch(error => {
    document.querySelector('#load-state').textContent = 'Asset failed to load';
    document.querySelector('#error').textContent = error.message;
  });
})();
