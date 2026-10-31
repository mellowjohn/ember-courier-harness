const assert=require('node:assert/strict'),path=require('node:path');
const {chromium}=require(process.env.EMBER_PLAYWRIGHT_MODULE);
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.EMBER_BROWSER_EXECUTABLE});
  const page=await browser.newPage({viewport:{width:1500,height:1000}});
  page.setDefaultTimeout(15000);
  page.on('pageerror',error=>process.stderr.write('Host browser error: '+error.message+'\n'));
  try{
    await page.goto(process.env.EMBER_BROWSER_URL+'#'+process.env.EMBER_BROWSER_TOKEN);
    process.stdout.write('Editing saved gameplay scenarios\n');
    await page.locator('#gameplay-plan').waitFor();
    await page.locator('#gameplay-plan > summary').click();
    await page.getByLabel('Test plan name',{exact:true}).fill('Counter scoring and touch controls');
    async function scenario(name,viewport,actions){
      await page.getByRole('button',{name:'Add scenario',exact:true}).click();
      const box=page.locator('#gameplay-editor fieldset').last();
      await box.getByLabel('Scenario name',{exact:true}).fill(name);
      await box.getByLabel('Controls to test',{exact:true}).selectOption(viewport);
      for(const [index,step] of actions.entries()){
        if(index)await box.getByRole('button',{name:'Add step',exact:true}).click();
        const row=box.locator('.panel').nth(index);
        await row.getByLabel('Action',{exact:true}).selectOption(step.action);
        if(step.selector)await row.getByLabel('Target',{exact:true}).fill(step.selector);
        if(step.key)await row.getByLabel('Key',{exact:true}).selectOption(step.key);
        if(step.value!==undefined)await row.getByLabel('Minimum score',{exact:true}).fill(String(step.value));
      }
    }
    await scenario('Keyboard scoring','desktop',[
      {action:'click',selector:'button'},{action:'number_at_least',selector:'#score',value:1},
      {action:'press',key:'ArrowRight'},{action:'number_at_least',selector:'#score',value:2}]);
    await scenario('Touch scoring','mobile',[{action:'tap',selector:'button'},{action:'number_at_least',selector:'#score',value:1}]);
    await scenario('Keyboard before any click','desktop',[{action:'press',key:'ArrowRight'},{action:'number_at_least',selector:'#score',value:1}]);
    await page.getByRole('button',{name:'Save gameplay plan',exact:true}).click();
    await page.getByText('Plan saved · Frozen into future overnight scopes',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Run gameplay checks',exact:true}).click();
    await page.getByText('Current game · Listed checks passed',{exact:true}).waitFor();
    process.stdout.write('Current gameplay assertions passed\n');
    await page.locator('#gameplay-plan').screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'gameplay-plan.png')});
    await page.reload();
    await page.locator('#gameplay-plan > summary').click();
    assert.equal(await page.getByLabel('Test plan name',{exact:true}).inputValue(),'Counter scoring and touch controls');
    await page.locator('#gameplay-plan > summary').click();
    await page.getByRole('tab',{name:'Overnight polish',exact:true}).click();
    await page.getByLabel('What should feel better?',{exact:true}).fill('Make the counter feel warm, tactile and polished. Keep the original controls and scoring.');
    await page.getByRole('button',{name:'Review overnight scope',exact:true}).click();
    await page.getByRole('button',{name:'Approve scope & start polish',exact:true}).waitFor();
    assert.equal(await page.locator('.build-version').textContent(),'Version 1 · Latest approved build');
    await page.getByRole('button',{name:'Approve scope & start polish',exact:true}).click();
    page.setDefaultTimeout(90000);
    await page.getByRole('heading',{name:'Your polish report',exact:true}).waitFor();
    assert.equal(await page.locator('.build-version').textContent(),'Version 1 · Latest approved build');
    assert((await page.locator('#polish-workspace').textContent()).includes('Strongest candidate: Warm, responsive counter'));
    assert((await page.locator('#polish-workspace').textContent()).includes('Frozen gameplay plan: Counter scoring and touch controls'));
    await page.getByRole('button',{name:'Compare before / after screenshots',exact:true}).click();
    await page.locator('#polish-workspace img').nth(3).waitFor();
    await page.waitForFunction(()=>[...document.querySelectorAll('#polish-workspace img')].length===4&&[...document.querySelectorAll('#polish-workspace img')].every(img=>img.complete&&img.naturalWidth>0));
    await page.locator('summary').filter({hasText:'Play completed candidates (3)'}).click();
    assert.equal(await page.getByText('Gameplay: Required checks failed',{exact:true}).count(),1);
    await page.getByRole('button',{name:'Play candidate 1',exact:true}).click();
    const candidate=page.frameLocator('iframe[title="Polish candidate 1 · awaiting final approval"]');
    await candidate.getByRole('button',{name:'Start',exact:true}).click();
    await candidate.locator('body').press('ArrowRight');
    assert.equal(await candidate.locator('#score').textContent(),'2');
    await page.locator('#polish-workspace').getByRole('heading',{name:'Your polish report',exact:true}).scrollIntoViewIfNeeded();
    await page.locator('#polish-workspace').screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'morning-report.png')});
    await page.getByRole('button',{name:'Review exact changes',exact:true}).click();
    await page.getByRole('button',{name:'Approve & play',exact:true}).waitFor();
    assert.equal(await page.locator('.build-version').textContent(),'Version 1 · Latest approved build');
    await page.getByRole('button',{name:'Try proposed changes',exact:true}).click();
    const proposed=page.frameLocator('iframe[title="Proposed browser prototype · not applied"]');
    await proposed.getByRole('button',{name:'Start',exact:true}).click();
    assert.equal(await proposed.locator('body').evaluate(el=>getComputedStyle(el).display),'grid');
    assert.equal(await page.locator('.build-version').textContent(),'Version 1 · Latest approved build');
    await page.getByRole('button',{name:'Approve & play',exact:true}).click();
    await page.getByText('Version 2 · Latest approved build',{exact:true}).waitFor();
    const current=page.frameLocator('iframe[title="Approved browser prototype"]');
    await current.getByRole('button',{name:'Start',exact:true}).waitFor();
    assert.equal(await current.locator('body').evaluate(el=>getComputedStyle(el).display),'grid');
    await page.reload();
    await page.getByRole('tab',{name:'Overnight polish',exact:true}).click();
    await page.getByRole('heading',{name:'Your polish report',exact:true}).waitFor();
    assert.equal(await page.locator('.build-version').textContent(),'Version 2 · Latest approved build');
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    assert.equal(await page.locator('#error').textContent(),'');
    process.stdout.write('PASS: overnight scope, autonomous rounds, real captures, best-candidate selection and final approval\n');
  }catch(error){await page.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'failure.png'),fullPage:true});throw error}
  finally{await browser.close()}
})().catch(error=>{process.stderr.write(String(error.stack||error)+'\n');process.exitCode=1});
