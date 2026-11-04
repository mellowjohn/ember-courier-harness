const assert=require('node:assert/strict');
global.Image=class{set src(value){[this.naturalWidth,this.naturalHeight]=value.endsWith('blob')?[128,96]:[32,32];queueMicrotask(()=>this.onload());}};
require(process.argv[2] || '../ember_harness/asset_lab/sprite-player.js');
const spec={profile:'sprite-atlas-v1',kind:'tileset',frame_size:[16,16],grid:[2,2],frames:4,fps:1,loop:false,
  pivot:[.5,1],blend:'source-over',sampling:'nearest',tileset:{seamless:true,tiles:{
    grass:{frame:0,solid:false},wall:{frame:1,solid:true},water:{frame:2,solid:true},path:{frame:3,solid:false}}}};
(async()=>{
  const data={spec,png_base64:'fixture'},atlas=await EmberSprites.load(data),calls=[];
  const ctx={save(){calls.push(['save']);},restore(){calls.push(['restore']);},translate(...a){calls.push(['translate',...a]);},
    scale(...a){calls.push(['scale',...a]);},drawImage(...a){calls.push(['draw',...a.slice(1)]);}};
  atlas.drawTile(ctx,'path',10,20,{scale:2,flipX:true});
  assert.deepEqual(calls,[['save'],['translate',42,20],['scale',-1,1],['draw',16,16,16,16,0,0,32,32],['restore']]);
  assert.equal(ctx.imageSmoothingEnabled,false);
  const player=atlas.createPlayer();player.update(100);assert.equal(player.frame,0,'Static tiles must never cycle through terrain');
  calls.length=0;
  const rows=[['grass',null],[0,'wall']];
  assert.equal(atlas.drawMap(ctx,rows,5,6,{scale:2}),3);
  assert.deepEqual(calls.filter(c=>c[0]==='translate'),[['translate',5,6],['translate',5,38],['translate',37,38]]);
  assert.equal(atlas.solidAt(rows,1,1),true);assert.equal(atlas.solidAt(rows,0,1),false);
  assert.equal(atlas.solidAt([[2]],0,0),true);assert.equal(atlas.solidAt(rows,1,0),false);assert.equal(atlas.solidAt(rows,-1,0),false);
  assert.throws(()=>atlas.solidAt(rows,.5,0),RangeError);
  for(const rows of [[],[[]],[[0],[1,2]],[[0],,],[[0,'missing']],[[false]],[[4]],[[undefined]],[[,]],Array.from({length:65},()=>Array(256).fill(0))]){
    calls.length=0;assert.throws(()=>atlas.drawMap(ctx,rows),RangeError);assert.equal(calls.length,0,'Reject invalid maps before any draw');
  }
  for(const scale of [0,-1,NaN,Infinity,1e308]){
    assert.throws(()=>atlas.drawMap(ctx,[[0]],0,0,{scale}),RangeError);
    assert.throws(()=>atlas.drawTile(ctx,0,0,0,{scale}),RangeError);
  }
  assert.throws(()=>atlas.drawTile(ctx,'unknown',0,0),RangeError);
  calls.length=0;
  const variants={grass:{2:'wall',8:'path'}};
  atlas.drawMap(ctx,[['grass',0]],0,0,{variants});
  assert.deepEqual(calls.filter(c=>c[0]==='draw').map(c=>c.slice(1,3)),[[16,0],[16,16]]);
  calls.length=0;
  assert.throws(()=>atlas.drawMap(ctx,[['grass']],0,0,{variants:{grass:{256:'wall'}}}),/neighbor mask/);
  assert.deepEqual(calls,[]);
  const blob=await EmberSprites.load({spec:{...spec,frames:47,grid:[8,6],tileset:{seamless:true,
    edge_mode:'blob',tiles:{ground:{frame:46,solid:true}}}},png_base64:'blob'});
  const ground=[['ground','ground','ground'],['ground','ground','ground'],['ground','ground','ground']];
  blob.drawMap(ctx,ground);
  assert.deepEqual(calls.filter(c=>c[0]==='draw')[4].slice(1,3),[96,80],'A surrounded cell draws frame 46');
  calls.length=0;
  ground[0][2]=null;
  blob.drawMap(ctx,ground);
  assert.deepEqual(calls.filter(c=>c[0]==='draw')[3].slice(1,3),[80,80],'A missing diagonal selects a concave corner');
  calls.length=0;
  blob.drawMap(ctx,[['ground',null,'ground']]);
  assert.deepEqual(calls.filter(c=>c[0]==='draw').map(c=>c.slice(1,3)),[[0,0],[0,0]]);
  assert.equal(blob.solidAt(ground,2,0),false);
  assert.equal(blob.solidAt(ground,1,1),true);
  ctx.drawImage=()=>{throw Error('failed');};assert.throws(()=>atlas.drawTile(ctx,0,0,0),/failed/);assert.deepEqual(calls.at(-1),['restore']);
  ctx.drawImage=()=>{};
  const legacy={...spec};delete legacy.tileset;
  const old=await EmberSprites.load({spec:legacy,png_base64:'fixture'});assert.equal(old.tiles['tile-3'].frame,3);
  const scene=await EmberSprites.createScene({version:1,entities:[{id:'terrain',asset_ref:'terrain',required_clips:['default'],machine:null}]},{terrain:data});
  const terrain=scene.createEntity('terrain');assert.equal(terrain.drawMap(ctx,rows),3);terrain.drawTile(ctx,'grass',0,0);
  assert.equal(terrain.solidAt(rows,1,1),true);assert.equal(scene.diagnostics()[0].draws,4);
  terrain.dispose();assert.deepEqual(scene.diagnostics(),[]);assert.throws(()=>terrain.drawMap(ctx,rows),/disposed/);
  console.log('Static tile drawing, map placement, collision hints, legacy atlases and entity diagnostics passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
