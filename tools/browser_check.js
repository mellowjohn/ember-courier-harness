// Optional developer rehearsal. Install Playwright in an ignored tools folder.
const assert = require('node:assert/strict');
const path = require('node:path');
const {chromium} = require(process.env.EMBER_PLAYWRIGHT_MODULE || 'playwright');

(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.EMBER_BROWSER_EXECUTABLE?{executablePath:process.env.EMBER_BROWSER_EXECUTABLE}:{})});
  try{
    const page=await browser.newPage({viewport:{width:1500,height:1000}}),hostErrors=[];
    page.on('pageerror',error=>hostErrors.push(error.message));
    await page.goto(process.env.EMBER_BROWSER_URL+'#'+process.env.EMBER_BROWSER_TOKEN);
    const smoke=page.getByRole('button',{name:'Run browser smoke check',exact:true});
    await smoke.waitFor();
    const preview=page.frameLocator('iframe[title="Approved browser prototype"]');
    await preview.getByRole('button',{name:'Start',exact:true}).click();
    await preview.locator('body').press('ArrowRight');
    assert.equal(await preview.locator('#score').textContent(),'2');
    // An unrelated frame/window must not be able to inject a preview observation.
    await page.evaluate(()=>window.postMessage({emberPreview:'wrong-channel',kind:'error',message:'FORGED'},'*'));
    assert(!await page.locator('.playtest-area pre').textContent().then(text=>text.includes('FORGED')));
    await smoke.click();
    await page.locator('iframe[title="Browser smoke check"]').waitFor();
    await page.evaluate(()=>{
      const html=document.querySelector('iframe[title="Browser smoke check"]').srcdoc;
      const channel=html.match(/const channel="([a-f0-9]+)"/)[1];
      window.postMessage({emberSmoke:channel,kind:'done',metrics:{loaded:true,animation_frame:true,inputs_sent:true,button_clicked:true,completed:true}},'*');
    });
    await page.locator('#smoke-status').getByText('Browser check: issues observed',{exact:true}).waitFor();
    assert((await page.locator('#smoke-status').textContent()).includes('SYNTHETIC startup failure'));
    // Saving a smoke report and polling must preserve the player's current game.
    assert.equal(await preview.locator('#score').textContent(),'2');
    await page.getByRole('button',{name:'Ask Muse to fix browser issues',exact:true}).click();
    await page.getByRole('button',{name:'Approve & play',exact:true}).waitFor();
    assert.equal(await preview.locator('#score').textContent(),'2');
    await page.getByRole('button',{name:'Approve & play',exact:true}).click();
    await page.getByText('Version 3 · Latest approved build',{exact:true}).waitFor();
    await preview.getByRole('button',{name:'Start',exact:true}).waitFor();
    assert.equal(await preview.locator('body').getAttribute('data-revision'),'fixed');
    await smoke.click();
    await page.locator('#smoke-status').getByText('Browser check: no errors observed',{exact:true}).waitFor();
    await page.locator('summary').filter({hasText:'Saved versions ('}).click();
    await page.getByRole('button',{name:'Review restore of version 1',exact:true}).click();
    await page.getByRole('button',{name:'Approve restore & play',exact:true}).waitFor();
    assert.equal(await page.locator('.build-version').textContent(),'Version 3 · Latest approved build');
    await page.getByText('View code changes',{exact:true}).click();
    assert((await page.locator('#review pre').first().textContent()).includes('dataset.revision'));
    await page.getByRole('button',{name:'Approve restore & play',exact:true}).click();
    await page.getByText('Version 4 · Latest approved build',{exact:true}).waitFor();
    await preview.getByRole('button',{name:'Start',exact:true}).waitFor();
    assert.equal(await preview.locator('body').getAttribute('data-revision'),null);
    await preview.getByRole('button',{name:'Start',exact:true}).click();
    await preview.locator('body').press('ArrowRight');
    assert.equal(await preview.locator('#score').textContent(),'2');
    await smoke.click();
    await page.locator('#smoke-status').getByText('Browser check: no errors observed',{exact:true}).waitFor();
    await page.locator('summary').filter({hasText:'Saved versions ('}).click();
    await page.getByRole('button',{name:'Preview version 2',exact:true}).click();
    await page.frameLocator('iframe[title="Saved build version 2"]').getByRole('button',{name:'Start',exact:true}).waitFor();
    const downloadPromise=page.waitForEvent('download');
    await page.getByRole('button',{name:'Download version 1',exact:true}).click();
    const download=await downloadPromise;
    assert.equal(download.suggestedFilename(),'ember-game-v1.zip');
    await download.saveAs(path.join(process.env.EMBER_BROWSER_OUTPUT,'original-game.zip'));
    const sandbox=await page.locator('iframe[title="Approved browser prototype"]').getAttribute('sandbox');
    assert.equal(sandbox,'allow-scripts');
    assert.equal(await page.locator('#error').textContent(),'');
    await page.locator('summary').filter({hasText:'Saved versions ('}).click();
    await page.locator('.playtest-area').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'workspace.png')});
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.locator('.playtest-area').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'mobile.png')});
    assert(hostErrors.every(message=>message==='SYNTHETIC startup failure'),JSON.stringify(hostErrors));
    process.stdout.write('PASS: browser QA, reviewed fix, restore, preserved history, responsive workspace and ZIP export\n');
  }finally{await browser.close()}
})().catch(error=>{process.stderr.write(String(error.stack||error)+'\n');process.exitCode=1});
