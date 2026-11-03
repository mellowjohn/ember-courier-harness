// UI-only synthetic evidence fixtures; normal workflow evidence is checked separately.
const assert = require('node:assert/strict');
const path = require('node:path');

module.exports = async function checkTaskReview(page, view) {
  await view('chat');
  const requests=[];
  await page.route('**/api/task-preview?*',async route=>{
    requests.push(new URL(route.request().url()));
    await route.fulfill({json:{html:'<!doctype html><button>Inspect retained candidate</button>',index:2}});
  });
  await page.route('**/api/task-image?*',async route=>{
    requests.push(new URL(route.request().url()));
    await route.fulfill({status:409,json:{error:'Retained capture changed; evidence must be inspected'}});
  });
  await page.evaluate(()=>{
    const root=document.createElement('article');root.id='synthetic-task-review';root.className='panel';document.querySelector('#task-run-list').append(root);
    const observations={viewports:[{name:'desktop',screenshot:'desktop.png',observations:['Synthetic script startup error'],after:{overflow:false}},{name:'mobile',screenshot:'mobile.png',observations:[],after:{overflow:true}}],gameplay:{scenarios:[{name:'Restart retains controls',viewport:'mobile',outcome:'failed',steps:[{status:'failed',observed:'Restart button did not respond'}]}]}};
    const report={index:2,qualified:false,observations,verdict:{summary:'The HUD is clearer, but restart is broken.',issues:['Restore the mobile restart handler.'],criteria:[{id:'presentation',status:'not_met',reason:'Instructions cover the restart control.',evidence:[]},{id:'interaction',status:'not_observed',reason:'Repeated play was not observed.',evidence:[]},{id:'human-experience',status:'not_observed',reason:'Owner playtest pending.',evidence:[]}]},quality:{blockers:['presentation: review both desktop and mobile captures.']},comparison:{assessment:{improved:false,improvement:'The requested reset improvement was not established.',losses:['The mobile restart path regressed.']},baseline_observations:observations,blockers:['Requested interaction improvement lacks evidence.']}};
    window.syntheticTaskReviewRun={id:'synthetic-review',goal:'Make restart clear and reliable',status:'awaiting_decision',attempts:{blocked:true,attempts:[{},{},{}]},quality:{criteria:[{id:'presentation',method:'visual',expectation:'Restart must remain readable.'},{id:'interaction',method:'gameplay',expectation:'A second playthrough works.'},{id:'human-experience',method:'human',expectation:'Play it.'}]},comparison:{baseline_status:'captured'},reports:[{...report,index:1},report]};
    renderTaskResult(activeSession.id,window.syntheticTaskReviewRun,root);
    renderCoverageReview({task_expectation:'Make restart clear and reliable',paths:[{id:'reset',label:'Restart / reset',status:'missing',basis:'declared_intent',suggestion:'Click restart, then assert the initial score.'}],missing:['reset'],unsupported:['Human feel'],observation_limit:'Visible values are reported by the game, not independent physics proof.'},root);
  });
  const root=page.locator('#synthetic-task-review');
  for(const text of ['Changes are blocked from recommendation','Broken behavior:','Browser problem: desktop: Synthetic script startup error','Broken layout: mobile:','Visual judgment:','Unavailable evidence:','Evidence blocker:','Next change to discuss:','3 allocated in the attempt history','attempt allowance is exhausted','Human playtest pending:','Reported loss:','Missing check','Suggested check:']){
    assert((await root.textContent()).includes(text),text);
  }
  assert.equal(await root.getByRole('button',{name:/Approve|Accept|Retry|Start/}).count(),0,'Review rendering cannot approve, accept or retry work');
  await root.getByText('Play and inspect retained attempts (2)',{exact:true}).click();
  await root.getByRole('button',{name:'Play task attempt 2',exact:true}).click();
  assert.equal(await root.locator('iframe').getAttribute('sandbox'),'allow-scripts');
  await root.locator('iframe').contentFrame().getByRole('button',{name:'Inspect retained candidate'}).waitFor();
  await root.getByRole('button',{name:'View task screenshots · attempt 2',exact:true}).click();
  await root.getByText('Evidence unavailable: Retained capture changed; evidence must be inspected',{exact:true}).waitFor();
  assert(requests.some(url=>url.pathname==='/api/task-image'&&url.searchParams.get('stage')==='baseline'&&url.searchParams.get('index')==='2'));
  assert(requests.some(url=>url.pathname==='/api/task-preview'&&url.searchParams.get('index')==='2'));
  for(const width of [390,1500]){
    await page.setViewportSize({width,height:1000});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await root.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'task-quality-blockers-'+width+'.png')});
  }
  await page.evaluate(()=>{
    const root=document.querySelector('#synthetic-task-review');root.replaceChildren();
    renderTaskResult(activeSession.id,{id:'synthetic-empty',goal:'Create the first game',reports:[{index:1,qualified:true,verdict:{summary:'Synthetic initial candidate',issues:[]},observations:{viewports:[]}}],comparison:{baseline_status:'no_playable_baseline'}},root);
  });
  await root.getByText('No playable starting game was available for a before/after comparison.',{exact:true}).waitFor();
  await root.getByText('Checks support review · your playtest is still pending',{exact:true}).waitFor();
  await page.evaluate(()=>document.querySelector('#synthetic-task-review').remove());
  // Changing elapsed progress and unrelated UI busy state must retain live play.
  await page.evaluate(()=>renderProjectPlan({...lastState,project_plan:{reason:'Synthetic task UI review',tasks:[],active:false},task_runs:[{...window.syntheticTaskReviewRun,status:'running',phase:'Synthetic worker elapsed 1s'}]}));
  const retained=page.locator('[data-task-run="synthetic-review"]');
  await retained.getByText('Play and inspect retained attempts (2)',{exact:true}).click();
  await retained.getByRole('button',{name:'Play task attempt 2',exact:true}).click();
  await retained.locator('iframe').contentFrame().getByRole('button',{name:'Inspect retained candidate'}).waitFor();
  await retained.locator('iframe').contentFrame().locator('body').evaluate(node=>node.dataset.retainedPlay='yes');
  await page.evaluate(()=>{window.retainedTaskIframe=document.querySelector('[data-task-run="synthetic-review"] iframe');busy=true;renderProjectPlan({...lastState,project_plan:{reason:'Synthetic task UI review',tasks:[],active:false},task_runs:[{...window.syntheticTaskReviewRun,status:'running',phase:'Synthetic worker elapsed 2s'}]});busy=false;});
  assert(await page.evaluate(()=>window.retainedTaskIframe===document.querySelector('[data-task-run="synthetic-review"] iframe')));
  assert.equal(await retained.locator('iframe').contentFrame().locator('body').getAttribute('data-retained-play'),'yes','Polling cannot reset candidate play state');
  await page.evaluate(()=>{renderProjectPlan({...lastState,project_plan:null});delete window.retainedTaskIframe;delete window.syntheticTaskReviewRun;});
  assert.equal(await page.locator('#task-run-list [data-task-run]').count(),0,'Unavailable planning state cannot display another session’s retained task cards');
  await page.evaluate(()=>renderProjectPlan(lastState));
  await page.unroute('**/api/task-preview?*');await page.unroute('**/api/task-image?*');
  await view('playtest');
  await page.evaluate(()=>{window.savedCoverageDraft=structuredClone(gameplayDraft);gameplayDraft.plan.scenarios[0].coverage=[];gameplayEditor();document.querySelector('#gameplay-form').hidden=false;});
  const coverage=page.locator('.scenario-coverage').first();
  await coverage.getByRole('checkbox',{name:'Restart / reset',exact:true}).check();
  assert(await page.evaluate(()=>gameplayDraft.dirty&&gameplayDraft.plan.scenarios[0].coverage.includes('reset')));
  assert((await coverage.textContent()).includes('labels alone do not verify behavior'));
  await page.evaluate(()=>{Object.assign(gameplayDraft,window.savedCoverageDraft);delete window.savedCoverageDraft;gameplayEditor();document.querySelector('#gameplay-form').hidden=true;gameplayButtons(lastState)});
  await view('chat');
};
