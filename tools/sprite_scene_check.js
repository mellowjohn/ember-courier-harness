const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
async function checkReview(browser,output){
  const context=await browser.newContext({viewport:{width:1400,height:1000}}),page=await context.newPage(),errors=[];
  try{
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(process.env.EMBER_BROWSER_URL+'#'+process.env.EMBER_BROWSER_TOKEN);
    await require('./workspace_browser').view(page,'chat');
    const prepare=page.locator('.message.assistant').getByRole('button',{name:'Generate artwork & prepare game changes',exact:true});
    await prepare.waitFor();await prepare.click();
    const accept=page.getByRole('button',{name:'Accept 2 assets & play',exact:true});await accept.waitFor();
    const artwork=page.locator('.message.assistant').last().locator('.sprite-inventory');
    assert.equal(await artwork.getAttribute('open'),'');
    assert.equal(await artwork.locator('.artwork-preview img').count(),2);
    const planned=page.locator('.message.assistant').first().locator('.sprite-inventory');
    assert.equal(await planned.locator('[data-entity-id="hero"] img').count(),0);
    assert.match(await planned.locator('[data-entity-id="hero"]').innerText(),/Not generated yet/);
    assert.equal(await planned.locator('[data-entity-id="impact"] img').count(),1);
    await page.waitForFunction(()=>[...document.querySelectorAll('.message .artwork-preview img')].every(img=>img.complete&&img.naturalWidth>0));
    assert.equal(await page.locator('#review .artwork-preview img').count(),2);
    await page.waitForFunction(()=>[...document.querySelectorAll('#review .artwork-preview img')].length===2&&[...document.querySelectorAll('#review .artwork-preview img')].every(img=>img.complete&&img.naturalWidth>0));
    const pending=await page.evaluate(async token=>{
      const headers={'X-Ember-Token':token},state=await fetch('/api/state',{headers}).then(r=>r.json()),request=state.build.requests.find(r=>!r.decision);
      return fetch('/api/proposal-preview?'+new URLSearchParams({session_id:state.session.id,ref:request.ref}),{headers}).then(r=>r.json());
    },process.env.EMBER_BROWSER_TOKEN);
    assert(pending.html);fs.writeFileSync(path.join(output,'pending-preview.json'),JSON.stringify(pending));
    await require('./workspace_browser').view(page,'assets');
    const known=page.locator('#known-asset-list > article[data-asset-ref] .artwork-preview');
    assert.equal(await known.count(),2);
    await page.waitForFunction(()=>[...document.querySelectorAll('#known-asset-list > article .artwork-preview img')].every(img=>img.complete&&img.naturalWidth>0));
    const downloaded=page.waitForEvent('download');await known.first().getByRole('link',{name:'Download PNG',exact:true}).click();
    const download=await downloaded;assert.match(download.suggestedFilename(),/\.png$/);await download.saveAs(path.join(output,'downloaded-artwork.png'));
    await page.reload();await require('./workspace_browser').view(page,'chat');await accept.waitFor();
    await page.waitForFunction(()=>[...document.querySelectorAll('.message .artwork-preview img')].length===3&&[...document.querySelectorAll('.message .artwork-preview img')].every(img=>img.complete&&img.naturalWidth>0));
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Artwork cards must fit on mobile');
    await artwork.screenshot({path:path.join(output,'artwork-mobile.png')});
    await page.setViewportSize({width:1400,height:1000});
    const list=page.getByRole('group',{name:'Accept each changed artwork'}),boxes=list.getByRole('checkbox');
    assert.equal(await boxes.count(),2);assert(await accept.isDisabled());
    await page.waitForTimeout(1500);assert(await accept.isDisabled(),'Polling must not bypass artwork choices');
    await boxes.nth(0).check();assert(await accept.isDisabled());
    await boxes.nth(1).check();assert(await accept.isEnabled());
    await page.getByRole('button',{name:'Try proposed changes',exact:true}).click();
    await page.frameLocator('iframe[title="Proposed browser prototype · not applied"]').locator('#load-state').filter({hasText:'Asset ready'}).waitFor();
    await page.screenshot({path:path.join(output,'asset-review.png')});
    await accept.click();await page.getByText('Version 2 · Approved and ready to play',{exact:true}).waitFor();
    await page.frameLocator('iframe[title="Approved browser prototype"]').locator('#load-state').filter({hasText:'Asset ready'}).waitFor();
    assert.deepEqual(errors,[]);
    return {stage:'asset-review',reusedArtworkPreviews:2,plannedArtworkNotGenerated:true,knownAssetPreviews:2,
      prepareFromSavedPlan:true,pngDownload:true,previewsSurviveReload:true,mobileArtworkFits:true,
      individualArtworkChoices:2,unappliedPreview:true,appliedAfterExplicitAcceptance:true,errors};
  }finally{await context.close();}
}

async function checkGame({context,page,frame,stage,mobile,output,errors,requests}){
  const state=frame.locator('#state');
  await frame.locator('#load-state').filter({hasText:'Asset ready'}).waitFor();
  await state.filter({hasText:'idle'}).waitFor();
  // Loading finishes before the first animation frame paints the actual atlas.
  await frame.locator('canvas').evaluate(canvas=>new Promise(resolve=>{
    const painted=()=>{if(canvas.getContext('2d').getImageData(160,196,1,1).data[3])resolve();else requestAnimationFrame(painted);};painted();
  }));
  const pixel=await frame.locator('canvas').evaluate(canvas=>Array.from(canvas.getContext('2d').getImageData(160,196,1,1).data));
  assert([40,55].includes(pixel[0])&&pixel[1]===100&&pixel[2]===160&&pixel[3]===255,'Actual bound courier pixels must replace its old rectangle');
  const initial=Number(await frame.locator('#position').textContent());
  if(mobile){
    const box=await frame.locator('#right').boundingBox(),client=await context.newCDPSession(page);
    await client.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:box.x+box.width/2,y:box.y+box.height/2}]});
    await state.filter({hasText:'walk'}).waitFor();await page.waitForTimeout(220);
    await client.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  }else{
    await frame.locator('body').click({position:{x:5,y:5}});await page.keyboard.down('ArrowRight');
    await state.filter({hasText:'walk'}).waitFor();await page.waitForTimeout(220);await page.keyboard.up('ArrowRight');
  }
  const moved=Number(await frame.locator('#position').textContent());assert(moved>initial+20);
  await state.filter({hasText:'idle'}).waitFor();
  assert.equal(await frame.locator('#score').textContent(),'7');assert.equal(await frame.locator('#health').textContent(),'3');
  await state.evaluate(el=>{globalThis.__jumpStates=[];const record=()=>{const value=el.textContent;if(globalThis.__jumpStates.at(-1)!==value)globalThis.__jumpStates.push(value)};record();new MutationObserver(record).observe(el,{childList:true,characterData:true,subtree:true});});
  if(mobile)await frame.locator('#jump').tap();else await page.keyboard.press('ArrowUp');
  await page.waitForTimeout(1100);
  const jumpStates=await state.evaluate(()=>globalThis.__jumpStates);
  assert(jumpStates.includes('jump')&&jumpStates.includes('fall'),'Physics must drive both airborne states: '+jumpStates.join(', '));
  assert.equal(await state.textContent(),'idle');
  await frame.locator('#attack').click();await state.filter({hasText:'attack'}).waitFor();
  await frame.locator('#attack').click();await frame.locator('#attack').click();
  await frame.locator('#hits').filter({hasText:'1'}).waitFor();
  const impact=await frame.locator('body').evaluate(()=>EmberSprites.diagnostics().find(i=>i.entityId==='impact'&&i.draws>0));
  assert(impact,'The hit must draw its independently bound impact atlas');
  const hero=await frame.locator('body').evaluate(()=>EmberSprites.diagnostics().find(i=>i.entityId==='hero'));
  assert.notEqual(hero.assetRef,impact.assetRef,'Character and effect must use their intended different atlases');
  await state.filter({hasText:'idle'}).waitFor();await page.waitForTimeout(400);
  assert.equal(await frame.locator('#hits').textContent(),'1');assert.equal(await frame.locator('#score').textContent(),'8');assert.equal(await frame.locator('#health').textContent(),'2');
  await frame.locator('#attack').click();await state.filter({hasText:'attack'}).waitFor();await frame.locator('#hurt').click();
  await state.filter({hasText:'hurt'}).waitFor();await state.filter({hasText:'idle'}).waitFor();await page.waitForTimeout(400);
  assert.equal(await frame.locator('#hits').textContent(),'1','An interrupted attack must not damage the target');
  await frame.locator('#attack').click();await state.filter({hasText:'attack'}).waitFor();await frame.locator('#die').click();
  await state.filter({hasText:'death'}).waitFor();await page.waitForTimeout(500);
  await frame.locator('#attack').click();await frame.locator('#hurt').click();
  assert.equal(await state.textContent(),'death');assert.equal(await frame.locator('#hits').textContent(),'1');
  const held=await frame.locator('body').evaluate(()=>EmberSprites.diagnostics().find(i=>i.entityId==='hero'));
  assert(held.completed);assert.equal(held.frame,11);
  await page.screenshot({path:path.join(output,stage+'-'+(mobile?'mobile':'desktop')+'.png')});
  await frame.locator('#respawn').click();await state.filter({hasText:'idle'}).waitFor();
  assert.equal(await frame.locator('body').evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false);
  assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
  return {stage,viewport:mobile?'mobile':'desktop',actualCourierPixel:pixel,movedTo:moved,jumpFallLanding:true,
    singleDamageEvent:true,cancelledAttackNoDamage:true,terminalDeathHeld:true,explicitRespawn:true,hero,impact,held,errors,externalRequests:requests};
}
module.exports={checkReview,checkGame};
