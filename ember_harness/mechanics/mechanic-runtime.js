/* Original fixed-step reference physics. Shared by browser play and bounded checks. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.EmberMechanics=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const HZ=120,DT=1/HZ,STEP_MS=1000/HZ,PROFILE='ember-platformer-v1',EPS=1e-8;
  const BASE={max_speed:240,acceleration_ms:0,stopping_ms:0,reversal_multiplier:1,coyote_ms:0,jump_buffer_ms:0};
  const PLATFORM=[{left:0,right:300,top:360},{left:390,right:1000,top:360},{left:520,right:640,top:280}];
  const move=(v,target,amount)=>v<target?Math.min(target,v+amount):Math.max(target,v-amount);
  function parameters(value){
    if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).sort().join()!==Object.keys(BASE).sort().join())throw Error('Use the declared mechanic settings');
    for(const [name,v] of Object.entries(value))if(typeof v!=='number'||!Number.isFinite(v))throw Error('Settings must be finite numbers');
    if(value.max_speed<60||value.max_speed>480||value.acceleration_ms<0||value.acceleration_ms>600||value.stopping_ms<0||value.stopping_ms>600||value.reversal_multiplier<1||value.reversal_multiplier>5||value.coyote_ms<0||value.coyote_ms>200||value.jump_buffer_ms<0||value.jump_buffer_ms>200)throw Error('Settings exceed reference limits');
    for(const name of ['acceleration_ms','stopping_ms','coyote_ms','jump_buffer_ms'])if(!Number.isInteger(value[name]))throw Error('Use whole milliseconds');
    return {...value};
  }
  function create(value){
    const settings=parameters(value||BASE);
    let state,accumulator=0;
    function reset(){state={tick:0,x:40,y:328,vx:0,vy:0,grounded:true,jumpCount:0,lastGroundedTick:0,coyoteAvailable:true,pendingJump:false,queuedAt:0,jumpHeld:false,left:false,right:false};accumulator=0;return snapshot();}
    function snapshot(){return {...state,time_ms:state.tick*STEP_MS};}
    function pressJump(){if(!state.jumpHeld){state.pendingJump=true;state.queuedAt=state.tick;}state.jumpHeld=true;}
    function releaseJump(){state.jumpHeld=false;}
    function clearInput(){state.left=false;state.right=false;state.jumpHeld=false;state.pendingJump=false;}
    function launch(){state.vy=-420;state.grounded=false;state.jumpCount++;state.pendingJump=false;state.coyoteAvailable=false;}
    function step(input){
      if(input!==undefined){if(!input||typeof input!=='object'||Object.keys(input).some(k=>!['left','right','jump'].includes(k))||Object.values(input).some(v=>typeof v!=='boolean'))throw Error('Use bounded directional input');
        if('left'in input)state.left=input.left;if('right'in input)state.right=input.right;
        if('jump'in input){if(input.jump)pressJump();else releaseJump();}}
      if(state.grounded){state.lastGroundedTick=state.tick;state.coyoteAvailable=true;}
      const age=(state.tick-state.queuedAt)*STEP_MS;
      const fresh=state.pendingJump&&age<EPS;
      const buffered=state.pendingJump&&(fresh||(settings.jump_buffer_ms>0&&age<=settings.jump_buffer_ms+EPS));
      const coyote=state.coyoteAvailable&&(state.grounded||(settings.coyote_ms>0&&(state.tick-state.lastGroundedTick)*STEP_MS<=settings.coyote_ms+EPS));
      if(buffered&&coyote)launch();
      const direction=Number(state.right)-Number(state.left),cap=settings.max_speed;
      if(direction===0){state.vx=settings.stopping_ms===0?0:move(state.vx,0,cap/(settings.stopping_ms/1000)*DT);}
      else if(state.vx*direction<0){state.vx=settings.stopping_ms===0?0:move(state.vx,0,cap/(settings.stopping_ms/1000)*settings.reversal_multiplier*DT);}
      else state.vx=settings.acceleration_ms===0?direction*cap:move(state.vx,direction*cap,cap/(settings.acceleration_ms/1000)*DT);
      state.x=Math.max(0,Math.min(976,state.x+state.vx*DT));
      const oldBottom=state.y+32;
      state.vy+=1000*DT;state.y+=state.vy*DT;state.grounded=false;
      for(const platform of PLATFORM){if(state.x+24>platform.left&&state.x<platform.right&&state.vy>=0&&oldBottom<=platform.top+EPS&&state.y+32>=platform.top){state.y=platform.top-32;state.vy=0;state.grounded=true;state.lastGroundedTick=state.tick;state.coyoteAvailable=true;break;}}
      if(state.grounded&&state.pendingJump&&settings.jump_buffer_ms>0&&age<=settings.jump_buffer_ms+EPS)launch();
      if(state.pendingJump&&age>settings.jump_buffer_ms+EPS)state.pendingJump=false;
      if(state.y>600){reset();return snapshot();}
      state.tick++;return snapshot();
    }
    function advanceSteps(count,input){if(!Number.isInteger(count)||count<0||count>600)throw Error('Advance at most 600 explicit simulation steps');for(let i=0;i<count;i++)step(input);return snapshot();}
    function advanceFrame(seconds,input){if(typeof seconds!=='number'||!Number.isFinite(seconds)||seconds<0||seconds>0.25)throw Error('Frame duration exceeds the bounded reference limit');accumulator+=seconds;let steps=0;while(accumulator+EPS>=DT){step(input);accumulator=Math.max(0,accumulator-DT);steps++;}return {state:snapshot(),steps};}
    function scenario(name){reset();if(name==='start')return snapshot();
      if(name==='coyote'){Object.assign(state,{x:310,y:328,vx:0,vy:0,grounded:false,lastGroundedTick:0,coyoteAvailable:true});}
      else if(name==='buffer'){Object.assign(state,{x:80,y:320,vx:0,vy:160,grounded:false,lastGroundedTick:-1000,coyoteAvailable:false});}
      else if(name==='landing-next'){Object.assign(state,{x:80,y:327,vx:0,vy:120,grounded:false,lastGroundedTick:-1000,coyoteAvailable:false});}
      else throw Error('Choose a fixed reference scenario');return snapshot();
    }
    reset();return {settings,snapshot,reset,step,advanceSteps,advanceFrame,pressJump,releaseJump,clearInput,scenario,get state(){return state;}};
  }
  function verify(config){
    const settings=parameters(config.settings),checks=[];
    const add=(id,passed,observed)=>checks.push({id,status:passed?'passed':'failed',observed});
    let m=create(settings);const ramp=Math.max(1,Math.ceil(settings.acceleration_ms/STEP_MS-EPS));
    const first=m.step({right:true}).vx;m.advanceSteps(ramp-1,{right:true});
    add('acceleration',Math.abs(m.state.vx-settings.max_speed)<EPS&&(settings.acceleration_ms===0||first<settings.max_speed),{first_velocity:first,full_velocity:m.state.vx,steps:ramp,configured_ms:settings.acceleration_ms});
    const stop=Math.max(1,Math.ceil(settings.stopping_ms/STEP_MS-EPS));let minimum=m.state.vx;
    for(let i=0;i<stop;i++){m.step({right:false});minimum=Math.min(minimum,m.state.vx);}
    add('friction',Math.abs(m.state.vx)<EPS&&minimum>=-EPS,{velocity:m.state.vx,minimum_velocity:minimum,steps:stop});
    m=create(settings);m.advanceSteps(ramp,{right:true});const reversalSteps=settings.stopping_ms===0?1:Math.ceil(settings.stopping_ms/settings.reversal_multiplier/STEP_MS-EPS);
    m.advanceSteps(reversalSteps,{right:false,left:true});const braked=m.state.vx;m.step({left:true});const reversed=m.state.vx;
    m.step({left:true,right:true});const neutral=Math.abs(m.state.vx)<=Math.abs(reversed)+EPS;
    add('reversal',Math.abs(braked)<EPS&&reversed<0&&neutral,{braked_velocity:braked,reversed_velocity:reversed,neutral_velocity:m.state.vx,braking_steps:reversalSteps});
    const distances=[30,60,120].map(fps=>{const game=create(settings);for(let i=0;i<fps;i++)game.advanceFrame(1/fps,{right:true});return game.state.x;});
    add('render-rates',Math.max(...distances)-Math.min(...distances)<=2,{fps:[30,60,120],positions:distances,tolerance_px:2});
    const coyoteAt=steps=>{const game=create(settings);game.scenario('coyote');game.advanceSteps(steps);game.pressJump();game.step();return game.state.jumpCount;};
    const inside=Math.floor(settings.coyote_ms/STEP_MS+EPS),outside=inside+1;
    const cInside=coyoteAt(inside),cOutside=coyoteAt(outside),cZero=coyoteAt(0);
    add('coyote',cInside===(settings.coyote_ms>0?1:0)&&cOutside===0&&(settings.coyote_ms>0||cZero===0),{inside_steps:inside,inside_jumps:cInside,outside_steps:outside,outside_jumps:cOutside,zero_age_jumps:cZero,inclusive:true});
    const bufferAt=steps=>{const game=create(settings);game.scenario('landing-next');game.state.tick=steps;game.state.pendingJump=true;game.state.queuedAt=0;game.step();return game.state.jumpCount;};
    const bInsideSteps=Math.floor(settings.jump_buffer_ms/STEP_MS+EPS),bInside=bufferAt(bInsideSteps),bOutside=bufferAt(bInsideSteps+1);
    m=create(settings);m.scenario('buffer');m.pressJump();m.advanceSteps(6);const natural=m.state.jumpCount;
    add('buffer',bInside===(settings.jump_buffer_ms>0?1:0)&&bOutside===0,{inside_steps:bInsideSteps,inside_jumps:bInside,outside_steps:bInsideSteps+1,outside_jumps:bOutside,natural_landing_jumps:natural,inclusive:true});
    m=create(settings);m.pressJump();m.step();for(let i=0;i<20;i++){m.pressJump();m.step();}const held=m.state.jumpCount;m.releaseJump();m.pressJump();m.step();const repeated=m.state.jumpCount;m.reset();
    add('single-jump',held===1&&repeated===1&&m.state.jumpCount===0&&!m.state.pendingJump&&!m.state.jumpHeld,{held_jumps:held,repressed_in_air_jumps:repeated,reset_jumps:m.state.jumpCount});
    const legacy=create({...settings,coyote_ms:0,jump_buffer_ms:0}),assisted=create(settings);legacy.pressJump();assisted.pressJump();let error=0;
    for(let i=0;i<70;i++){const a=legacy.step(),b=assisted.step();error=Math.max(error,Math.abs(a.y-b.y),Math.abs(a.vy-b.vy));}
    add('trajectory',error<EPS,{maximum_difference:error,steps:70});
    return {profile:PROFILE,scenario_version:1,step_ms:STEP_MS,settings,recipe_sha256:(config.recipes||[]).map(r=>r.sha256),checks,outcome:checks.every(row=>row.status==='passed')?'passed':'failed'};
  }
  return {PROFILE,HZ,STEP_MS,BASE:{...BASE},platforms:PLATFORM.map(row=>({...row})),create,verify};
});
