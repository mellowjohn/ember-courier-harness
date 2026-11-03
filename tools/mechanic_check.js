const assert=require('node:assert/strict'),path=require('node:path');
const {chromium}=require(process.env.EMBER_PLAYWRIGHT_MODULE);
(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.EMBER_BROWSER_EXECUTABLE}),errors=[];
try{
 const page=await browser.newPage({viewport:{width:1500,height:1000},hasTouch:true});page.setDefaultTimeout(60000);page.on('pageerror',error=>errors.push(error.message));
 const view=async id=>{await page.waitForFunction(()=>!busy&&!sending&&!gameplayDraft?.saving&&!gameplayDraft?.running);return require('./workspace_browser').view(page,id);},shot=name=>page.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,name+'.png')});
 const version=n=>page.getByText('Version '+n+' · Approved and ready to play',{exact:true}).waitFor();
 const preview=page.frameLocator('iframe[title="Approved browser prototype"]');
 const openRecipes=async()=>{await view('plan');await page.locator('#mechanic-recipes').scrollIntoViewIfNeeded();};
 const compare=async()=>{await view('chat');await page.getByRole('button',{name:'Check proposed changes',exact:true}).click();await page.getByText('Proposed gameplay checks passed',{exact:true}).waitFor({timeout:180000});};
 const currentChecks=async(passed)=>{await view('playtest');await page.getByRole('button',{name:'Run gameplay checks',exact:true}).click();await page.waitForFunction(()=>!gameplayDraft.running&&/Listed gameplay checks passed|Gameplay checks found a problem|Checks stopped:/.test(document.querySelector('#gameplay-message')?.textContent||''),{timeout:120000});const message=await page.locator('#gameplay-message').textContent();assert(!message.startsWith('Checks stopped:'),message);await page.waitForFunction(expected=>document.querySelector('#gameplay-reports')?.textContent.includes(expected),passed?'Current game · Listed checks passed':'Current game · Gameplay checks failed',{timeout:20000});};
 const referenceChecks=async()=>{await openRecipes();const previous=await page.evaluate(()=>lastState.gameplay_plan.revision);await page.getByRole('button',{name:'Use reference gameplay checks',exact:true}).click();await page.waitForFunction(revision=>lastState.gameplay_plan.revision>revision&&gameplayDraft?.revision===lastState.gameplay_plan.revision&&!gameplayDraft.dirty&&JSON.stringify(gameplayDraft.plan)===JSON.stringify(lastState.gameplay_plan.plan),previous,{timeout:60000});};
 const download=async(label,file)=>{await view('report');const pending=page.waitForEvent('download');await page.getByRole('button',{name:label,exact:true}).click();const item=await pending;await item.saveAs(path.join(process.env.EMBER_BROWSER_OUTPUT,file));};
 await require('./workspace_browser').stubPlanBuild(page);
 await page.goto(process.env.EMBER_BROWSER_URL+'#'+process.env.EMBER_BROWSER_TOKEN);
 await page.getByRole('button',{name:'Approve project plan',exact:true}).click();
 await openRecipes();await page.getByRole('button',{name:'Review reference platformer',exact:true}).click();
 await page.getByRole('heading',{name:'Original movement and jumping reference',exact:true}).waitFor();
 await page.getByText('Starting rules: instant movement and no jump assistance.',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Approve & play',exact:true}).click();await version(1);
 await referenceChecks();await currentChecks(true);
 await openRecipes();await page.locator('#mechanic-choice').selectOption('movement-smoothing');
 await page.locator('#mechanic-form input[name="max_speed"]').fill('999');
 await page.getByRole('button',{name:'Review recipe changes',exact:true}).click();
 assert(!(await page.locator('#mechanic-form input[name="max_speed"]').evaluate(input=>input.validity.valid)));
 await page.locator('#mechanic-form input[name="max_speed"]').fill('300');
 await page.getByRole('button',{name:'Review recipe changes',exact:true}).click();
 await page.getByRole('heading',{name:'Mechanic recipe: Smoother movement',exact:true}).waitFor();
 await page.getByText('Maximum speed: 300 px/s',{exact:true}).waitFor();await shot('movement-review');
 await page.reload();await page.getByRole('heading',{name:'Mechanic recipe: Smoother movement',exact:true}).waitFor();
 await page.getByText('Maximum speed: 300 px/s',{exact:true}).waitFor();assert.equal(await page.locator('.build-version').textContent(),'Version 1 · Approved and ready to play');
 await compare();await page.getByRole('button',{name:'Approve & play',exact:true}).click();await version(2);
 // Author a fixed, tick-based formerly missed jump through the existing editor.
 await view('playtest');await page.locator('#gameplay-edit').click();
 while(await page.getByRole('button',{name:'Remove scenario',exact:true}).count())await page.getByRole('button',{name:'Remove scenario',exact:true}).first().click();
 await page.getByLabel('Test plan name',{exact:true}).fill('Inclusive 100 ms edge jump');
 await page.getByRole('button',{name:'Add scenario',exact:true}).click();
 let box=page.locator('#gameplay-editor > fieldset').last();await box.getByLabel('Scenario name',{exact:true}).fill('Formerly missed edge jump');
 const steps=[{action:'click',selector:'summary'},{action:'click',selector:'#scenario-coyote'},{action:'click',selector:'#step-twelve'},{action:'click',selector:'#jump'},{action:'click',selector:'#step-one'},{action:'text',selector:'#jump-count',value:'1'}];
 for(const [index,step] of steps.entries()){if(index)await box.getByRole('button',{name:'Add step',exact:true}).click();const row=box.locator(':scope > .panel').nth(index);await row.getByLabel('Action',{exact:true}).selectOption(step.action);await row.getByLabel('Target',{exact:true}).fill(step.selector);if(step.value!==undefined)await row.getByLabel('Expected text',{exact:true}).fill(step.value);}
 await page.getByRole('button',{name:'Save gameplay plan',exact:true}).click();await page.getByText('Plan saved · Frozen into future overnight scopes',{exact:true}).waitFor();await currentChecks(false);await shot('missed-jump-baseline');
 // A valid but ineffective zero-window recipe must fail the required behavior,
 // retain its review evidence, and leave the approved game untouched.
 await openRecipes();await page.locator('#mechanic-choice').selectOption('forgiving-jumps');await page.locator('#mechanic-form input[name="coyote_ms"]').fill('0');await page.locator('#mechanic-form input[name="jump_buffer_ms"]').fill('0');
 await page.getByRole('button',{name:'Review recipe changes',exact:true}).click();await page.getByRole('heading',{name:'Mechanic recipe: More forgiving jumps',exact:true}).waitFor();
 await view('chat');await page.getByRole('button',{name:'Check proposed changes',exact:true}).click();await page.getByText('Proposed gameplay checks failed',{exact:true}).waitFor({timeout:180000});assert.equal(await page.locator('.build-version').textContent(),'Version 2 · Approved and ready to play');await shot('rejected-zero-window');
 await page.getByRole('button',{name:'Discard',exact:true}).click();await openRecipes();await page.locator('#mechanic-choice').selectOption('forgiving-jumps');await page.locator('#mechanic-form input[name="coyote_ms"]').fill('100');await page.locator('#mechanic-form input[name="jump_buffer_ms"]').fill('100');
 await page.getByRole('button',{name:'Review recipe changes',exact:true}).click();await page.getByRole('heading',{name:'Mechanic recipe: More forgiving jumps',exact:true}).waitFor();
 await page.getByText('Grace after an edge: 100 ms',{exact:true}).waitFor();await page.reload();await page.getByText('Grace after an edge: 100 ms',{exact:true}).waitFor();await compare();await page.getByText('Fixed',{exact:true}).waitFor();await shot('jump-before-after');
 await page.getByRole('button',{name:'Approve & play',exact:true}).click();await version(3);
 await preview.locator('#scene').focus();await page.keyboard.down('ArrowRight');await page.waitForTimeout(300);await page.keyboard.up('ArrowRight');assert(Number(await preview.locator('#position').textContent())>41);await page.keyboard.press('Space');await preview.locator('#jump-count').getByText('1',{exact:true}).waitFor();await preview.locator('#restart').click();
 await page.setViewportSize({width:390,height:844});await preview.locator('#jump').tap();await preview.locator('#jump-count').getByText('1',{exact:true}).waitFor();await preview.locator('#restart').tap();await preview.locator('#jump-count').getByText('0',{exact:true}).waitFor();assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await shot('mechanics-mobile');await page.setViewportSize({width:1500,height:1000});
 // Real touch hold/release and a real focus transfer exercise the same held
 // input cleanup as keyboard play; timing-window proof remains tick-based.
 await page.setViewportSize({width:390,height:844});await preview.locator('#right').evaluate(button=>button.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'}));const rect=await preview.locator('#right').boundingBox(),cdp=await page.context().newCDPSession(page);assert(rect&&rect.x>=0&&rect.y>=0&&rect.x+rect.width<=390&&rect.y+rect.height<=844,'Touch movement control must be visible');
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:rect.x+rect.width/2,y:rect.y+rect.height/2,id:7,radiusX:1,radiusY:1,force:1}]});await page.waitForTimeout(250);await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await preview.locator('#velocity').getByText('0',{exact:true}).waitFor();assert(Number(await preview.locator('#position').textContent())>41);await cdp.detach();
 await preview.locator('#restart').tap();await preview.locator('#scene').focus();await page.keyboard.down('ArrowRight');await page.waitForTimeout(150);await page.locator('#chat-input').evaluate(input=>input.focus({preventScroll:true}));await preview.locator('#velocity').getByText('0',{exact:true}).waitFor();await page.keyboard.up('ArrowRight');const stopped=await preview.locator('#position').textContent();await page.waitForTimeout(150);assert.equal(await preview.locator('#position').textContent(),stopped);await page.setViewportSize({width:1500,height:1000});
 await referenceChecks();await currentChecks(true);await download('Download game ZIP','game.zip');
 // Both checked historical settings are restored forward, preserving all receipts.
 const restore=async(number,next)=>{await view('report');const summary=page.locator('summary').filter({hasText:/^Saved versions \(/}).first(),details=summary.locator('..');if(!await details.evaluate(node=>node.open))await summary.click();await details.getByRole('button',{name:'Review restore of version '+number,exact:true}).click();await compare();await page.getByRole('button',{name:'Approve restore & play',exact:true}).click();await version(next);};
 await restore(2,4);await restore(3,5);await currentChecks(true);
 await view('plan');await page.locator('[data-task-id="task-1"]').getByRole('button',{name:'Accept task outcome',exact:true}).click();await page.locator('[data-task-id="task-1"]').getByText('Outcome accepted by you',{exact:true}).waitFor();await download('Download project handoff','handoff.zip');
 await page.reload();await version(5);await openRecipes();await page.getByText('Grace after an edge: 100 ms',{exact:true}).waitFor();await shot('accepted-mechanics');
 assert.deepEqual(errors,[]);console.log('PASS: scoped recipe preparation, fixed-step before/after, input, exact review, reload, restore, ZIP, separate fixture acceptance and handoff');
}finally{await browser.close();}})().catch(error=>{console.error(error);process.exit(1)});
