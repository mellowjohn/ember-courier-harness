// Fixed host runner. Generated source executes only in an opaque, network-blocked frame.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {chromium}=require(process.env.EMBER_PLAYWRIGHT_MODULE);
const input=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),output=process.argv[3];
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const policy="default-src 'none';script-src 'unsafe-inline' data:;style-src 'unsafe-inline' data:;img-src data:;connect-src 'none';frame-src 'none';object-src 'none';base-uri 'none';form-action 'none'";
async function openGame(browser,name){
  const mobile=name==='mobile',context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1100,height:740},
    hasTouch:mobile,isMobile:mobile,serviceWorkers:'block',acceptDownloads:false});
  await context.route('**/*',route=>route.abort());
  const page=await context.newPage(),errors=[];
  page.setDefaultTimeout(1000);
  const observe=message=>{if(errors.length<5)errors.push(String(message).slice(0,300))};
  page.on('pageerror',error=>observe(error.message));
  page.on('console',message=>{if(message.type()==='error')observe(message.text())});
  await page.setContent('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0"><iframe title="polish candidate" sandbox="allow-scripts" referrerpolicy="no-referrer" style="width:100vw;height:100vh;border:0"></iframe></body></html>');
  await page.locator('iframe').evaluate((frame,html)=>{frame.srcdoc=html},'<meta http-equiv="Content-Security-Policy" content="'+policy+'">'+input.html);
  const frame=page.frameLocator('iframe');await frame.locator('body').waitFor({state:'attached'});
  await page.waitForTimeout(500);
  return {context,page,frame,errors};
}
async function gameplay(browser){
  const plan=input.gameplay_plan;
  if(!plan?.scenarios?.length)return null;
  const scenarios=[];
  for(const scenario of plan.scenarios){
    const game=await openGame(browser,scenario.viewport),steps=[];
    let failed=false;
    try{
      for(const [index,step] of scenario.steps.entries()){
        if(failed){steps.push({index,status:'skipped',observed:'Earlier step failed'});continue}
        try{
          let observed='Action completed';
          const target=step.selector?game.frame.locator('css='+step.selector):null;
          if(['click','tap','text','contains','number_at_least'].includes(step.action)&&await target.count()!==1)
            throw Error('Target must match exactly one element: '+step.selector);
          if(step.action==='click')await target.click({timeout:800});
          else if(step.action==='tap')await target.tap({timeout:800});
          else if(step.action==='press'){
            await game.page.locator('iframe').focus({timeout:800});
            await game.page.keyboard.press(step.key);
          }
          else if(step.action==='hold'){
            await game.page.locator('iframe').focus({timeout:800});
            await game.page.keyboard.down(step.key);
            try{await game.page.waitForTimeout(step.ms)}finally{await game.page.keyboard.up(step.key)}
          }
          else if(step.action==='wait')await game.page.waitForTimeout(step.ms);
          else {
            const deadline=Date.now()+800;
            while(true){
              const count=await target.count();let matched=false;
              if(count>1)throw Error('Target is ambiguous: '+step.selector);
              if(step.action==='visible'||step.action==='hidden'){
                const visible=count===1&&await target.isVisible();
                observed=visible?'Visible':'Hidden or absent';matched=step.action==='visible'?visible:!visible;
              }else if(count===1&&await target.isVisible()){
                observed=(await target.textContent({timeout:100})||'').trim();
                if(step.action==='text')matched=observed===step.value;
                else if(step.action==='contains')matched=observed.includes(step.value);
                else if(step.action==='number_at_least')matched=/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(observed)&&Number(observed)>=step.value;
                else throw Error('Unsupported gameplay assertion');
              }else observed='Target missing or hidden';
              if(matched)break;
              if(Date.now()>=deadline)throw Error('Expectation not met; observed: '+observed);
              await game.page.waitForTimeout(50);
            }
          }
          steps.push({index,status:'passed',observed:observed.slice(0,300)});
        }catch(error){failed=true;steps.push({index,status:'failed',observed:String(error.message).slice(0,300)})}
      }
      scenarios.push({name:scenario.name,viewport:scenario.viewport,steps,errors:game.errors,
        outcome:failed||game.errors.length?'failed':'passed'});
    }finally{await game.context.close()}
  }
  return {plan_sha256:input.gameplay_plan_sha256,scenarios,outcome:scenarios.every(s=>s.outcome==='passed')?'passed':'failed'};
}
(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch({headless:true,executablePath:process.env.EMBER_BROWSER_EXECUTABLE});
  const results=[];
  try{
    for(const name of ['desktop','mobile']){
      const {context,page,frame,errors:observations}=await openGame(browser,name);
      page.setDefaultTimeout(4000);
      const body=frame.locator('body');
      const before=await body.evaluate(el=>({text:(el.innerText||'').slice(0,1000),overflow:el.ownerDocument.documentElement.scrollWidth>innerWidth+2}));
      const initial=path.join(output,name+'-before.png');
      await page.screenshot({path:initial,animations:'disabled'});
      const steps=[];
      const button=frame.locator('button:visible:enabled').first();
      if(await button.count()){
        try{await button.click({timeout:1500});steps.push('Clicked first visible enabled button')}catch{observations.push('First button could not be clicked')}
      }
      const action=path.join(output,name+'-action.png');
      for(const key of ['ArrowLeft','ArrowUp','ArrowRight','ArrowDown','Space','a','d']){
        await page.locator('iframe').focus();await page.keyboard.down(key);await page.waitForTimeout(120);
        if(key==='ArrowRight')await page.screenshot({path:action,animations:'disabled'});
        await page.keyboard.up(key);
      }
      steps.push('Sent arrow, space, A and D keyboard input');
      await page.waitForTimeout(500);
      const after=await body.evaluate(el=>({text:(el.innerText||'').slice(0,1000),overflow:el.ownerDocument.documentElement.scrollWidth>innerWidth+2,canvas:el.querySelectorAll('canvas').length}));
      const sprites=await body.evaluate(()=>{
        const plan=globalThis.EMBER_SPRITE_PLAN;if(!plan)return null;
        const instances=globalThis.EmberSprites?.diagnostics?.()||[];
        return {instances,missingEntities:plan.entities.filter(e=>e.activation==='startup'&&!instances.some(i=>i.entityId===e.id&&i.assetRef===e.asset_ref&&i.draws>0)).map(e=>e.id)};
      });
      if(sprites?.missingEntities.length)observations.push('Sprite entities were not observed drawing their bound artwork: '+sprites.missingEntities.join(', '));
      const screenshot=path.join(output,name+'.png');
      await page.screenshot({path:screenshot,animations:'disabled'});
      results.push({name,loaded:true,steps,observations:observations.slice(0,5),before,after,...(sprites?{sprites}:{}),
                    screenshot:path.basename(screenshot),sha256:hash(fs.readFileSync(screenshot)),
                    action_screenshot:path.basename(action),action_sha256:hash(fs.readFileSync(action)),action_input:'ArrowRight held for 120ms',
                    before_screenshot:path.basename(initial),before_sha256:hash(fs.readFileSync(initial))});
      await context.close();
    }
    const checks=await gameplay(browser);
    const report={complete:true,input_sha256:hash(fs.readFileSync(process.argv[2])),viewports:results,
      ...(checks?{gameplay:checks}:{}),
      basis:'Real Chromium input and screenshots; DOM and error text are untrusted observations, not gameplay proof.'};
    fs.writeFileSync(path.join(output,'report.tmp'),JSON.stringify(report));
    fs.renameSync(path.join(output,'report.tmp'),path.join(output,'report.json'));
  }finally{await browser.close()}
})().catch(error=>{process.stderr.write(String(error.stack||error));process.exitCode=1});
