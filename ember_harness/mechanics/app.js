/* Original reference interface; recipe changes only replace mechanic-config.js. */
(()=>{'use strict';
  const config=EMBER_MECHANIC_CONFIG,api=EmberMechanics,game=api.create(config.settings),canvas=document.querySelector('#scene'),ctx=canvas.getContext('2d');
  let paused=false,last=null,input={left:false,right:false},pointers=new Map();
  const by=id=>document.getElementById(id);
  function observe(){const s=game.snapshot();by('position').textContent=String(Number(s.x.toFixed(3)));by('velocity').textContent=String(Number(s.vx.toFixed(3)));by('grounded').textContent=s.grounded?'yes':'no';by('jump-count').textContent=String(s.jumpCount);by('scenario-report').textContent=JSON.stringify({profile:api.PROFILE,configuration_sha256:config.sha256,step_ms:api.STEP_MS,...s},null,2);by('status').textContent=s.x>900?'The lantern is lit. Restart to try another route.':paused?'Fixed-step scenario · use Advance, then inspect the observations.':'Carry your light across the broken trail.';}
  function draw(){const s=game.snapshot();ctx.clearRect(0,0,1000,440);ctx.fillStyle='#203c42';for(let i=0;i<13;i++){const x=i*90;ctx.beginPath();ctx.moveTo(x,300);ctx.lineTo(x+45,160+(i%3)*18);ctx.lineTo(x+100,300);ctx.fill();}ctx.fillStyle='#415653';for(const p of api.platforms){ctx.fillRect(p.left,p.top,p.right-p.left,440-p.top);ctx.fillStyle='#b7b48a';ctx.fillRect(p.left,p.top,p.right-p.left,5);ctx.fillStyle='#415653';}ctx.fillStyle='#ffd88d';ctx.fillRect(920,310,8,50);ctx.beginPath();ctx.arc(924,306,15,0,Math.PI*2);ctx.fill();ctx.fillStyle='#ffb65a';ctx.shadowColor='#ffb65a';ctx.shadowBlur=16;ctx.beginPath();ctx.roundRect(s.x,s.y,24,32,9);ctx.fill();ctx.shadowBlur=0;ctx.fillStyle='#27382d';ctx.fillRect(s.x+15,s.y+10,3,4);observe();}
  function clear(){input={left:false,right:false};pointers.clear();game.clearInput();}
  function restart(){paused=false;last=null;clear();game.reset();draw();canvas.focus({preventScroll:true});}
  // Touch compatibility clicks can be retargeted outside a button in an
  // opaque hosted iframe. Use the real pointer action exactly once; retain
  // detail-zero click activation for keyboard and assistive technology.
  function activate(id,action){const button=by(id);button.addEventListener('pointerdown',event=>{if(event.button!==0)return;event.preventDefault();action();});button.onclick=event=>{if(event.detail===0)action();};}
  activate('restart',restart);
  const keys={ArrowLeft:'left',a:'left',ArrowRight:'right',d:'right'};
  addEventListener('keydown',event=>{if(event.target instanceof HTMLInputElement)return;if(keys[event.key]){event.preventDefault();if(!event.repeat)input[keys[event.key]]=true;}else if(event.code==='Space'||event.key===' '){if(event.target instanceof HTMLButtonElement&&event.target.id!=='jump')return;event.preventDefault();if(!event.repeat)game.pressJump();}else if(event.key==='r'){event.preventDefault();restart();}});
  addEventListener('keyup',event=>{if(keys[event.key]){event.preventDefault();input[keys[event.key]]=false;}if(event.code==='Space'||event.key===' ')game.releaseJump();});
  for(const action of ['left','right','jump']){const button=by(action);button.addEventListener('pointerdown',event=>{event.preventDefault();button.setPointerCapture(event.pointerId);pointers.set(event.pointerId,action);if(action==='jump')game.pressJump();else input[action]=true;});
    const release=event=>{const active=pointers.get(event.pointerId);pointers.delete(event.pointerId);if(!active)return;if(active==='jump')game.releaseJump();else input[active]=[...pointers.values()].includes(active);};button.addEventListener('pointerup',release);button.addEventListener('pointercancel',release);button.addEventListener('lostpointercapture',release);}
  addEventListener('blur',clear);document.addEventListener('visibilitychange',()=>{if(document.hidden){clear();last=null;}});
  for(const [id,name] of [['scenario-start','start'],['scenario-coyote','coyote'],['scenario-buffer','buffer']])activate(id,()=>{clear();game.scenario(name);paused=name!=='start';last=null;draw();canvas.focus({preventScroll:true});});
  for(const [id,count] of [['step-one',1],['step-six',6],['step-twelve',12]])activate(id,()=>{paused=true;game.advanceSteps(count,input);draw();});
  activate('check-mechanics',()=>{const report=api.verify(config);by('mechanic-result').textContent=report.outcome;by('check-list').replaceChildren();for(const row of report.checks){const p=document.createElement('p');p.textContent=row.id+': ';const result=document.createElement('output');result.id='check-'+row.id;result.textContent=row.status;p.append(result);by('check-list').append(p);}by('mechanic-report').textContent=JSON.stringify(report,null,2);});
  function frame(now){if(last===null)last=now;const elapsed=Math.min(.25,Math.max(0,(now-last)/1000));last=now;if(!paused){game.advanceFrame(elapsed,input);draw();}requestAnimationFrame(frame);}
  draw();requestAnimationFrame(frame);
})();
