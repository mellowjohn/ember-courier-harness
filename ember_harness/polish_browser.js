// Fixed host runner. Generated source executes only in an opaque, network-blocked frame.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {chromium}=require(process.env.EMBER_PLAYWRIGHT_MODULE);
const {previewDocument,blockPeerConnections,inspectionBrowserOptions}=require('./ui_library.js');
const input=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),output=process.argv[3];
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
function observePlayers(players){
  const expected=new Map(players.map(row=>[row.id,row.asset_ref]));
  const seen=new Set(),lastSample=new Map();
  let active=null,enabled=false,runtime;
  globalThis.__emberPlayerProbe=Object.freeze({start(){enabled=true;},read(){return [...seen];}});
  // Wrap the existing scene API in the inspection frame only. The approved game
  // and its bundled sprite runtime still execute their exact source bytes.
  Object.defineProperty(globalThis,'EmberSprites',{get:()=>runtime,set(api){
    runtime=Object.create(api,{createScene:{value:async function(...args){
      const scene=await api.createScene(...args);
      return Object.create(scene,{createEntity:{value:function(id){
        const entity=scene.createEntity(id);
        if(entity.assetRef!==expected.get(id)||!expected.has(id))return entity;
        return Object.create(entity,{draw:{value:function(...drawArgs){
          const prior=active;active=id;
          try{return entity.draw(...drawArgs);}finally{active=prior;}
        }}});
      }}});
    }}});
  }});
  const draw=CanvasRenderingContext2D.prototype.drawImage;
  CanvasRenderingContext2D.prototype.drawImage=function(image,...args){
    const paint=()=>draw.call(this,image,...args);
    const canvas=this.canvas,now=performance.now();
    if(!enabled||!active||seen.has(active)||args.length!==8||!canvas.isConnected||
       now-(lastSample.get(active)??-Infinity)<90)return paint();
    lastSample.set(active,now);
    const box=canvas.getBoundingClientRect();
    if(!box.width||!box.height)return paint();
    for(let el=canvas;el;el=el.parentElement){
      const style=getComputedStyle(el);
      if(style.visibility!=='visible'||Number(style.opacity)<0.05)return paint();
    }
    const [x,y,w,h]=args.slice(4),matrix=this.getTransform();
    const points=[[x,y],[x+w,y],[x,y+h],[x+w,y+h]].map(([x,y])=>matrix.transformPoint({x,y}));
    const sx=canvas.width/box.width,sy=canvas.height/box.height;
    const left=Math.ceil(Math.max(0,-box.left*sx,Math.min(...points.map(p=>p.x))));
    const top=Math.ceil(Math.max(0,-box.top*sy,Math.min(...points.map(p=>p.y))));
    const width=Math.floor(Math.min(canvas.width,(innerWidth-box.left)*sx,Math.max(...points.map(p=>p.x))))-left;
    const height=Math.floor(Math.min(canvas.height,(innerHeight-box.top)*sy,Math.max(...points.map(p=>p.y))))-top;
    if(width/sx<4||height/sy<4)return paint();
    const sw=Math.min(width,128),sh=Math.min(height,128);
    const sample=[left+Math.floor((width-sw)/2),top+Math.floor((height-sh)/2),sw,sh];
    if(getComputedStyle(canvas).pointerEvents!=='none'&&![[.5,.5],[.25,.25],[.75,.75]].some(([x,y])=>
      document.elementFromPoint(box.left+(sample[0]+sw*x)/sx,box.top+(sample[1]+sh*y)/sy)===canvas))return paint();
    let before;
    try{before=this.getImageData(...sample).data;}catch{return paint();}
    const result=paint();
    const id=active;
    try{
      const after=this.getImageData(...sample).data;
      queueMicrotask(()=>{
        try{
          // Sample again after the game's synchronous paint finishes so a sprite
          // immediately cleared or painted over does not count.
          const final=this.getImageData(...sample).data;
          let changed=0;
          for(let i=0;i<after.length;i+=4){
            if(after[i]===final[i]&&after[i+1]===final[i+1]&&after[i+2]===final[i+2]&&after[i+3]===final[i+3]&&
               Math.abs(after[i]-before[i])+Math.abs(after[i+1]-before[i+1])+
               Math.abs(after[i+2]-before[i+2])+Math.abs(after[i+3]-before[i+3])>=12&&++changed>=12){seen.add(id);break;}
          }
        }catch{/* The game may have released or resized the canvas. */}
      });
    }catch{/* The draw still completes when pixels cannot be inspected. */}
    return result;
  };
}
async function startControl(frame){
  const marked=frame.locator('button[data-ember-play]:visible:enabled').first();
  if(await marked.count())return marked;
  const named=frame.getByRole('button',{name:/^(?:start|play)\b/i}).and(frame.locator('button:visible:enabled'));
  const targets=[frame.locator('button#start-btn:visible:enabled'),...await named.all()];
  for(const target of targets){
    if(await target.count()&&await target.evaluate(node=>{
      const r=node.getBoundingClientRect();return node.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));
    }))return target;
  }
  return await named.count()?named.first():targets[0];
}
async function openGame(browser,name){
  const mobile=name==='mobile',context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1100,height:740},
    hasTouch:mobile,isMobile:mobile,serviceWorkers:'block',acceptDownloads:false,offline:true});
  await context.addInitScript(blockPeerConnections);
  await context.route('**/*',route=>route.abort());
  const page=await context.newPage(),errors=[];
  page.setDefaultTimeout(1000);
  const observe=message=>{if(errors.length<5)errors.push(String(message).slice(0,300))};
  page.on('pageerror',error=>observe(error.message));
  page.on('console',message=>{if(message.type()==='error')observe(message.text())});
  await page.setContent('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0"><iframe title="polish candidate" sandbox="allow-scripts" referrerpolicy="no-referrer" style="width:100vw;height:100vh;border:0"></iframe></body></html>');
  const probe=input.players?.length?'<script>('+observePlayers.toString()+')('+JSON.stringify(input.players)+');</script>':'';
  await page.locator('iframe').evaluate((frame,html)=>{frame.srcdoc=html},previewDocument(probe+input.html));
  const frame=page.frameLocator('iframe');await frame.locator('body').waitFor({state:'attached'});
  await page.waitForTimeout(500);
  return {context,page,frame,errors};
}
async function checkSpriteState(game,step){
  const read=()=>game.frame.locator('body').evaluate((_,id)=>{
    const entity=globalThis.EMBER_SPRITE_PLAN?.entities?.find(e=>e.id===id);
    return entity?(globalThis.EmberSprites?.diagnostics?.()||[]).filter(i=>i.entityId===id&&i.assetRef===entity.asset_ref):[];
  },step.entity);
  const previous=new Map((await read()).map(i=>[i.instanceId,i.draws]));
  const frames=new Map();
  const deadline=Date.now()+(step.frames>1?1800:800);
  let observed='no new draw for the bound atlas';
  while(Date.now()<deadline){
    for(const row of await read()){
      if(row.draws<=(previous.get(row.instanceId)||0))continue;
      previous.set(row.instanceId,row.draws);
      const state=row.drawnState??row.state,frame=row.drawnFrame??row.frame;
      if(!Number.isInteger(frame))continue;
      const seen=frames.get(row.instanceId)||new Set();
      if(state===step.value)seen.add(frame);
      else seen.clear();
      frames.set(row.instanceId,seen);
      observed=state+' drew frame '+frame+(seen.size?' ('+seen.size+' distinct)':'');
      if(seen.size>=step.frames)return step.entity+' · '+step.value+' drew frames '+[...seen].join(', ');
    }
    await game.page.waitForTimeout(25);
  }
  throw Error(step.entity+' expected '+step.value+' with '+step.frames+' distinct drawn frame(s); observed '+observed);
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
          else if(step.action==='sprite_state')observed=await checkSpriteState(game,step);
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
async function mechanicObservations(browser){
  if(!input.mechanic_binding)return null;
  if(!['ember-platformer-v1','ember-platformer-v2'].includes(input.mechanic_binding.profile))throw Error('Unsupported mechanic observation profile');
  const game=await openGame(browser,'desktop');
  try{
    await game.frame.locator('#check-mechanics').click();
    const text=await game.frame.locator('#mechanic-report').textContent();
    if(!text||text.length>65536)throw Error('Missing or oversized mechanic observations');
    if(game.errors.length)throw Error('Reference mechanics reported a browser error');
    return JSON.parse(text);
  }finally{await game.context.close()}
}
async function reviewSheet(browser,name,files){
  // Fixed, bounded image packing inside the same gated browser invocation.
  // Labels identify the original evidence refs; all originals remain retained.
  const tileWidth=name==='desktop'?800:390,tileHeight=Math.ceil(tileWidth*(name==='desktop'?740/1100:844/390));
  const context=await browser.newContext({viewport:{width:tileWidth*2,height:(tileHeight+28)*Math.ceil(files.length/2)},deviceScaleFactor:1,
    serviceWorkers:'block',acceptDownloads:false});
  try{
    await context.route('**/*',route=>route.abort());
    const page=await context.newPage();
    await page.setContent('<!doctype html><html><body style="margin:0;background:#14191e;color:white;font:16px sans-serif;display:grid;grid-template-columns:1fr 1fr">'+
      files.map(file=>'<section style="margin:0;overflow:hidden"><div style="height:28px;padding:4px;box-sizing:border-box">'+file+'</div><img width="'+tileWidth+'" height="'+tileHeight+'" style="display:block;object-fit:contain" src="data:image/png;base64,'+fs.readFileSync(path.join(output,file)).toString('base64')+'"></section>').join('')+'</body></html>');
    await page.locator('img').evaluateAll(images=>Promise.all(images.map(image=>image.decode())));
    const filename=name+'-review.png';
    await page.screenshot({path:path.join(output,filename),animations:'disabled'});
    const bytes=fs.readFileSync(path.join(output,filename));
    if(bytes.length>4*1024*1024)throw Error('Review contact sheet exceeds the image allowance');
    return {review_screenshot:filename,review_sha256:hash(bytes),review_sources:files};
  }finally{await context.close()}
}
async function aspectCaptures(page,body,name){
  const results=[],original=page.viewportSize();
  // Resize the same live game document, rather than loading a fresh game for each ratio.
  const witness=await body.evaluate(()=>globalThis.__emberResizeWitness=Math.random().toString(36));
  for(const profile of (input.aspect_ratios||[]).filter(p=>p.group===name)){
    await page.setViewportSize({width:profile.width,height:profile.height});
    await page.waitForTimeout(120);
    const layout=await body.evaluate((el,witness)=>{
      const rect=n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}};
      const visible=n=>{const r=n.getBoundingClientRect(),s=getComputedStyle(n);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none'};
      const renderers=[...el.querySelectorAll('canvas,svg')].filter(visible).sort((a,b)=>b.clientWidth*b.clientHeight-a.clientWidth*a.clientHeight);
      const renderer=renderers[0];
      const stage=el.querySelector('[data-ember-game-stage]')||renderer?.closest('#stage,.stage,main,[role="application"]')||el.querySelector('main,[role="application"],#game-stage');
      const clipped=[...el.querySelectorAll('button,input,select,textarea,[role="button"]')].filter(visible).filter(n=>{
        const r=n.getBoundingClientRect();return r.left < -2||r.top < -2||r.right > innerWidth+2||r.bottom > innerHeight+2;
      }).slice(0,12).map(n=>(n.getAttribute('aria-label')||n.textContent||n.id).trim().slice(0,100));
      return {viewport:{width:innerWidth,height:innerHeight},stage:stage?rect(stage):null,
        renderer:renderer?rect(renderer):null,document_preserved:globalThis.__emberResizeWitness===witness,
        horizontal_overflow:el.ownerDocument.documentElement.scrollWidth>innerWidth+2,
        clipped_controls:clipped};
    },witness);
    const filename='aspect-'+profile.name+'.png';
    await page.screenshot({path:path.join(output,filename),animations:'disabled'});
    results.push({...profile,layout,screenshot:filename,sha256:hash(fs.readFileSync(path.join(output,filename)))});
  }
  if(results.length){await page.setViewportSize(original);await page.waitForTimeout(120)}
  return results;
}
(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch(inspectionBrowserOptions(process.env.EMBER_BROWSER_EXECUTABLE));
  const results=[],ratios=[];
  try{
    for(const name of ['desktop','mobile']){
      const {context,page,frame,errors:observations}=await openGame(browser,name);
      page.setDefaultTimeout(4000);
      const body=frame.locator('body');
      const before=await body.evaluate(el=>({text:(el.innerText||'').slice(0,1000),overflow:el.ownerDocument.documentElement.scrollWidth>innerWidth+2}));
      const initial=path.join(output,name+'-before.png');
      await page.screenshot({path:initial,animations:'disabled'});
      const steps=[];
      const start=await startControl(frame);
      const hasStart=await start.count()===1;
      const button=hasStart?start:frame.locator(input.players?.length?'button[data-ember-play]:visible:enabled':'button:visible:enabled').first();
      let started=!hasStart;
      if(await button.count()){
        try{
          if(hasStart&&name==='mobile')await button.tap({timeout:1500});
          else await button.click({timeout:1500});
          started=true;
          steps.push(hasStart?(name==='mobile'?'Tapped start button':'Clicked start button'):'Clicked first visible enabled button');
        }catch{observations.push(hasStart?'Start button could not be activated':'First button could not be clicked')}
      }
      if(input.players?.length&&started)await body.evaluate(()=>globalThis.__emberPlayerProbe.start());
      if(input.players?.length&&started)await page.waitForTimeout(700);
      const players=input.players?.length?await body.evaluate((_,expected)=>{
        const visible=globalThis.__emberPlayerProbe.read();
        return expected.map(({id})=>({id,visible:visible.includes(id)}));
      },input.players):null;
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
      const aspectViews=await aspectCaptures(page,body,name);ratios.push(...aspectViews);
      let panelCapture={};
      const panelButtons=frame.locator('button[aria-controls]:visible:enabled');
      for(let i=0;i<Math.min(await panelButtons.count(),8);i++){
        const trigger=panelButtons.nth(i);
        const label=(await trigger.getAttribute('aria-label'))||(await trigger.textContent())||'';
        const target=await trigger.getAttribute('aria-controls');
        if(!/help|settings|pause|guide/i.test(label)||!target||!/^[-a-zA-Z0-9_]+$/.test(target))continue;
        const panel=frame.locator('#'+target);
        if(await panel.count()!==1)continue;
        try{
          if(!await panel.isVisible())await trigger.click({timeout:1000});
          if(await panel.isVisible()){
            const opened=path.join(output,name+'-panel.png');
            await page.screenshot({path:opened,animations:'disabled'});
            panelCapture={panel_screenshot:path.basename(opened),panel_sha256:hash(fs.readFileSync(opened)),panel_trigger:label.slice(0,100)};
            break;
          }
        }catch{/* Missing panel evidence stays unobserved; gameplay captures remain available. */}
      }
      const reviewCapture=input.review_sheets?await reviewSheet(browser,name,[name+'.png',name+'-before.png',name+'-action.png',...(panelCapture.panel_screenshot?[panelCapture.panel_screenshot]:[]),...aspectViews.map(v=>v.screenshot)]):{};
      results.push({name,loaded:true,steps,observations:observations.slice(0,5),before,after,...(sprites?{sprites}:{}),...reviewCapture,
                    ...(players?{players}:{}),
                    ...panelCapture,
                    screenshot:path.basename(screenshot),sha256:hash(fs.readFileSync(screenshot)),
                    action_screenshot:path.basename(action),action_sha256:hash(fs.readFileSync(action)),action_input:'ArrowRight held for 120ms',
                    before_screenshot:path.basename(initial),before_sha256:hash(fs.readFileSync(initial))});
      await context.close();
    }
    const checks=await gameplay(browser);
    const mechanics=await mechanicObservations(browser);
    const report={complete:true,input_sha256:hash(fs.readFileSync(process.argv[2])),viewports:results,
      ...(input.aspect_ratios?{aspect_ratios:ratios}:{}),
      ...(checks?{gameplay:checks}:{}),
      ...(mechanics?{mechanics}:{}),
      basis:'Real Chromium input and screenshots; DOM and error text are untrusted observations, not gameplay proof.'};
    fs.writeFileSync(path.join(output,'report.tmp'),JSON.stringify(report));
    fs.renameSync(path.join(output,'report.tmp'),path.join(output,'report.json'));
  }finally{await browser.close()}
})().catch(error=>{process.stderr.write(String(error.stack||error));process.exitCode=1});
