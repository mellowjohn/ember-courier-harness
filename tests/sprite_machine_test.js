const assert=require('node:assert/strict');
global.Image=class{constructor(){this.naturalWidth=128;this.naturalHeight=64;}set src(value){queueMicrotask(()=>this.onload());}};
require(process.argv[2] || '../ember_harness/asset_lab/sprite-player.js');
const state=(clip,priority,interruptible=true,on_complete=null,terminal=false,markers=[])=>({clip,priority,interruptible,on_complete,terminal,markers});
const rule=(from,to,event=null,when=[])=>({from,to,event,when});
const eq=(signal,value)=>({signal,op:'eq',value});
const machine={initial:'idle',signals:{moving:{type:'boolean',default:false},grounded:{type:'boolean',default:true},dead:{type:'boolean',default:false},vy:{type:'number',default:0}},
  states:{idle:state('idle',0),walk:state('walk',1),jump:state('jump',20),fall:state('fall',20),
    attack:state('attack',50,false,'idle',false,[{event:'hit',frame:1}]),hurt:state('hurt',100,false,'idle'),death:state('death',1000,false,null,true)},
  transitions:[rule(['*'],'death',null,[eq('dead',true)]),rule(['*'],'hurt','hurt'),rule(['*'],'attack','attack',[eq('grounded',true)]),
    rule(['*'],'jump',null,[eq('grounded',false),{signal:'vy',op:'lt',value:0}]),rule(['*'],'fall',null,[eq('grounded',false),{signal:'vy',op:'gte',value:0}]),
    rule(['*'],'walk',null,[eq('moving',true),eq('grounded',true)]),rule(['walk','jump','fall'],'idle',null,[eq('moving',false),eq('grounded',true)])]};
const spec={profile:'sprite-atlas-v1',frame_size:[32,32],grid:[4,2],frames:8,fps:10,loop:true,pivot:[.5,1],blend:'source-over',sampling:'nearest',
  animations:{idle:{frames:[0],fps:10,loop:true},walk:{frames:[1,2],fps:10,loop:true},jump:{frames:[2],fps:10,loop:true},fall:{frames:[2],fps:10,loop:true},
    attack:{frames:[3,4],fps:10,loop:false,next:'walk'},hurt:{frames:[5],fps:10,loop:false},death:{frames:[6,7],fps:10,loop:false}}};
(async()=>{
  const atlas=await EmberSprites.load({spec,png_base64:'fixture'});
  const actor=EmberSprites.createMachine(atlas,machine,{entityId:'hero'});
  actor.update(.05,{moving:true});assert.equal(actor.state,'walk');
  actor.update(0,{moving:false});assert.equal(actor.state,'idle');
  assert.deepEqual(actor.update(.05,{},['attack']),[]);assert.equal(actor.state,'attack');
  const sequence=actor.sequence;
  const hits=actor.update(.05,{moving:true},['attack','attack']);assert.equal(actor.state,'attack');assert.equal(actor.sequence,sequence);
  assert.equal(hits.length,1);assert.equal(hits[0].name,'hit');assert.equal(hits[0].entityId,'hero');
  assert.deepEqual(actor.update(0,{},['attack']),[],'Marker must not fire twice');
  actor.update(.1,{moving:false});assert.equal(actor.state,'idle','State completion must override the raw clip next');
  actor.update(.02,{},['attack']);actor.update(.02,{moving:true},['hurt']);assert.equal(actor.state,'hurt','Hurt must interrupt a locked attack');
  assert.deepEqual(actor.update(.2,{moving:false}),[],'Cancelled attacks must not deliver late damage');
  actor.update(.01,{dead:true,moving:true},['attack','hurt']);assert.equal(actor.state,'death','Death must win competing transitions');
  actor.update(5,{dead:false,moving:true},['attack','hurt']);assert.equal(actor.state,'death');assert.equal(actor.frame,7);assert(actor.completed);
  actor.reset();assert.equal(actor.state,'idle');actor.update(.01,{grounded:false,vy:-5});assert.equal(actor.state,'jump');
  actor.update(.01,{vy:5});assert.equal(actor.state,'fall');actor.update(.01,{grounded:true,moving:true});assert.equal(actor.state,'walk');
  assert.throws(()=>actor.update(.1,{moving:1}),/signal/);assert.throws(()=>actor.update(.1,{unknown:true}),/signal/);
  assert.throws(()=>actor.update(Infinity),RangeError);
  const second=EmberSprites.createMachine(atlas,machine);assert.equal(second.state,'idle');
  const before=actor.state;assert.throws(()=>actor.update(.1,{moving:false,vy:NaN}),/signal/);assert.equal(actor.state,before,'Invalid input must not partially change state');
  const registry={['a'.repeat(64)]:{spec,png_base64:'fixture'},['b'.repeat(64)]:{spec,png_base64:'fixture'}};
  const plan={version:1,entities:[{id:'hero',asset_ref:'a'.repeat(64),machine},{id:'enemy',asset_ref:'b'.repeat(64),machine},
    {id:'effect',asset_ref:'b'.repeat(64),machine:null,required_clips:['attack']}]};
  const scene=await EmberSprites.createScene(plan,registry),hero=scene.createEntity('hero'),enemy=scene.createEntity('enemy');
  hero.update(.05,{moving:true});assert.equal(enemy.state,'idle');assert.equal(hero.state,'walk');
  const ctx={save(){},restore(){},translate(){},scale(){},drawImage(){}};
  hero.draw(ctx,10,20);enemy.draw(ctx,30,40);
  assert.deepEqual(scene.diagnostics().map(d=>[d.entityId,d.assetRef,d.draws]),[['hero','a'.repeat(64),1],['enemy','b'.repeat(64),1]]);
  hero.dispose();assert.equal(scene.diagnostics().length,1);assert.throws(()=>hero.update(0),/disposed/);
  assert.throws(()=>scene.createEntity('missing'),/Unknown/);
  const effect=scene.createEntity('effect');assert.equal(effect.frame,3);effect.update(.2);assert(effect.completed);assert.equal(effect.frame,4);
  console.log('State priorities, guarded movement, airborne transitions, locked attacks, one-shot hit events, cancellation, terminal death, reset and multi-atlas instances passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
