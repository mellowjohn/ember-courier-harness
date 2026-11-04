// Reuse the owned offline browser fixture; no provider calls or user sessions.
const assert = require('node:assert/strict');
const path = require('node:path');

module.exports = async function checkLibrary(page, view) {
  await page.locator('#chat-send:not([disabled])').waitFor();
  await page.evaluate(() => {
    const frame = prototypeFrame(document.body, 'Preview isolation test');
    frame.id = 'preview-isolation-test';
    frame.srcdoc = previewDocument(`<body><script>
      let canReadApp = true;
      try { void parent.sessionStorage.length; } catch { canReadApp = false; }
      document.body.dataset.isolated = String(!canReadApp && typeof RTCPeerConnection === 'undefined' &&
        !Object.getOwnPropertyDescriptor(window, 'RTCPeerConnection').configurable);
    </script></body>`);
  });
  await page.frameLocator('#preview-isolation-test').locator('body[data-isolated=true]').waitFor({state:'attached'});
  await page.locator('#preview-isolation-test').evaluate(frame => frame.remove());
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
  await page.locator('#agent-progress .agent-live-dot').waitFor();
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
  assert.equal(await page.locator('#agent-progress .agent-task').textContent(),'Courier delivery route');
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
  await page.evaluate(()=>{
    const message={id:'synthetic-plan-draft',role:'assistant',model:'Muse',created_at:new Date().toISOString()};
    const text=[
      'Here is a first draft for Courier Dash.', '',
      'Concept: Carry a parcel across a windy island.', '',
      '**Core loop:** Pick up the parcel, dodge gusts, reach the lighthouse.', '',
      '### Controls / platform [Proposed]', 'Keyboard or touch.', '',
      'First playable:', '- One island route', '- A delivery and restart screen', '',
      'Success criteria: The player can complete a delivery.', '',
      'This is just a draft. Tell me what you would change. <img src=x>'
    ].join('\n');
    renderChat({...lastState,messages:[{...message,id:'plain-reply',text:'What kind of game would you like to make?'},{...message,text}]});
  });
  const draft=page.locator('.message.plan-draft');
  await draft.getByRole('heading',{name:'Game plan draft',exact:true}).waitFor();
  assert.deepEqual(await draft.locator('h4').allTextContents(),['Concept','Core loop','Controls / platform','First playable','Success criteria']);
  assert.deepEqual(await draft.getByRole('listitem').allTextContents(),['One island route','A delivery and restart screen']);
  assert.equal(await draft.locator('.draft-note').textContent(),'[Proposed]');
  assert((await draft.locator('.draft-closing').textContent()).includes('<img src=x>'));
  assert.equal(await draft.locator('img, button').count(),0);
  await page.locator('.message.assistant:not(.plan-draft)').getByText('What kind of game would you like to make?',{exact:true}).waitFor();
  await page.waitForFunction(()=>document.querySelector('.draft-heading').getBoundingClientRect().top>=document.querySelector('#conversation-history').getBoundingClientRect().top);
  for (const width of [1500,390]) {
    await page.setViewportSize({width,height:900});
    assert(await draft.evaluate(node=>node.scrollWidth<=node.clientWidth));
    await page.locator('#chat').screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'plan-draft-'+width+'.png')});
  }
  await page.setViewportSize({width:1500,height:1000});
  await page.evaluate(()=>renderChat(lastState));
  // A real-length task with asset references stays compact on desktop/mobile.
  await page.evaluate(()=>{
    const title='Complete first playable SNOWBALL SHOWDOWN duel in one snowy town square dusk arena reusing '+
      ['kid-thrower','frosty-rival','snowball-fx','backdrop'].map((name,i)=>name+' '+String(i+1).repeat(64)).join(', ')+
      ': sequential alternating turns, Throw/Big Throw/Dodge/Scoop, HP and ammo HUD, win/lose/restart, keyboard and touch controls';
    const now=new Date().toISOString();
    window.longTaskActivity={turn_id:'synthetic-long-task',kind:'plan_build',plan_start:{title},state:'active',phase:'muse_working',
      title:'Muse is working on your request',started_at:new Date(Date.now()-32000).toISOString(),updated_at:now,
      read_files:['app.js','game.js','index.html'],events:[],execution:{label:'Implementation',reason:'Creating or changing game code',timeout_seconds:900}};
    renderAgentActivity({...lastState,chat_activity:longTaskActivity});
  });
  assert.equal(await page.locator('#agent-progress .ember-status-context').count(),0);
  assert.equal(await page.locator('#agent-progress .agent-task').count(),1);
  assert((await page.locator('#agent-progress .agent-task').textContent()).length<=97);
  assert(!/[a-f0-9]{64}/i.test(await page.locator('#agent-progress').textContent()));
  assert.equal(await page.locator('#agent-progress .ember-dots').count(),0);
  assert.equal(await page.locator('#plan-build-notice').textContent(),'Plan approved');
  assert.equal(await page.locator('#agent-progress .agent-history').evaluate(n=>n.open),false);
  assert.deepEqual(await page.locator('#agent-progress [data-kind="source"] .agent-file').allTextContents(),['app.js','game.js','index.html']);
  for(const width of [390,1500]){
    await page.setViewportSize({width,height:1000});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    assert((await page.locator('#agent-progress').boundingBox()).height<480);
    await page.locator('#agent-progress').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'compact-progress-'+width+'.png')});
    await page.locator('#agent-progress').screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'progress-card-'+width+'.png')});
  }
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await page.locator('.agent-live-dot').evaluate(n=>getComputedStyle(n).animationName),'none');
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.evaluate(() => {
    const phases=['saved','context','muse_working','validating','testing_before','testing_candidate','visual_review'];
    const titles=['Message saved','Reading your game','Muse is working on your request','Checking the response','Testing the current game for comparison','Trying the proposed game on desktop and mobile','Muse is inspecting the actual game screenshots'];
    window.syntheticActivity={turn_id:'synthetic-visual-review',state:'active',phase:'visual_review',title:titles.at(-1),
      detail:'Muse is reviewing captured game images and test results against your request.',
      started_at:new Date(Date.now()-90000).toISOString(),updated_at:new Date().toISOString(),
      events:phases.map((phase,i)=>({phase,title:titles[i],at:new Date(Date.now()-(phases.length-i)*25000).toISOString()}))};
    renderAgentActivity({...lastState,chat_activity:window.syntheticActivity});
  });
  assert.equal(await page.locator('#agent-progress .ember-status-title').textContent(),'Reviewing screenshots');
  assert(await page.locator('.agent-step-detail').isHidden());
  assert.equal(await page.locator('.agent-timeline li').count(),7);
  assert.equal(await page.locator('.agent-timeline [aria-current="step"]').count(),1);
  assert.equal(await page.locator('#agent-progress details').evaluate(n=>n.open),false);
  assert((await page.locator('#agent-waiting').textContent()).includes('screenshots'));
  for(const width of [390,1500]){
    await page.setViewportSize({width,height:1000});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.locator('#agent-progress').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'request-steps-'+width+'.png')});
  }
  await page.locator('#agent-progress .agent-history > summary').click();
  await page.evaluate(()=>renderAgentActivity({...lastState,chat_activity:{...window.syntheticActivity,detail:'Checking the captured movement poses against the request.'}}));
  assert.equal(await page.locator('#agent-progress details').evaluate(n=>n.open),true);
  assert((await page.locator('.agent-step-detail').textContent()).includes('movement poses'));
  await page.evaluate(() => renderAgentActivity({...lastState, chat_activity: {turn_id: 'synthetic-status', state: 'interrupted', phase: 'muse_working', started_at: new Date().toISOString(), updated_at: new Date().toISOString(), events: []}}));
  assert.equal(await page.locator('#agent-progress .ember-dots').count(), 0);
  assert((await page.locator('#agent-progress').textContent()).includes('Request interrupted'));
  assert.equal(await page.locator('#agent-progress .agent-live-dot').count(),0);
  assert.equal(await page.locator('.agent-timeline [aria-current="step"]').count(),0);
  await require('./task_review_ui_check')(page,view);
  // Polling must never turn an unfinished candidate into a ready review, and
  // a code-only fix must not re-present every retained artwork entity.
  await page.evaluate(()=>{
    const request=structuredClone(lastState.requests.find(r=>r.payload.body.build));
    request.ref='d'.repeat(64);request.decision=null;
    const build=request.payload.body.build;
    build.turn_id='synthetic-diff-review';build.title='SYNTHETIC facing-only change';
    build.files=[{name:'game.js',before_sha256:'before',after_sha256:'after'}];
    build.diff='--- game.js\n+++ game.js\n-flipX:true\n+flipX:false';
    build.sprite_plan={version:1,entities:['player','frosty','snowball','backdrop'].map(id=>({id}))};
    build.sprite_changes=[];request.payload.body.asset_actions=[];
    const now=new Date().toISOString();
    window.diffReviewState={...lastState,requests:[request],chat_activity:{turn_id:build.turn_id,state:'active',phase:'visual_review',
      title:'Inspecting game screenshots',started_at:now,updated_at:now,events:[],read_files:['index.html','game.js'],proposed_files:['game.js']},
      build:{...lastState.build,requests:[request],quality_check:{request_ref:request.ref,status:'running',issues:[]}}};
    renderReview(diffReviewState);renderAgentActivity(diffReviewState);
  });
  assert.equal(await page.locator('#review .brand').textContent(),'CHECKING PROPOSED CHANGES');
  assert.equal(await page.locator('#review .decision').count(),0);
  assert.equal(await page.locator('#review .artwork-preview').count(),0);
  assert.deepEqual(await page.locator('#agent-progress [data-kind="source"] .agent-file').allTextContents(),['index.html','game.js']);
  assert.deepEqual(await page.locator('#agent-progress [data-kind="edits"] .agent-file').allTextContents(),['game.js']);
  await page.evaluate(()=>{
    diffReviewState.chat_activity={...diffReviewState.chat_activity,phase:'receiving',file_changes:[
      {path:'game.js',new:false,added:1,removed:1,lines:['@@ -1 +1 @@','-flipX:true','+flipX:false']},
      {path:'style.css',new:true,added:1,removed:0,lines:['+body {}']},
    ]};
    renderAgentActivity(diffReviewState);
  });
  const liveDiff=page.getByRole('region',{name:'Draft file changes'});
  const editedFile=liveDiff.locator('details[data-diff-path="game.js"]');
  assert.deepEqual(await liveDiff.locator('summary .agent-diff-kind').allTextContents(),['Edited','New']);
  assert.deepEqual(await liveDiff.locator('summary .agent-diff-added').allTextContents(),['+1','+1']);
  assert.deepEqual(await liveDiff.locator('summary .agent-diff-removed').allTextContents(),['-1','-0']);
  await editedFile.locator('summary').click();
  await editedFile.locator('pre .agent-diff-removed').getByText('-flipX:true',{exact:true}).waitFor();
  await page.evaluate(()=>{
    diffReviewState.chat_activity.file_changes_exact=true;
    diffReviewState.chat_activity.phase='visual_review';
    renderAgentActivity(diffReviewState);
  });
  const proposedFile=page.getByRole('region',{name:'Proposed file changes'}).locator('details[data-diff-path="game.js"]');
  assert.equal(await proposedFile.evaluate(node=>node.open),true);
  await proposedFile.locator('pre .agent-diff-added').getByText('+flipX:false',{exact:true}).waitFor();
  await page.evaluate(()=>{
    diffReviewState.chat_activity={...diffReviewState.chat_activity,state:'complete',phase:'awaiting_review'};
    diffReviewState.build.quality_check={...diffReviewState.build.quality_check,status:'needs_changes',issues:['Facing fix is not proven.']};
    renderReview(diffReviewState);
  });
  assert.equal(await page.locator('#review .brand').textContent(),'CHANGES NEED ATTENTION');
  await page.getByText('Artwork unchanged · 4 existing entities retained',{exact:true}).waitFor();
  assert.equal(await page.locator('#review .artwork-preview').count(),0);
  assert.equal(await page.locator('#review details').filter({has:page.locator('summary',{hasText:'View code changes'})}).evaluate(n=>n.open),true);
  await page.evaluate(()=>{
    renderAgentActivity({...diffReviewState,chat_activity:{...diffReviewState.chat_activity,state:'active',phase:'image_generating',generating_asset:'Snowy backdrop',proposed_files:[]}});
  });
  assert.deepEqual(await page.locator('#agent-progress [data-kind="artwork"] .agent-file').allTextContents(),['Snowy backdrop']);
  await page.evaluate(()=>{current='';renderReview(lastState);renderAgentActivity(lastState);delete window.diffReviewState;});
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
