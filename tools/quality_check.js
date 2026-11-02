// Owned fixture browser; never a user session or live provider.
const assert=require('node:assert/strict'),path=require('node:path');
const {chromium}=require(process.env.EMBER_PLAYWRIGHT_MODULE);
(async()=>{
  const browser=await chromium.launch({headless:true,executablePath:process.env.EMBER_BROWSER_EXECUTABLE});
  try{
    const page=await browser.newPage({viewport:{width:1400,height:1000}}),errors=[];page.setDefaultTimeout(90000);
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(process.env.EMBER_BROWSER_URL+'#'+process.env.EMBER_BROWSER_TOKEN);
    await require('./workspace_browser').view(page,'chat');
    const review=page.getByRole('region',{name:'Game verification'});
    await review.getByText('Verification found issues to fix',{exact:true}).waitFor();
    await review.getByText('Gameplay assertions: failed · AI visual review: completed',{exact:true}).waitFor();
    await review.getByText('View game screenshots',{exact:true}).click();
    await page.waitForFunction(()=>[...document.querySelectorAll('#proposal-quality-review img')].length===4&&[...document.querySelectorAll('#proposal-quality-review img')].every(i=>i.complete&&i.naturalWidth>0));
    await review.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'verification-issues.png')});
    await review.getByRole('button',{name:'Fix verification issues',exact:true}).click();
    await review.getByText('Checks passed · ready for your review',{exact:true}).waitFor();
    await review.getByText('Gameplay assertions: passed · AI visual review: completed',{exact:true}).waitFor();
    await review.getByText('View game screenshots',{exact:true}).click();
    await page.waitForFunction(()=>[...document.querySelectorAll('#proposal-quality-review img')].length===4&&[...document.querySelectorAll('#proposal-quality-review img')].every(i=>i.complete&&i.naturalWidth>0));
    await review.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'verification-passed.png')});
    await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await review.screenshot({path:path.join(process.env.EMBER_BROWSER_OUTPUT,'verification-mobile.png')});
    assert.deepEqual(errors,[]);
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
