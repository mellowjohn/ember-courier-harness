// Deterministic timing and drawing contract checks; the browser rehearsal decodes real PNGs.
const assert = require('node:assert/strict');
const fs = require('node:fs');
global.Image = class {
  constructor() { this.naturalWidth = 128; this.naturalHeight = 64; }
  set src(value) { queueMicrotask(() => value.endsWith('broken') ? this.onerror() : this.onload()); }
};
require(process.argv[2] || '../ember_harness/asset_lab/sprite-player.js');
const spec = {profile:'sprite-atlas-v1', frame_size:[32,32], grid:[4,2], frames:8, fps:10, loop:false,
  pivot:[.25,1], blend:'lighter', sampling:'nearest', default_animation:'idle', animations:{
    idle:{frames:[0,1],fps:4,loop:true}, walk:{frames:[2,3,4],fps:10,loop:true},
    attack:{frames:[5,6],fps:10,loop:false,next:'idle'}, death:{frames:[6,7],fps:10,loop:false}}};
(async () => {
  const atlas = await EmberSprites.load({spec,png_base64:'fixture'}), a = atlas.createPlayer(), b = atlas.createPlayer('walk');
  const noDefault = {...spec,animations:{attack:spec.animations.attack,idle:spec.animations.idle}}; delete noDefault.default_animation;
  assert.equal((await EmberSprites.load({spec:noDefault,png_base64:'fixture'})).createPlayer().animation,'idle');
  assert.equal(a.animation,'idle'); assert.equal(b.frame,2);
  a.update(.25); assert.equal(a.frame,1); a.play('idle'); assert.equal(a.frame,1,'Repeated state selection must not reset animation');
  a.play('idle',{restart:true}); assert.equal(a.frame,0);
  a.play('attack'); assert.deepEqual(a.update(.35),['attack']);
  assert.equal(a.animation,'idle'); assert.equal(a.frame,0); a.update(.1); assert.equal(a.frame,1,'Overflow time must carry to the next clip');
  assert.equal(b.frame,2,'Players must not share animation clocks'); b.update(.2); assert.equal(b.frame,4);
  b.update(.1); assert.equal(b.frame,2,'Loop must wrap at its exact duration');
  a.play('death'); assert.deepEqual(a.update(.2),['death']); assert.equal(a.frame,7); assert.equal(a.completed,true);
  assert.deepEqual(a.update(100),[],'Held clips emit completion once'); assert.equal(a.frame,7);
  a.seek(0); assert.equal(a.completed,false); assert.equal(a.frame,6); a.update(.1); assert.equal(a.frame,7);
  for (const value of [-1,NaN,Infinity]) assert.throws(() => a.update(value),RangeError);
  assert.throws(() => a.play('missing'),/Unknown/); assert.throws(() => a.seek(2),RangeError);
  const single = atlas.createPlayer('attack'), partitioned = atlas.createPlayer('attack');
  single.update(.8); for (let i=0;i<32;i++) partitioned.update(.025);
  assert.equal(partitioned.animation,single.animation); assert.equal(partitioned.frame,single.frame);
  const calls = [], ctx = {save(){calls.push(['save']);},restore(){calls.push(['restore']);},translate(...args){calls.push(['translate',...args]);},
    scale(...args){calls.push(['scale',...args]);},drawImage(...args){calls.push(['draw',...args.slice(1)]);}};
  a.draw(ctx,100,200,{scale:2,flipX:true});
  assert.deepEqual(calls,[['save'],['translate',100,200],['scale',-1,1],['draw',96,32,32,32,-16,-64,64,64],['restore']]);
  assert.equal(ctx.imageSmoothingEnabled,false); assert.equal(ctx.globalCompositeOperation,'lighter');
  const leftSource = (await EmberSprites.load({spec:{...spec,facing:'left'},png_base64:'fixture'})).createPlayer();
  calls.length = 0;
  leftSource.draw(ctx,0,0,{facing:'left'});
  leftSource.draw(ctx,0,0,{facing:'right'});
  assert.deepEqual(calls.filter(c=>c[0]==='scale'),[['scale',1,1],['scale',-1,1]]);
  assert.throws(()=>leftSource.draw(ctx,0,0,{facing:'right',flipX:false}),/Directional drawing/);
  assert.throws(()=>a.draw(ctx,0,0,{facing:'right'}),/Directional drawing/);
  ctx.drawImage = () => {throw Error('draw failure');};
  assert.throws(() => a.draw(ctx,0,0),/draw failure/); assert.deepEqual(calls.at(-1),['restore']);
  const legacySpec = {...spec}; delete legacySpec.animations; delete legacySpec.default_animation;
  const legacy = (await EmberSprites.load({spec:legacySpec,png_base64:'fixture'})).createPlayer();
  assert.equal(legacy.animation,'default'); legacy.update(.8); assert.equal(legacy.frame,7); assert(legacy.completed);
  await assert.rejects(EmberSprites.load({spec,png_base64:'broken'}),/decoded/);
  await assert.rejects(EmberSprites.load({spec:{...spec,grid:[1,1]},png_base64:'fixture'}),/dimensions/);
  const cycleSpec = {...spec,animations:{a:{frames:[0],fps:60,loop:false,next:'b'},b:{frames:[1],fps:60,loop:false,next:'a'}},default_animation:'a'};
  const cycling = (await EmberSprites.load({spec:cycleSpec,png_base64:'fixture'})).createPlayer();
  assert(cycling.update(1e6).length <= 256,'A long suspended-tab interval must stay bounded');
  console.log('Sprite player timing, clips, independent instances, draw geometry, legacy playback and load failures passed.');
})().catch(error => {console.error(error); process.exitCode=1;});
