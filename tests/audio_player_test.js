// Deterministic audio lifecycle tests. Real signal checks live in audio_check.js.
const assert = require('node:assert/strict');
class Param { constructor(){this.value=1;} setValueAtTime(){} setTargetAtTime(){} linearRampToValueAtTime(){} exponentialRampToValueAtTime(){} }
const nodes=[];
class Node {
  constructor(){this.gain=new Param();this.frequency=new Param();this.pan=new Param();this.threshold=new Param();this.ratio=new Param();this.disconnected=false; nodes.push(this);}
  connect(){} disconnect(){this.disconnected=true;} start(){this.started=true;} stop(time){this.stopped=true;if(time===undefined)this.onended?.();}
}
let count=0, latest;
global.AudioContext=class {
  constructor(){count++; latest=this; this.state='suspended';this.currentTime=0;this.sampleRate=8000;this.destination=new Node();}
  createGain(){return new Node();} createOscillator(){return new Node();} createStereoPanner(){return new Node();}
  createDynamicsCompressor(){return new Node();} createBufferSource(){return new Node();} createBiquadFilter(){return new Node();}
  createBuffer(channels,length){return {getChannelData:()=>new Float32Array(length)};}
  addEventListener(){} removeEventListener(){}
  async resume(){this.state='running';} async suspend(){this.state='suspended';} async close(){this.state='closed';}
};
const listeners=new Map();
global.document={hidden:false,addEventListener:(event,fn)=>listeners.set(event,fn),removeEventListener:event=>listeners.delete(event)};
require(process.argv[2] || '../ember_harness/asset_lab/ember-audio.js');
(async()=>{
  const audio=EmberAudio.create();
  assert.equal(count,0,'Creating a mixer must never autoplay or allocate a context');
  assert.equal(audio.play('jump'),false); assert.equal(audio.startMusic(),false); assert.equal(count,0);
  const unlocked=await Promise.all([audio.unlock(),audio.unlock()]); assert.deepEqual(unlocked,[true,true]); assert.equal(count,1);
  assert.equal(audio.play('pickup'),true); assert.equal(audio.play('pickup'),false,'Repeated frame triggers are throttled');
  latest.currentTime+=.2; assert.equal(audio.play('pickup'),true);
  for(let i=0;i<80;i++) audio.tone({frequency:220}); assert.equal(audio.diagnostics().activeVoices,32);
  audio.stopAll(); assert.equal(audio.diagnostics().activeVoices,0);
  assert.equal(audio.startMusic('explore'),true); assert.equal(audio.startAmbience('wind'),true);
  const firstAmbience=nodes.findLast(n=>n.started && !n.stopped);
  audio.startAmbience('embers'); assert.equal(firstAmbience.stopped,true);
  audio.setMuted(true);audio.setVolume('music',.8); assert.equal(audio.diagnostics().muted,true);
  assert.equal(audio.diagnostics().volumes.music,.8);
  audio.setPaused(true);assert.equal(latest.state,'suspended');assert.equal(audio.play('jump'),false);
  audio.setPaused(false);assert.equal(latest.state,'running');
  document.hidden=true;listeners.get('visibilitychange')(); assert.equal(latest.state,'suspended');
  assert.equal(audio.tone({}),false);document.hidden=false;listeners.get('visibilitychange')();assert.equal(latest.state,'running');
  assert.throws(()=>audio.setVolume('music',NaN),RangeError);
  assert.throws(()=>audio.setVolume('master',2),RangeError);
  assert.throws(()=>audio.setVolume('bad',.2),RangeError);
  assert.throws(()=>audio.setMuted('false'),TypeError);
  assert.throws(()=>audio.tone({duration:Infinity}),RangeError);
  assert.throws(()=>audio.startMusic({bpm:120,steps:[[Infinity]]}),RangeError);
  assert.throws(()=>audio.startMusic({bpm:120,steps:[[60.5]]}),RangeError);
  assert.throws(()=>audio.startMusic('missing'),RangeError);
  assert.throws(()=>audio.play('missing'),RangeError);
  audio.dispose();audio.dispose();assert.equal(latest.state,'closed');assert.equal(listeners.size,0);
  assert.equal(await audio.unlock(),false);assert.equal(audio.diagnostics().activeVoices,0);
  assert.equal(audio.diagnostics().music,false);assert.equal(audio.diagnostics().state,'disposed');
  const second=EmberAudio.create(); await second.unlock();assert.equal(count,2);assert.equal(second.diagnostics().muted,false);second.dispose();
  delete global.AudioContext;
  const unavailable=EmberAudio.create();assert.equal(await unavailable.unlock(),false);assert.equal(unavailable.play('jump'),false);unavailable.dispose();
  console.log('Audio lifecycle, limits, mixing, looping, pause and unsupported-browser checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
