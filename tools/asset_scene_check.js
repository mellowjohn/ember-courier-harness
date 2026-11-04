// Inspect the actual scene passed to Three.js while operating a sandboxed proposal.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.EMBER_PLAYWRIGHT_MODULE);
const {previewDocument,blockPeerConnections,inspectionBrowserOptions}=require('../ember_harness/ui_library.js');
const input=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),output=process.argv[3];
const config=input.interaction||{pivot_node:'LidPivot',axis:'x',open_angle_rad:-1.85,collision_node:'COLLISION_Chest',passage:false};
const observe=`<script>(()=>{const T=Ember3D.THREE;class ObservedRenderer extends T.WebGLRenderer{constructor(options){super(options);const original=this.render;this.render=function(scene,camera){globalThis.__observedScene=scene;return original.call(this,scene,camera);};}}globalThis.Ember3D={...Ember3D,THREE:{...T,WebGLRenderer:ObservedRenderer}};})();</script>`;
(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch(inspectionBrowserOptions(process.env.EMBER_BROWSER_EXECUTABLE));
  const results=[];
  try{
    for(const mobile of [false,true]){
      const context=await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1100,height:900},hasTouch:mobile,isMobile:mobile,serviceWorkers:'block',offline:true});
      await context.addInitScript(blockPeerConnections);
      const page=await context.newPage(),errors=[],requests=[];
      page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url());});
      await context.route('**/*',r=>r.abort());
      await page.setContent('<meta name="viewport" content="width=device-width,initial-scale=1"><iframe sandbox="allow-scripts" style="width:100vw;height:100vh;border:0"></iframe><style>body{margin:0}</style>');
      await page.locator('iframe').evaluate((frame,html)=>frame.srcdoc=html,previewDocument(input.html.replace('</script>','</script>'+observe)));
      const frame=page.frameLocator('iframe');await frame.locator('#load-state').filter({hasText:'Asset ready'}).waitFor({timeout:15000});
      await page.waitForTimeout(100);
      const initial=await frame.locator('body').evaluate((_,c)=>{
        const s=globalThis.__observedScene,p=s.getObjectByName('CourierPlayer'),motion=s.getObjectByName(c.pivot_node),proxy=s.getObjectByName(c.collision_node);
        return {z:p.position.z,angle:motion.rotation[c.axis],proxyVisible:proxy.visible,overflow:document.documentElement.scrollWidth>innerWidth+2};
      },config);
      assert.equal(initial.proxyVisible,false);assert.equal(initial.overflow,false);
      const name=mobile?'mobile':'desktop';await page.screenshot({path:path.join(output,name+'-closed.png')});
      if(mobile)await frame.locator('#approach').tap();
      else{
        await page.locator('iframe').focus();await page.keyboard.down('ArrowUp');await page.waitForTimeout(2100);await page.keyboard.up('ArrowUp');
      }
      await frame.locator('#status').filter({hasText:'Ready to open'}).waitFor({timeout:3000});
      const collision=await frame.locator('body').evaluate((_,c)=>{
        const T=Ember3D.THREE,s=globalThis.__observedScene,p=s.getObjectByName('CourierPlayer'),proxy=s.getObjectByName(c.collision_node);
        const bounds=new T.Box3().setFromObject(proxy);return {playerZ:p.position.z,front:bounds.max.z};
      },config);
      assert(collision.playerZ<initial.z-.2,'Player did not move toward the asset');
      assert(collision.playerZ>=collision.front+.155,'Player penetrated the actual exported collision box');
      assert(collision.playerZ<collision.front+.24,'Player could not approach the asset closely');
      let frameCollision=null;
      if(input.frame_probe_node&&!mobile){
        await page.keyboard.down('ArrowRight');await page.waitForTimeout(650);await page.keyboard.up('ArrowRight');
        frameCollision=await frame.locator('body').evaluate((_,c)=>{
          const s=globalThis.__observedScene,T=Ember3D.THREE,p=s.getObjectByName('CourierPlayer');
          const b=new T.Box3().setFromObject(s.getObjectByName(c.probeNode));
          return {playerX:p.position.x,postMinX:b.min.x,hidden:c.static_collision_nodes.every(n=>!s.getObjectByName(n).visible)};
        },{...config,probeNode:input.frame_probe_node});
        assert(frameCollision.hidden,'Frame collision helpers leaked into the visible scene');
        assert(frameCollision.playerX<=frameCollision.postMinX-.155,'Player penetrated the fixed frame post');
        assert(frameCollision.playerX>frameCollision.postMinX-.20,'Player did not move toward the frame post');
        await frame.locator('#approach').click();
      }
      if(mobile)await frame.locator('#interact').tap();else await page.keyboard.press('Space');
      await page.waitForTimeout(650);
      const opened=await frame.locator('body').evaluate((_,c)=>({angle:globalThis.__observedScene.getObjectByName(c.pivot_node).rotation[c.axis],
        count:document.getElementById('deliveries').textContent,lid:document.getElementById('lid-state').textContent}),config);
      assert.equal(opened.lid,'Open');assert.equal(opened.count,'1');
      assert(Math.abs(opened.angle-initial.angle-config.open_angle_rad)<.02,'Rendered hinge did not reach its declared angle');
      let passage=null;
      if(config.passage&&!mobile){
        await page.keyboard.down('ArrowUp');await page.waitForTimeout(200);await page.keyboard.up('ArrowUp');
        await page.keyboard.press('Space');
        await frame.locator('#status').filter({hasText:'Step clear to close'}).waitFor({timeout:1000});
        assert.equal(await frame.locator('#lid-state').textContent(),'Open');
        await page.keyboard.down('ArrowUp');await page.waitForTimeout(1200);await page.keyboard.up('ArrowUp');
        passage=await frame.locator('body').evaluate((_,c)=>{
          const s=globalThis.__observedScene,T=Ember3D.THREE,p=s.getObjectByName('CourierPlayer'),b=new T.Box3().setFromObject(s.getObjectByName(c.collision_node));
          return {playerZ:p.position.z,proxyBounds:[b.min.toArray(),b.max.toArray()]};
        },config);
        assert(passage.playerZ<collision.front-.6,'Opening did not create a traversable passage');
        const [low,high]=passage.proxyBounds;
        assert(Math.abs(high[2]-low[2])>.8,'The actual exported collider did not rotate with the gate');
        await frame.locator('#approach').click();
      }
      await page.screenshot({path:path.join(output,name+'-open.png')});
      if(mobile)await frame.locator('#interact').tap();else await page.keyboard.press('Space');
      await page.waitForTimeout(650);
      const closed=await frame.locator('body').evaluate((_,c)=>globalThis.__observedScene.getObjectByName(c.pivot_node).rotation[c.axis],config);
      assert(Math.abs(closed-initial.angle)<.02,'Hinge did not return to its source position');
      assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
      results.push({viewport:name,initial,collision,frameCollision,opened,closed,passage,networkRequests:requests.length});
      await context.close();
    }
  }finally{await browser.close();}
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({passed:true,results},null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
