const assert = require('node:assert/strict'), path = require('node:path');
const {chromium} = require(process.env.EMBER_PLAYWRIGHT_MODULE);
(async()=>{
  const browser = await chromium.launch({headless:true, executablePath:process.env.EMBER_BROWSER_EXECUTABLE});
  const page = await browser.newPage({viewport:{width:1500,height:1000}});
  page.setDefaultTimeout(30000);
  const view = id=>require('./workspace_browser').view(page,id);
  const exactForm=process.env.EMBER_GIT_FORM==='1';
  const title=exactForm?'Repair two-point parcel reward':'Two-point parcel delivery';
  try{
    await page.goto(process.env.EMBER_BROWSER_URL+'#'+process.env.EMBER_BROWSER_TOKEN);
    if(exactForm){
      await view('plan');
      const form=page.locator('#git-repair-form');
      await form.getByLabel('What should this repair fix?',{exact:true}).fill(title);
      await form.locator('select[name="path"]').selectOption('app.js');
      await form.getByLabel('Find this exact source text',{exact:true}).fill('score+=1');
      await form.getByLabel('Replace it with',{exact:true}).fill('score+=2');
      await form.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'git-exact-edit-form.png')});
      await form.getByRole('button',{name:'Review local Git repair',exact:true}).click();
    }else await page.getByRole('button',{name:'Verify this proposal with Git',exact:true}).click();
    await page.getByRole('button',{name:'Approve local Git repair',exact:true}).waitFor();
    await page.getByText('LOCAL GIT REPAIR · REVIEW BEFORE EXECUTION',{exact:true}).waitFor();
    assert.equal(await page.locator('.build-version').textContent(),'Version 1 · Approved and ready to play');
    assert.equal(await page.getByRole('button',{name:'Approve & play',exact:true}).count(),0,'The pending Git permissions must be reviewed first');
    await page.locator('#review').screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'git-permission-review.png')});
    await page.getByRole('button',{name:'Approve local Git repair',exact:true}).click();
    await page.getByRole('button',{name:'Approve local Git repair',exact:true}).waitFor({state:'detached'});
    await view('plan');
    const card=page.locator('[data-git-run]').last();
    await card.getByRole('button',{name:'Review Git-verified game changes',exact:true}).waitFor({timeout:150000});
    assert.equal(await page.locator('.build-version').textContent(),'Version 1 · Approved and ready to play');
    await card.getByRole('button',{name:'Play Git candidate',exact:true}).click();
    const candidate=card.locator('iframe').contentFrame();
    await candidate.getByRole('button',{name:'Collect parcel',exact:true}).click();
    assert.equal(await candidate.locator('#score').textContent(),'2');
    await candidate.getByRole('button',{name:'Restart',exact:true}).click();
    assert.equal(await candidate.locator('#score').textContent(),'0');
    assert.equal(await card.locator('iframe').getAttribute('sandbox'),'allow-scripts');
    await card.getByRole('button',{name:'View Git before / after screenshots',exact:true}).click();
    await page.waitForFunction(()=>{
      const images=document.querySelectorAll('[data-git-run] img');
      return images.length===4&&[...images].every(image=>image.complete&&image.naturalWidth>0);
    });
    await card.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'git-verified-before-after.png')});
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'git-candidate-mobile.png')});
    await page.setViewportSize({width:1500,height:1000});
    await card.getByRole('button',{name:'Review Git-verified game changes',exact:true}).click();
    await page.getByRole('heading',{name:exactForm?'Git-verified browser repair':title,exact:true}).waitFor();
    await page.getByRole('button',{name:'Approve & play',exact:true}).click();
    await page.getByText('Version 2 · Approved and ready to play',{exact:true}).waitFor();
    await view('plan');
    await page.locator('[data-task-id="task-1"]').getByText('Build applied · outcome needs review',{exact:true}).waitFor();
    await page.locator('[data-task-id="task-1"]').getByRole('button',{name:'Accept task outcome',exact:true}).waitFor();
    await page.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'git-applied-outcome-pending.png')});
    await view('plan');
    const synthetic=await page.evaluate(()=>structuredClone(lastState));
    const saved=synthetic.git_runs.at(-1), stateHash='f'.repeat(64);
    saved.status='needs_changes';saved.report=null;
    saved.attempts={attempts:[1,2,3].map(number=>({number,run_id:'synthetic-policy-'+number,outcome:'failed'})),
      blocked:true,allowance:3,limit:3,next_attempt:4,stopped:false,state_hash:stateHash};
    synthetic.git_runs=[structuredClone(saved),structuredClone(saved)];
    const retry=page.getByRole('button',{name:'Authorize one extra Git attempt',exact:true});
    await page.waitForFunction(()=>!busy&&!sending);
    let received;
    const submittedPromise=new Promise(resolve=>{received=resolve});
    await page.route('**/api/git-task',async route=>{
      const submitted=route.request().postDataJSON();
      await route.fulfill({status:200,contentType:'application/json',body:'{}'});
      received(submitted);
    },{times:1});
    const controls=await page.evaluate(state=>{
      renderGit(state);
      const buttons=[...document.querySelectorAll('button')].filter(button=>button.textContent==='Authorize one extra Git attempt');
      if(buttons.length!==1)throw Error('Shared task allowance controls must be deduplicated');
      buttons[0].click();return buttons.length;
    },synthetic);
    assert.equal(controls,1);
    const submitted=await submittedPromise;
    await page.unrouteAll({behavior:'wait'});
    await retry.waitFor({state:'detached'});
    assert.deepEqual(submitted,{session_id:synthetic.session.id,action:'escalate',run_id:saved.id,choice:'retry',state_hash:stateHash});
    process.stdout.write('PASS: actual Git permission card, before/head progress, private candidate play and captures, separate exact approval, human outcome pending\n');
    process.stdout.write('PASS: synthetic three-attempt UI policy and deduplicated retry submission; click intercepted, real ledger unchanged\n');
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exit(1)});
