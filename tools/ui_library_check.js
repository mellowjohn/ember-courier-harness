// Reuse the owned offline browser fixture; no provider calls or user sessions.
const assert = require('node:assert/strict');
const path = require('node:path');

module.exports = async function checkLibrary(page, view) {
  await page.locator('#chat-send:not([disabled])').waitFor();
  assert.equal(await page.locator('#conversation-history #known-assets').count(), 0);
  await view('assets');
  assert.equal(await page.locator('#workspace-tools #known-assets').count(), 1);
  await page.getByText('A home for your project’s little treasures.', {exact: false}).waitFor();
  await view('library');
  assert.equal(await page.locator('.type-specimen').count(), 8);
  assert.equal(await page.locator('.library-icon').count(), await page.evaluate(() => EmberUI.iconNames.length));
  assert.equal(await page.locator('.library-icon svg:not([aria-hidden="true"])').count(), 0);
  assert.equal(await page.locator('#workspace-tools-open').getAttribute('aria-label'), null);
  await page.screenshot({path: path.join(process.env.EMBER_BROWSER_OUTPUT, 'typography-library.png')});
  await page.emulateMedia({reducedMotion: 'reduce'});
  assert.equal(await page.locator('.library-status .ember-dots span').first().evaluate(n => getComputedStyle(n).animationName), 'none');
  await page.emulateMedia({reducedMotion: 'no-preference'});
  await view('chat');

  let calls = 0, release, requestStarted;
  const gate = new Promise(resolve => { release = resolve; });
  const requestSeen = new Promise(resolve => { requestStarted = resolve; });
  await page.route('**/api/chat', async route => { calls++; requestStarted(); await gate; await route.fulfill({json: {}}); });
  const input = page.locator('#chat-input');
  await input.fill('   '); await input.press('Enter');
  assert.equal(calls, 0);
  // Starter ideas remain editable drafts: selecting one must never call Muse.
  assert.equal(await page.locator('.starter-card').count(), 3);
  await page.locator('.starter-card').first().click();
  assert((await input.inputValue()).includes('arcade game'));
  assert.equal(await input.evaluate(node => node === document.activeElement), true);
  assert.equal(calls, 0);
  await input.fill('First line'); await input.press('End'); await input.press('Shift+Enter'); await input.press('b');
  assert.equal(await input.inputValue(), 'First line\nb'); assert.equal(calls, 0);
  // IME confirmation and held-key repeats must not send a draft.
  await input.evaluate(node => {
    node.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', isComposing: true, bubbles: true, cancelable: true}));
    node.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', keyCode: 229, bubbles: true, cancelable: true}));
    node.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', repeat: true, bubbles: true, cancelable: true}));
    for (const modifier of ['ctrlKey', 'altKey', 'metaKey']) node.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', [modifier]: true, bubbles: true, cancelable: true}));
  });
  assert.equal(calls, 0);
  await input.fill('SYNTHETIC keyboard-only submission'); await input.press('Enter');
  await page.waitForFunction(() => document.querySelector('#chat-send').disabled);
  await page.locator('#agent-progress .ember-dots').waitFor();
  assert.equal(await page.locator('#status').textContent(), 'Working');
  await requestSeen;
  await input.press('Enter');
  assert.equal(calls, 1, 'An active request cannot be submitted twice');
  assert.equal(await page.locator('#chat-send').getAttribute('type'), 'submit');
  await page.screenshot({path: path.join(process.env.EMBER_BROWSER_OUTPUT, 'working-status.png')});
  release(); await page.locator('#chat-send:not([disabled])').waitFor();
  await page.unroute('**/api/chat');

  // Current task and actual stages are shown; stopped work has no animated dots.
  await page.evaluate(() => {
    const now = new Date().toISOString();
    const activity = {turn_id: 'synthetic-status', state: 'active', phase: 'muse_working', title: 'Muse is working on your request', started_at: now, updated_at: now, events: []};
    renderAgentActivity({...lastState, project_plan: {selected_task: 'test-task', tasks: [{id: 'test-task', title: 'Courier delivery route'}]}, chat_activity: activity});
  });
  assert((await page.locator('#agent-progress').textContent()).includes('Current task · Courier delivery route'));
  await page.evaluate(() => { const node=document.querySelector('#agent-progress .ember-status');node.dataset.retained='yes'; });
  await page.evaluate(() => renderAgentActivity({...lastState, project_plan: {selected_task: 'test-task', tasks: [{id: 'test-task', title: 'Courier delivery route'}]}, chat_activity: {turn_id: 'synthetic-status', state: 'active', phase: 'muse_working', title: 'Muse is working on your request', started_at: new Date(Date.now()-30000).toISOString(), updated_at: new Date(Date.now()-25000).toISOString(), response_chars: 42, events: []}}));
  assert.equal(await page.locator('#agent-progress .ember-status').getAttribute('data-retained'), 'yes');
  assert((await page.locator('#agent-elapsed').textContent()).startsWith('30s'));
  assert((await page.locator('#agent-received').textContent()).includes('42 response characters'));
  assert(await page.locator('#agent-waiting').isVisible());
  await page.evaluate(() => renderAgentActivity({...lastState, chat_activity: {
    turn_id: 'synthetic-status', state: 'active', phase: 'muse_working', title: 'Muse is working on your request',
    started_at: new Date(Date.now()-240000).toISOString(), updated_at: new Date().toISOString(),
    response_chars: 0, call_elapsed_seconds: 240, events: [],
    execution: {profile: 'deep', label: 'Extended investigation and implementation', timeout_seconds: 1800,
      reasoning_effort: 'high', reason: 'A previous attempt failed verification'}
  }}));
  const extendedStatus=await page.locator('#agent-progress').textContent();
  assert(extendedStatus.includes('up to 30m for this request'));
  assert(extendedStatus.includes('A previous attempt failed verification'));
  assert(extendedStatus.includes('not a completion estimate'));
  assert(await page.locator('#agent-waiting').isVisible(), 'Host heartbeats must not hide a quiet provider');
  // Real stage titles and recent observed steps stay visible without opening technical history.
  let resumePolling;
  const pollingGate=new Promise(resolve=>{resumePolling=resolve});
  await page.route('**/api/state', async route => { await pollingGate; await route.continue(); });
  await page.evaluate(() => {
    const phases=['saved','context','muse_working','validating','testing_before','testing_candidate','visual_review'];
    const titles=['Message saved','Reading your game','Muse is working on your request','Checking the response','Testing the current game for comparison','Trying the proposed game on desktop and mobile','Muse is inspecting the actual game screenshots'];
    window.syntheticActivity={turn_id:'synthetic-visual-review',state:'active',phase:'visual_review',title:titles.at(-1),
      detail:'Muse is reviewing captured game images and test results against your request.',
      started_at:new Date(Date.now()-90000).toISOString(),updated_at:new Date().toISOString(),
      events:phases.map((phase,i)=>({phase,title:titles[i],at:new Date(Date.now()-(phases.length-i)*25000).toISOString()}))};
    renderAgentActivity({...lastState,chat_activity:window.syntheticActivity});
  });
  assert((await page.locator('#agent-progress .ember-status-title').textContent()).startsWith('Muse is inspecting the actual game screenshots'));
  assert(await page.locator('.agent-step-detail').isVisible());
  assert.equal(await page.locator('.agent-timeline li').count(),5);
  assert.equal(await page.locator('.agent-timeline [aria-current="step"]').count(),1);
  assert.equal(await page.locator('#agent-progress details').evaluate(n=>n.open),false);
  assert((await page.locator('#agent-waiting').textContent()).includes('screenshot review'));
  for(const width of [390,1500]){
    await page.setViewportSize({width,height:1000});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.locator('#agent-progress').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'request-steps-'+width+'.png')});
  }
  await page.locator('#agent-progress summary').click();
  await page.evaluate(()=>renderAgentActivity({...lastState,chat_activity:{...window.syntheticActivity,detail:'Checking the captured movement poses against the request.'}}));
  assert.equal(await page.locator('#agent-progress details').evaluate(n=>n.open),true);
  assert((await page.locator('.agent-step-detail').textContent()).includes('movement poses'));
  await page.evaluate(() => renderAgentActivity({...lastState, chat_activity: {turn_id: 'synthetic-status', state: 'interrupted', phase: 'muse_working', started_at: new Date().toISOString(), updated_at: new Date().toISOString(), events: []}}));
  assert.equal(await page.locator('#agent-progress .ember-dots').count(), 0);
  assert((await page.locator('#agent-progress').textContent()).includes('Request stopped') || (await page.locator('#agent-progress').textContent()).includes('worker stopped'));
  assert.equal(await page.locator('.agent-timeline [aria-current="step"]').count(),0);
  await require('./task_review_ui_check')(page,view);
  resumePolling();await page.unrouteAll({behavior:'wait'});
  await page.evaluate(() => renderAgentActivity(lastState));
  // Previously generated batches advance the game plan together, rather than
  // selecting one atlas for a standalone workshop.
  let artworkPlanText;
  await page.route('**/api/chat',async route=>{artworkPlanText=route.request().postDataJSON().text;await route.fulfill({json:{}})});
  await page.evaluate(()=>{
    const original=renderArtworkPreview;renderArtworkPreview=()=>{};
    try{
      const refs=['a'.repeat(64),'b'.repeat(64)];
      const message={id:'synthetic-existing-art',role:'assistant',text:'SYNTHETIC already generated artwork',created_at:new Date().toISOString(),
        image_batch:{completed:2,total:2,items:refs.map((ref,i)=>({request:{specification:{id:'art-'+i,display_name:'Original art '+i}},generation:{status:'generated',asset_ref:ref}}))}};
      renderChat({...lastState,project_brief:{...lastState.project_brief,fields:{...lastState.project_brief.fields,goal:'A turn-based snowball duel'}},messages:[message]});
    }finally{renderArtworkPreview=original;}
  });
  await page.getByRole('button',{name:'Use these assets in the game plan',exact:true}).click();
  await page.locator('#chat-send:not([disabled])').waitFor();
  assert(artworkPlanText.includes('a'.repeat(64))&&artworkPlanText.includes('b'.repeat(64)));
  assert(artworkPlanText.includes('complete first playable game'));
  assert(artworkPlanText.includes('Prepare the plan for approval before implementation'));
  await page.unroute('**/api/chat');
  for (const width of [390, 768, 1500]) {
    await page.setViewportSize({width, height: 1000});
    for (const id of ['assets', 'library', 'chat']) {
      await view(id); assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    }
  }
  await input.fill('');
};
