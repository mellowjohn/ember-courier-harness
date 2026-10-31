// Fixed host runner. Generated source executes only in an opaque, network-blocked frame.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {chromium}=require(process.env.EMBER_PLAYWRIGHT_MODULE);
const input=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),output=process.argv[3];
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch({headless:true,executablePath:process.env.EMBER_BROWSER_EXECUTABLE});
  const results=[];
  try{
    for(const [name,width,height] of [['desktop',1100,740],['mobile',390,844]]){
      const context=await browser.newContext({viewport:{width,height},serviceWorkers:'block',acceptDownloads:false});
      await context.route('**/*',route=>route.abort());
      const page=await context.newPage(),observations=[];
      page.setDefaultTimeout(4000);
      page.on('pageerror',error=>{if(observations.length<5)observations.push(String(error.message).slice(0,300))});
      page.on('console',message=>{if(message.type()==='error'&&observations.length<5)observations.push(message.text().slice(0,300))});
      await page.setContent('<!doctype html><html><body style="margin:0"><iframe title="polish candidate" sandbox="allow-scripts" referrerpolicy="no-referrer" style="width:100vw;height:100vh;border:0"></iframe></body></html>');
      const policy="default-src 'none';script-src 'unsafe-inline' data:;style-src 'unsafe-inline' data:;img-src data:;connect-src 'none';frame-src 'none';object-src 'none';base-uri 'none';form-action 'none'";
      await page.locator('iframe').evaluate((frame,html)=>{frame.srcdoc=html},'<meta http-equiv="Content-Security-Policy" content="'+policy+'">'+input.html);
      const frame=page.frameLocator('iframe'),body=frame.locator('body');
      await body.waitFor({state:'attached'});
      await page.waitForTimeout(500);
      const before=await body.evaluate(el=>({text:(el.innerText||'').slice(0,1000),overflow:el.ownerDocument.documentElement.scrollWidth>innerWidth+2}));
      const initial=path.join(output,name+'-before.png');
      await page.screenshot({path:initial,animations:'disabled'});
      const steps=[];
      const button=frame.locator('button:visible:enabled').first();
      if(await button.count()){
        try{await button.click({timeout:1500});steps.push('Clicked first visible enabled button')}catch{observations.push('First button could not be clicked')}
      }
      for(const key of ['ArrowLeft','ArrowUp','ArrowRight','ArrowDown','Space','a','d']){
        await body.focus();await page.keyboard.down(key);await page.waitForTimeout(120);await page.keyboard.up(key);
      }
      steps.push('Sent arrow, space, A and D keyboard input');
      await page.waitForTimeout(500);
      const after=await body.evaluate(el=>({text:(el.innerText||'').slice(0,1000),overflow:el.ownerDocument.documentElement.scrollWidth>innerWidth+2,canvas:el.querySelectorAll('canvas').length}));
      const screenshot=path.join(output,name+'.png');
      await page.screenshot({path:screenshot,animations:'disabled'});
      results.push({name,loaded:true,steps,observations:observations.slice(0,5),before,after,
                    screenshot:path.basename(screenshot),sha256:hash(fs.readFileSync(screenshot)),
                    before_screenshot:path.basename(initial),before_sha256:hash(fs.readFileSync(initial))});
      await context.close();
    }
    const report={complete:true,input_sha256:hash(fs.readFileSync(process.argv[2])),viewports:results,
      basis:'Real Chromium input and screenshots; DOM and error text are untrusted observations, not gameplay proof.'};
    fs.writeFileSync(path.join(output,'report.tmp'),JSON.stringify(report));
    fs.renameSync(path.join(output,'report.tmp'),path.join(output,'report.json'));
  }finally{await browser.close()}
})().catch(error=>{process.stderr.write(String(error.stack||error));process.exitCode=1});
