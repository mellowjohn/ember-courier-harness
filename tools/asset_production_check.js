const assert=require('node:assert/strict');
const path=require('node:path');
const {chromium}=require(process.env.EMBER_PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.EMBER_BROWSER_EXECUTABLE});
 try{
  const page=await browser.newPage({viewport:{width:1500,height:1000}});page.setDefaultTimeout(180000);
    const view=id=>require('./workspace_browser').view(page,id);
    const editChecks=async()=>{await view('playtest');if(await page.locator('#gameplay-form').isHidden())await page.locator('#gameplay-edit').click()};

  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await require('./workspace_browser').stubPlanBuild(page);
  await page.goto(process.env.EMBER_BROWSER_URL+'#'+process.env.EMBER_BROWSER_TOKEN);
  await view('plan');
  await page.getByRole('button',{name:'Create chest directions',exact:true}).click();
  await Promise.race([page.getByRole('button',{name:'Approve task run',exact:true}).waitFor(),
    page.locator('#error').filter({hasText:/\S/}).waitFor().then(async()=>{throw Error(await page.locator('#error').textContent())})]);
  await page.getByRole('button',{name:'Approve task run',exact:true}).click();
  await page.getByRole('button',{name:'Choose Fieldwork oak',exact:true}).waitFor();
  await page.waitForFunction(()=>[...document.querySelectorAll('img[alt$="hero Blender render"]')].filter(i=>i.complete&&i.naturalWidth===512).length===3);
  assert.equal(await page.locator('[data-direction]').count(),3);
  await page.locator('#task-run-list').screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'three-directions.png')});
  await page.reload();await view('chat');
  await page.getByRole('button',{name:'Choose Fieldwork oak',exact:true}).click();
  await page.getByRole('button',{name:'Refine Blender source',exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Review exact asset changes',exact:true}).count(),0);
  await page.getByRole('textbox',{name:'Asset refinement feedback',exact:true}).fill('The collision prevents keyboard and touch opening. Reduce the proxy padding, keep the palette, and improve the front slat readability.');
  await page.getByRole('button',{name:'Refine Blender source',exact:true}).click();
  await page.getByRole('button',{name:'Review exact asset changes',exact:true}).waitFor();
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.locator('[data-task-run]').screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'refined-asset-mobile.png')});
  await page.setViewportSize({width:1500,height:1000});
  await page.getByRole('button',{name:'Review exact asset changes',exact:true}).click();
  await page.getByRole('button',{name:'Try proposed changes',exact:true}).click();
  const proposed=page.frameLocator('iframe[title="Proposed browser prototype · not applied"]');
  await proposed.locator('#approach').click();await proposed.locator('#interact').click();
  await proposed.locator('#lid-state').getByText('Open',{exact:true}).waitFor();
  await page.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'exact-asset-review.png')});
  await page.getByRole('button',{name:'Accept asset & play',exact:true}).click();
  await page.getByText('Version 1 · Approved and ready to play',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Accept task outcome',exact:true}).click();
  await page.locator('#active-task').getByText('Outcome accepted by you',{exact:true}).waitFor();
  if(process.env.EMBER_INTEGRATED_SAMPLE==='1'){
    await view('plan');await page.getByRole('button',{name:'Amend or renew project plan',exact:true}).click();
    await page.locator('#plan-features').fill('Produce and refine an original courier chest\nAward two parcels per dispatch');
    await page.locator('#plan-done_criteria').fill('Approved direction and editable native source\nIndependent export and keyboard/touch checks\nSeparate human asset acceptance\nEach accepted dispatch awards two parcels and reset clears the count');
    await page.getByRole('button',{name:'Prepare plan for review',exact:true}).click();
    await page.getByRole('button',{name:'Acknowledge scope changes',exact:true}).waitFor();
    assert(await page.getByRole('button',{name:'Approve project plan',exact:true}).isDisabled());
    await page.getByRole('button',{name:'Acknowledge scope changes',exact:true}).click();
    await page.getByRole('button',{name:'Approve project plan',exact:true}).click();
    await page.waitForFunction(()=>!busy&&!sending);
    await view('plan');
    const dispatch=page.locator('[data-task-id="task-2"]');
    await dispatch.getByRole('button',{name:'Work on this task',exact:true}).click();
    await editChecks();
    for(const input of await page.getByLabel('Expected text',{exact:true}).all()){
      if(await input.inputValue()==='1')await input.fill('2');
    }
    await page.getByRole('button',{name:'Save gameplay plan',exact:true}).click();
    await view('playtest');await page.getByRole('button',{name:'Run gameplay checks',exact:true}).click();
    await page.getByText('Gameplay checks found a problem',{exact:true}).waitFor();
    // First scenario passes (too far); select the keyboard dispatch failure explicitly.
    await page.locator('.playtest-area textarea').fill('SYNTHETIC integrated finding: approach and open with Space or touch; dispatch awards one parcel instead of the two required by the reviewed amendment.');
    await page.getByRole('button',{name:'Record problem',exact:true}).click();
    await page.locator('#finding-summary').fill('SYNTHETIC two-parcel dispatch is missing');
    await page.locator('#finding-steps').fill('Approach the chest\nPress Space or tap Open chest\nInspect the delivery count');
    await page.locator('#finding-expected').fill('Two parcels per dispatch');
    await page.locator('#finding-actual').fill('One parcel');
    await page.locator('#finding-symptom_tag').fill('two_parcel_dispatch');
    await page.getByRole('button',{name:'Prepare finding for review',exact:true}).click();
    await page.getByRole('button',{name:'Approve finding intake',exact:true}).click();
    const finding=page.locator('[data-finding="BUG-0001"]');
    await finding.getByLabel('Regression scenario for BUG-0001',{exact:true}).selectOption('1');
    await finding.getByRole('button',{name:'Prepare scoped fix',exact:true}).click();
    await page.getByRole('button',{name:'Approve task run',exact:true}).click();
    await page.getByRole('button',{name:'Review exact task changes',exact:true}).waitFor({timeout:300000});
    await page.locator('#task-run-list').screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'integrated-independent-fix.png')});
    await page.getByRole('button',{name:'Review exact task changes',exact:true}).click();
    await page.getByRole('button',{name:'Try proposed changes',exact:true}).click();
    await proposed.locator('#approach').click();await proposed.locator('#interact').click();
    await proposed.locator('#deliveries').getByText('2',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Approve & play',exact:true}).click();
    await page.getByText('Version 2 · Approved and ready to play',{exact:true}).waitFor();
    await view('playtest');await finding.getByRole('button',{name:'Review verified closure',exact:true}).click();
    await page.getByRole('button',{name:'Approve bug closure',exact:true}).click();
    await finding.getByText('S2 · closed · Systems Designer · 1 attempts',{exact:true}).waitFor();
    await view('plan');await dispatch.getByRole('button',{name:'Accept task outcome',exact:true}).click();
    await dispatch.getByText('Outcome accepted by you',{exact:true}).waitFor();
    await view('playtest');await page.getByRole('button',{name:'Run gameplay checks',exact:true}).click();
    await page.getByText('Listed gameplay checks passed',{exact:true}).waitFor();
    await page.reload();await page.getByText('Version 2 · Approved and ready to play',{exact:true}).waitFor();
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    const download=page.waitForEvent('download');
    await view('report');await page.getByRole('button',{name:'Download project handoff',exact:true}).click();
    await (await download).saveAs(path.join(process.env.EMBER_BROWSER_OUTPUT,'project-handoff.zip'));
    await page.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'integrated-handoff-mobile.png')});
  }
  assert.deepEqual(errors,[]);
  process.stdout.write('PASS: real concept renders, explicit pick, Blender refinement, independent checks and separate exact acceptance\n');
 }finally{await browser.close()}
})().catch(e=>{process.stderr.write(String(e.stack||e)+'\n');process.exitCode=1});
