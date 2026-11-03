/* Shared typography specimens, original 24px SVG icon set, and observed status copy. */
window.EmberUI = (() => {
  'use strict';
  const paths = Object.freeze({
    ember: ['M12 3c1 5-4 6-4 10a4 4 0 0 0 8 0c0-2-1-3-1-3s5 3 5 7a8 8 0 0 1-16 0C4 10 10 9 12 3Z'],
    plus: ['M12 5v14M5 12h14'],
    chat: ['M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-6 3V6a2 2 0 0 1 2-2Z', 'M7 9h10M7 13h6'],
    send: ['m21 3-7 18-4-7-7-4L21 3Z', 'm10 14 5-5'],
    tools: ['m14 5 5-2-1 5-4 2-9 11-3-3 11-9 1-4Z'],
    assets: ['m12 3 9 5v9l-9 5-9-5V8l9-5Z', 'm3 8 9 5 9-5M12 13v9M7.5 5.5l9 5'],
    plan: ['M9 4h6v4H9V4Z', 'M9 6H5v15h14V6h-4M8 12h8M8 16h5'],
    download: ['M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5'],
    activity: ['M3 12h4l3-8 4 16 3-8h4'],
    type: ['M4 5h16M12 5v15M8 20h8'],
    play: ['m8 4 12 8-12 8V4Z'],
    back: ['m10 5-7 7 7 7M3 12h18'],
    close: ['m6 6 12 12M6 18 18 6'],
    check: ['m5 12 4 4L19 6'],
    alert: ['m12 3 10 18H2L12 3Z', 'M12 9v4m0 4h.01'],
    clock: ['M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z', 'M12 7v5l3 2'],
    sparkles: ['m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z', 'M20 2v4M18 4h4'],
    gamepad: ['M7 7h10c3 0 4 3 5 9 .4 3-2 4-4 2l-2-2H8l-2 2c-2 2-4.4 1-4-2 1-6 2-9 5-9Z', 'M7 10v4M5 12h4M16 11h.01M19 14h.01'],
    compass: ['M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z', 'm16 8-3 5-5 3 3-5 5-3Z'],
    arrow: ['M4 12h16m-6-6 6 6-6 6'],
    folder: ['M3 6h6l2 3h10v11H3V6Z'],
    edit: ['m15 4 5 5-11 11H4v-5L15 4Z', 'm12 7 5 5'],
    restart: ['M4 9a8 8 0 1 1 0 6M4 3v6h6'],
    fullscreen: ['M8 3H3v5m13-5h5v5M3 16v5h5m8 0h5v-5'],
    external: ['M14 3h7v7m0-7L10 14M10 3H3v18h18v-7']
  });
  const typography = Object.freeze([
    ['display', 'Make room for your next idea.', 'Page titles'],
    ['heading', 'A little spark, a whole new world.', 'Major sections'],
    ['title', 'Everything in its right place', 'Panels and cards'],
    ['body', 'Tell Ember what you imagine. We’ll shape it together.', 'Conversation and reading'],
    ['label', 'Ready when you are', 'Controls and field labels'],
    ['caption', 'Saved here, ready for next time.', 'Supporting text and timestamps'],
    ['overline', 'Your workspace', 'Short section labels'],
    ['code', 'project / assets / courier.glb', 'Paths and technical evidence']
  ]);
  const actions = Object.freeze({
    'New session': 'plus', 'Send message': 'send', 'Working…': 'sparkles',
    'Project tools': 'tools', 'Back to game': 'back', 'Rename session': 'edit',
    'Plan & project': 'plan', 'Known assets': 'assets', 'Versions & downloads': 'download',
    'Activity & audit': 'activity', 'Typography & icons': 'type', 'Chat with Ember': 'chat',
    'Play & refine': 'play', 'Restart game': 'restart', 'Fullscreen': 'fullscreen',
    'Open in new window': 'external', 'Choose folder…': 'folder',
    'Approve & play': 'check', 'Accept asset & play': 'check', 'Try proposed changes': 'play',
    'Return to approved game': 'back', 'Retry reply': 'restart',
    'Download game ZIP': 'download', 'Download project handoff': 'download'
  });
  const stages = Object.freeze({
    sending: ['send', 'Sending your little spark'],
    saved: ['check', 'Your message is tucked away safely'],
    context: ['plan', 'Gathering the project pieces'],
    provider_starting: ['ember', 'Waking up Muse'],
    muse_working: ['sparkles', 'Ember is thinking it through'],
    receiving: ['chat', 'A reply is taking shape'],
    provider_finished: ['check', 'The reply has arrived'],
    cached_reply: ['restart', 'Picking up the saved reply'],
    validating: ['check', 'Giving the reply a careful check'],
    proposal: ['tools', 'Wrapping up changes for your review'],
    awaiting_review: ['check', 'Ready for your eyes'],
    complete: ['check', 'Your reply is ready']
  });
  function icon(name, size = 'medium') {
    if (!Object.hasOwn(paths, name)) throw new Error('Unknown Ember icon: ' + name);
    const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg');
    for (const [key, value] of Object.entries({viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.7', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true', focusable: 'false', class: 'ember-icon'})) svg.setAttribute(key, value);
    svg.dataset.icon = name; svg.dataset.size = size;
    for (const d of paths[name]) { const path = document.createElementNS(ns, 'path'); path.setAttribute('d', d); svg.append(path); }
    return svg;
  }
  function label(node, text, name = actions[text]) {
    node.replaceChildren();
    if (name) node.append(icon(name, 'small'));
    node.append(document.createTextNode(text));
    return node;
  }
  function status(parent, {phase, state = 'active', title, context, dots = true} = {}) {
    const row = document.createElement('div'); row.className = 'ember-status';
    const stopped = state === 'failed' || state === 'interrupted';
    row.dataset.tone = stopped ? 'danger' : state === 'active' ? 'working' : 'success';
    const stage = stages[phase] || ['clock', title || 'Working on your request'];
    row.append(icon(stopped ? 'alert' : stage[0]));
    const copy = document.createElement('div'); copy.className = 'ember-status-copy'; row.append(copy);
    const heading = document.createElement('span'); heading.className = 'ember-status-title';
    heading.textContent = stopped ? (state === 'interrupted' ? 'Request interrupted' : 'Request stopped') : title || stage[1];
    copy.append(heading);
    if (state === 'active' && dots) {
      const dots = document.createElement('span'); dots.className = 'ember-dots'; dots.setAttribute('aria-hidden', 'true');
      for (let i = 0; i < 3; i++) { const dot = document.createElement('span'); dot.textContent = '.'; dots.append(dot); }
      heading.append(dots);
    }
    if (context) { const detail = document.createElement('p'); detail.className = 'ember-status-context'; detail.textContent = context; copy.append(detail); }
    parent.append(row); return row;
  }
  function renderLibrary(parent) {
    const add = (tag, text, host = parent, cls) => { const node = document.createElement(tag); node.textContent = text; if (cls) node.className = cls; host.append(node); return node; };
    add('h2', 'Typography & icons');
    add('p', 'One familiar visual language for every part of Ember. A readable type scale, simple line icons, and a little warmth while work is happening.', parent, 'library-intro');
    add('h3', 'Typography');
    for (const [role, sample, usage] of typography) {
      const row = add('div', '', parent, 'type-specimen');
      add('small', role + ' · ' + usage, row, 'type-caption'); add('p', sample, row, 'type-' + role);
    }
    add('h3', 'Iconography');
    add('p', 'A consistent 24 × 24 grid with rounded strokes. Icons accompany a readable label; meaning never depends on color alone.', parent, 'type-caption');
    const grid = add('div', '', parent, 'library-icons');
    for (const name of Object.keys(paths)) { const cell = add('div', '', grid, 'library-icon'); cell.append(icon(name)); add('small', name, cell); }
    add('h3', 'A little company while you wait');
    add('p', 'Messages follow real work stages. The dots pause when reduced motion is enabled.', parent, 'type-caption');
    for (const example of [
      {phase: 'context', context: 'Reading this session, project and known assets'},
      {phase: 'muse_working', context: 'Current task · Build the courier’s delivery route'},
      {phase: 'awaiting_review', state: 'complete', context: 'Review the proposed changes before applying them.'},
      {state: 'interrupted', context: 'Your message is saved. Retry when you’re ready.'}
    ]) { const card = add('div', '', parent, 'library-status'); status(card, example); }
  }
  return Object.freeze({icon, label, status, renderLibrary, typography, iconNames: Object.freeze(Object.keys(paths)), actions});
})();
