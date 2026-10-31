const assert=require('node:assert/strict'),path=require('node:path');
const {chromium}=require(process.env.EMBER_PLAYWRIGHT_MODULE);
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.EMBER_BROWSER_EXECUTABLE});
  const page=await browser.newPage({viewport:{width:1500,height:1000}});
  page.setDefaultTimeout(90000);
  try{
    await page.goto(process.env.EMBER_BROWSER_URL+'#'+process.env.EMBER_BROWSER_TOKEN);
    await page.getByRole('tab',{name:'Overnight polish',exact:true}).click();
    await page.getByLabel('What should feel better?',{exact:true}).fill('Make the counter feel warm, tactile and polished. Keep the original controls and scoring.');
    await page.getByRole('button',{name:'Review overnight scope',exact:true}).click();
    await page.getByRole('button',{name:'Approve scope & start polish',exact:true}).waitFor();
    assert.equal(await page.locator('.build-version').textContent(),'Version 1 · Latest approved build');
    await page.getByRole('button',{name:'Approve scope & start polish',exact:true}).click();
    await page.getByRole('heading',{name:'Your polish report',exact:true}).waitFor();
    assert.equal(await page.locator('.build-version').textContent(),'Version 1 · Latest approved build');
    assert((await page.locator('#polish-workspace').textContent()).includes('Strongest candidate: Warm, responsive counter'));
    await page.getByRole('button',{name:'Compare before / after screenshots',exact:true}).click();
    await page.locator('#polish-workspace img').nth(3).waitFor();
    await page.waitForFunction(()=>[...document.querySelectorAll('#polish-workspace img')].length===4&&[...document.querySelectorAll('#polish-workspace img')].every(img=>img.complete&&img.naturalWidth>0));
    await page.locator('summary').filter({hasText:'Play completed candidates (3)'}).click();
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
