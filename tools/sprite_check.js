const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const {chromium} = require(process.env.EMBER_PLAYWRIGHT_MODULE);
const input = JSON.parse(fs.readFileSync(process.argv[2], 'utf8')), output = process.argv[3];
const policy = "default-src 'none';script-src 'unsafe-inline' data:;style-src 'unsafe-inline' data:;img-src data:;connect-src 'none';object-src 'none'";
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.EMBER_BROWSER_EXECUTABLE});
  const results = [];
  try {
    if(input.variant==='review')results.push(await require('./sprite_scene_check.js').checkReview(browser,output));
    else for (const stage of ['preview','exported']) for (const mobile of [false, true]) {
      const html=input[stage];
      const context = await browser.newContext({viewport:mobile?{width:390,height:844}:{width:1100,height:1000},hasTouch:mobile,isMobile:mobile,serviceWorkers:'block'});
      const page = await context.newPage(), errors = [], requests = [];
      page.on('pageerror', e => errors.push(e.message));
      page.on('request', r => {if (/^https?:/.test(r.url())) requests.push(r.url());});
      await context.route('**/*', r => r.abort());
      await page.setContent('<meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0}iframe{border:0;width:100vw;height:100vh}</style><iframe sandbox="allow-scripts"></iframe>');
      await page.locator('iframe').evaluate((frame, source) => frame.srcdoc=source, '<meta http-equiv="Content-Security-Policy" content="'+policy+'">'+html);
      const frame = page.frameLocator('iframe'), state = frame.locator('#animation-state');
      if(input.variant==='tiles'){
        results.push(await checkTiles({page,frame,stage,mobile,errors,requests}));
        await context.close();continue;
      }
      if(input.variant==='entities'){
        try{results.push(await require('./sprite_scene_check.js').checkGame({context,page,frame,stage,mobile,output,errors,requests}));}
        catch(error){console.error(JSON.stringify({stage,mobile,errors,requests,text:await frame.locator('body').innerText()}));await page.screenshot({path:path.join(output,'failed.png')});throw error;}
        await context.close();continue;
      }
      await frame.locator('#load-state').filter({hasText:'Asset ready'}).waitFor();
      await state.filter({hasText:'idle'}).waitFor();
      const pixels = await frame.locator('canvas').evaluate(canvas => {
        const image = canvas.getContext('2d').getImageData(0,0,840,340).data;
        let visible=0; for (let i=3;i<image.length;i+=4) if (image[i]) visible++;
        return visible;
      });
      assert(pixels>500, 'Actual PNG artwork must reach the canvas');
      const api = await frame.locator('body').evaluate(async () => {
        const atlas = await EmberSprites.load(), actor=atlas.createPlayer('walk'), other=atlas.createPlayer('idle');
        actor.seek(1); const reorderedFrame=actor.frame;
        actor.play('attack'); const completion=actor.update(.9), next=actor.animation;
        actor.play('death'); actor.update(5); const held=actor.frame, ended=actor.completed;
        const canvases=[document.createElement('canvas'), document.createElement('canvas')];
        actor.play('idle');
        const images=canvases.map((c,i)=>{
          c.width=c.height=100; const ctx=c.getContext('2d');
          ctx.globalCompositeOperation='xor'; ctx.imageSmoothingEnabled=true;
          actor.draw(ctx,50,80,{flipX:!!i});
          if(ctx.globalCompositeOperation!=='xor'||!ctx.imageSmoothingEnabled||ctx.getTransform().a!==1) throw Error('Canvas state leaked');
          return ctx.getImageData(0,0,100,100).data;
        });
        let mirrored=true;
        for(let y=0;y<100;y++)for(let x=0;x<100;x++)for(let c=0;c<4;c++)
          if(images[0][(y*100+x)*4+c]!==images[1][(y*100+99-x)*4+c]) mirrored=false;
        const color=Array.from(images[0].slice((56*100+50)*4,(56*100+50)*4+4));
        let decodeError=false;
        try {await EmberSprites.load({...EMBER_ASSET,png_base64:'broken'});} catch(e) {decodeError=/decoded/.test(e.message);}
        return {reorderedFrame,completion,next,held,ended,independentFrame:other.frame,mirrored,color,decodeError};
      });
      assert.deepEqual(api,{reorderedFrame:4,completion:['attack'],next:'idle',held:11,ended:true,independentFrame:0,mirrored:true,color:[40,100,160,255],decodeError:true});
      await frame.locator('#paused').check();
      await frame.locator('#playback-state').filter({hasText:'Paused'}).waitFor();
      await frame.locator('#replay').click();
      await frame.locator('#playback-state').filter({hasText:'Playing'}).waitFor();
      if (mobile) {
        const button = frame.locator('#right');
        // A real touch press is held long enough to observe movement and its walk clip.
        const box = await button.boundingBox();
        const client = await context.newCDPSession(page);
        await client.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:box.x+box.width/2,y:box.y+box.height/2}]});
        await state.filter({hasText:'walk'}).waitFor(); await page.waitForTimeout(220);
        await client.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
      } else {
        await frame.locator('body').click({position:{x:5,y:5}});
        await page.keyboard.down('ArrowRight');
        await state.filter({hasText:'walk'}).waitFor(); await page.waitForTimeout(220);
        await page.keyboard.up('ArrowRight');
      }
      const moved = Number(await frame.locator('#position').textContent());
      assert(moved>225,'Input must move the actual sprite');
      await state.filter({hasText:'idle'}).waitFor();
      if(mobile) await frame.locator('#action').tap(); else await page.keyboard.press('Space');
      await state.filter({hasText:'attack'}).waitFor();
      await state.filter({hasText:'idle'}).waitFor();
      await frame.locator('#animation').selectOption('death');
      await frame.locator('#playback-state').filter({hasText:'Finished'}).waitFor();
      await frame.locator('#status').filter({hasText:'Frame 12 / 12'}).waitFor();
      const viewport=mobile?'mobile':'desktop';
      await page.screenshot({path:path.join(output,stage+'-'+viewport+'.png')});
      assert.equal(await frame.locator('body').evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false,'Workshop must fit the viewport');
      assert.deepEqual(errors,[]); assert.deepEqual(requests,[]);
      results.push({stage,viewport,visiblePixels:pixels,movedTo:moved,api,errors,externalRequests:requests});
      await context.close();
    }
  } finally { await browser.close(); }
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({passed:true,results},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});

async function checkTiles({page,frame,stage,mobile,errors,requests}) {
  await frame.locator('#load-state').filter({hasText:'Asset ready'}).waitFor();
  assert.equal(await frame.locator('#tile option').count(),4);
  await frame.locator('#repeat-state').filter({hasText:'Repeated 4 × 4'}).waitFor();
  await frame.locator('#tile').selectOption('wall');
  await frame.locator('#status').filter({hasText:'wall · Cell 1 · Solid'}).waitFor();
  if(mobile)await frame.locator('#repeat').tap();else await frame.locator('#repeat').click();
  await frame.locator('#repeat-state').filter({hasText:'Single tile'}).waitFor();
  const api=await frame.locator('body').evaluate(async()=>{
    const atlas=await EmberSprites.load(),canvas=document.createElement('canvas');canvas.width=canvas.height=80;
    const ctx=canvas.getContext('2d'),rows=[['grass','wall'],['water',null]];
    ctx.imageSmoothingEnabled=true;ctx.globalCompositeOperation='xor';
    const drawn=atlas.drawMap(ctx,rows,4,5,{scale:2});
    const color=(x,y)=>Array.from(ctx.getImageData(x,y,1,1).data);
    const colors=[color(4,5),color(36,5),color(4,37),color(36,37)];
    const restored=ctx.imageSmoothingEnabled&&ctx.globalCompositeOperation==='xor'&&ctx.getTransform().a===1;
    const actor=atlas.createPlayer();actor.update(100);
    const scene=await EmberSprites.createScene({version:1,entities:[{id:'terrain',asset_ref:'tiles',machine:null,required_clips:['default']}]},{tiles:EMBER_ASSET});
    const terrain=scene.createEntity('terrain');terrain.drawMap(ctx,rows);const entityDraws=scene.diagnostics()[0].draws;
    return {drawn,colors,restored,frame:actor.frame,solid:atlas.solidAt(rows,1,0),empty:atlas.solidAt(rows,1,1),entityDraws,
      previewColor:Array.from(document.querySelector('canvas').getContext('2d').getImageData(470,45,1,1).data)};
  });
  assert.deepEqual(api,{drawn:3,colors:[[48,128,64,255],[128,96,80,255],[48,80,176,255],[0,0,0,0]],
    restored:true,frame:0,solid:true,empty:false,entityDraws:3,previewColor:[128,96,80,255]});
  const viewport=mobile?'mobile':'desktop';
  await page.screenshot({path:path.join(output,stage+'-'+viewport+'.png')});
  assert.equal(await frame.locator('body').evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false,'Tile workshop must fit the viewport');
  assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
  return {stage,viewport,api,errors,externalRequests:requests};
}
