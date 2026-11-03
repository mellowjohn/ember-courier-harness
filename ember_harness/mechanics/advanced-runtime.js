/* Original expanded reference. Fixed simulation time; no network or dynamic code. */
(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory(require('./mechanic-runtime.js'));else root.EmberAdvancedMechanics=factory(root.EmberMechanics);})(typeof globalThis!=='undefined'?globalThis:this,function(base){
  'use strict';
  const PROFILE='ember-platformer-v2',HZ=120,DT=1/HZ,STEP_MS=1000/HZ,EPS=1e-8,WIDTH=1000,VIEW=400;
  const BASE={...base.BASE,camera_deadzone_px:0,camera_easing_ms:0,reduced_motion:0,hit_stop_ms:0,invincibility_ms:0,enemy_detection_px:0,enemy_attack_px:0,enemy_hysteresis_px:0,enemy_cooldown_ms:700,level_seed:0,level_sections:10};
  const move=(value,target,amount)=>value<target?Math.min(target,value+amount):Math.max(target,value-amount);
  const clamp=(value,low,high)=>Math.max(low,Math.min(high,value));
  const steps=ms=>Math.max(0,Math.ceil(ms/STEP_MS-EPS));
  function parameters(value){
    if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).sort().join()!==Object.keys(BASE).sort().join())throw Error('Use the declared expanded settings');
    const ordinary=Object.fromEntries(Object.keys(base.BASE).map(name=>[name,value[name]]));base.create(ordinary);
    const bounds={camera_deadzone_px:[0,240],camera_easing_ms:[0,600],reduced_motion:[0,1],hit_stop_ms:[0,120],invincibility_ms:[0,2000],enemy_detection_px:[0,400],enemy_attack_px:[0,90],enemy_hysteresis_px:[0,80],enemy_cooldown_ms:[200,2000],level_seed:[0,2147483647],level_sections:[6,12]};
    for(const [name,[low,high]]of Object.entries(bounds))if(!Number.isInteger(value[name])||value[name]<low||value[name]>high)throw Error('Expanded settings exceed their integer bounds');
    if(value.enemy_detection_px>0&&(value.enemy_detection_px<120||value.enemy_attack_px<24||value.enemy_hysteresis_px<10))throw Error('Use the supported enemy ranges');
    return {...value};
  }
  function generate(seed,sections){
    if(!Number.isInteger(seed)||seed<0||seed>2147483647||!Number.isInteger(sections)||sections<6||sections>12)throw Error('Use a bounded integer seed and section count');
    let value=seed>>>0;const random=()=>value=(Math.imul(1664525,value)+1013904223)>>>0;
    const tops=Array.from({length:sections},(_,i)=>seed===0||i<2||i>=sections-2?360:360-(random()%3)*16);
    const hazards=seed===0?[Math.floor(sections/2)]:[...new Set(Array.from({length:2},()=>2+random()%(sections-4)))].sort((a,b)=>a-b);
    const signature=JSON.stringify([seed,1,sections,tops,hazards]);let hash=2166136261;
    for(let i=0;i<signature.length;i++)hash=Math.imul(hash^signature.charCodeAt(i),16777619)>>>0;
    return {seed,version:1,sections,width:WIDTH,tops,hazards,hash:hash.toString(16).padStart(8,'0'),
      platforms:tops.map((top,i)=>({left:i*WIDTH/sections,right:(i+1)*WIDTH/sections,top})),
      reachable:tops.slice(1).every((top,i)=>Math.abs(top-tops[i])<=88),spawn_safe:hazards.every(i=>i>=2),goal_safe:hazards.every(i=>i<sections-2)};
  }
  function camera(settings){
    let x=0;const half=settings.camera_deadzone_px/2;
    const reset=center=>x=clamp(center-VIEW/2,0,WIDTH-VIEW);
    function update(center,reduced=false){
      let desired=x;if(center-x>VIEW/2+half)desired=center-VIEW/2-half;else if(center-x<VIEW/2-half)desired=center-VIEW/2+half;
      desired=clamp(desired,0,WIDTH-VIEW);const amount=settings.camera_easing_ms===0||settings.reduced_motion||reduced?1:Math.min(1,STEP_MS/settings.camera_easing_ms);
      x=clamp(x+(desired-x)*amount,0,WIDTH-VIEW);return x;
    }
    // Ordinary play has a final containment guard: a long easing time and
    // fast movement cannot leave the courier outside the visible viewport.
    function contain(center){x=clamp(x,Math.max(0,center-(VIEW-12)),Math.min(WIDTH-VIEW,Math.max(0,center-12)));return x;}
    return {update,reset,contain,get x(){return x;}};
  }
  function damage(settings){
    let state;function reset(){state={tick:0,health:5,hits:0,invincibleUntil:0,stopUntil:0,lastDamageTick:-1,episodeUsed:false,actorsAdvanced:0};return snapshot();}
    const snapshot=()=>({...state,invincible_ms:Math.max(0,state.invincibleUntil-state.tick)*STEP_MS,hit_stop_ms:Math.max(0,state.stopUntil-state.tick)*STEP_MS});
    function contact(){if(state.health===0||state.lastDamageTick===state.tick||state.tick<state.invincibleUntil)return false;
      state.health--;state.hits++;state.lastDamageTick=state.tick;state.invincibleUntil=state.tick+steps(settings.invincibility_ms);
      if(!state.episodeUsed){state.stopUntil=Math.max(state.stopUntil,state.tick+steps(settings.hit_stop_ms));state.episodeUsed=true;}return true;}
    function step(overlap=false,paused=false){if(paused)return snapshot();if(!overlap)state.episodeUsed=false;else contact();if(state.tick>=state.stopUntil)state.actorsAdvanced++;state.tick++;return snapshot();}
    reset();return {contact,step,reset,snapshot,get state(){return state;}};
  }
  function enemy(settings){
    let state;function reset(){state={tick:0,x:740,spawn:740,mode:'patrol',direction:1,attacks:0,nextAttack:0};return snapshot();}
    const snapshot=()=>({...state});
    function sense(distance){if(settings.enemy_detection_px===0){state.mode='patrol';return state.mode;}
      if(state.mode==='patrol'&&distance<=settings.enemy_detection_px)state.mode='chase';
      if(state.mode==='chase'&&distance>settings.enemy_detection_px+settings.enemy_hysteresis_px)state.mode='patrol';
      else if(state.mode==='chase'&&distance<=settings.enemy_attack_px)state.mode='attack';
      else if(state.mode==='attack'&&distance>settings.enemy_attack_px+settings.enemy_hysteresis_px)state.mode=distance>settings.enemy_detection_px+settings.enemy_hysteresis_px?'patrol':'chase';
      return state.mode;
    }
    function step(playerX,paused=false){if(paused)return {state:snapshot(),attack:false};const distance=Math.abs(playerX-state.x),mode=sense(distance);let attack=false;
      if(mode==='patrol'){state.x+=state.direction*45*DT;if(state.x>=state.spawn+80||state.x<=state.spawn-80){state.x=clamp(state.x,state.spawn-80,state.spawn+80);state.direction*=-1;}}
      else if(mode==='chase')state.x=clamp(state.x+Math.sign(playerX-state.x)*90*DT,0,976);
      else if(state.tick>=state.nextAttack){state.attacks++;state.nextAttack=state.tick+steps(settings.enemy_cooldown_ms);attack=true;}
      state.tick++;return {state:snapshot(),attack};
    }
    reset();return {reset,snapshot,sense,step,get state(){return state;}};
  }
  function create(value){
    const settings=parameters(value||BASE),level=generate(settings.level_seed,settings.level_sections),cam=camera(settings),impact=damage(settings),sentinel=enemy(settings);
    let state,accumulator=0,reduced=false;
    const platforms=()=>['coyote','buffer','landing-next'].includes(state.scenario)?base.platforms:level.platforms;
    const floorAt=x=>level.platforms.find(p=>x+12>=p.left&&x+12<=p.right)||level.platforms.at(-1);
    function reset(){state={tick:0,x:40,y:328,vx:0,vy:0,grounded:true,jumpCount:0,lastGroundedTick:0,coyoteAvailable:true,pendingJump:false,queuedAt:0,jumpHeld:false,left:false,right:false,paused:false,scenario:'normal'};accumulator=0;cam.reset(52);impact.reset();sentinel.reset();return snapshot();}
    function snapshot(){const hits=impact.snapshot();return {...state,time_ms:state.tick*STEP_MS,camera_x:cam.x,health:hits.health,hits:hits.hits,invincible_ms:hits.invincible_ms,hit_stop_ms:hits.hit_stop_ms,actor_ticks:hits.actorsAdvanced,enemy:sentinel.snapshot(),level_hash:level.hash,level_seed:level.seed,reduced_motion:!!(settings.reduced_motion||reduced)};}
    function clearInput(){state.left=false;state.right=false;state.jumpHeld=false;state.pendingJump=false;}
    function pressJump(){if(!state.jumpHeld){state.pendingJump=true;state.queuedAt=state.tick;}state.jumpHeld=true;}
    function releaseJump(){state.jumpHeld=false;}
    function launch(){state.vy=-420;state.grounded=false;state.jumpCount++;state.pendingJump=false;state.coyoteAvailable=false;}
    function step(input){
      if(state.paused)return snapshot();
      if(input!==undefined){if(!input||typeof input!=='object'||Object.keys(input).some(k=>!['left','right','jump'].includes(k))||Object.values(input).some(v=>typeof v!=='boolean'))throw Error('Use bounded directional input');if('left'in input)state.left=input.left;if('right'in input)state.right=input.right;if('jump'in input){if(input.jump)pressJump();else releaseJump();}}
      let overlap=false;
      // Stakes damage grounded contact. A jump clears their contact zone,
      // including at the slowest supported movement speed. Visual points do
      // not manufacture a wider airborne collision box than this declared rule.
      if(state.grounded&&(state.scenario==='normal'||state.scenario==='damage'))for(const section of level.hazards){const x=(section+.5)*WIDTH/level.sections;if(state.x+24>x-12&&state.x<x+12)overlap=true;}
      if(overlap)impact.contact();
      const frozen=impact.state.tick<impact.state.stopUntil;
      if(!frozen&&impact.state.health>0){
        if(state.grounded){state.lastGroundedTick=state.tick;state.coyoteAvailable=true;}
        const age=(state.tick-state.queuedAt)*STEP_MS,fresh=state.pendingJump&&age<EPS;
        const buffered=state.pendingJump&&(fresh||(settings.jump_buffer_ms>0&&age<=settings.jump_buffer_ms+EPS));
        const coyote=state.coyoteAvailable&&(state.grounded||(settings.coyote_ms>0&&(state.tick-state.lastGroundedTick)*STEP_MS<=settings.coyote_ms+EPS));
        if(buffered&&coyote)launch();
        const direction=Number(state.right)-Number(state.left),cap=settings.max_speed;
        if(direction===0)state.vx=settings.stopping_ms===0?0:move(state.vx,0,cap/(settings.stopping_ms/1000)*DT);
        else if(state.vx*direction<0)state.vx=settings.stopping_ms===0?0:move(state.vx,0,cap/(settings.stopping_ms/1000)*settings.reversal_multiplier*DT);
        else state.vx=settings.acceleration_ms===0?direction*cap:move(state.vx,direction*cap,cap/(settings.acceleration_ms/1000)*DT);
        const wasGrounded=state.grounded;state.x=clamp(state.x+state.vx*DT,0,976);
        if(wasGrounded&&!['coyote','buffer','landing-next'].includes(state.scenario)&&state.vy===0&&Math.abs(floorAt(state.x).top-(state.y+32))<=32)state.y=floorAt(state.x).top-32;
        const oldBottom=state.y+32;state.vy+=1000*DT;state.y+=state.vy*DT;state.grounded=false;
        for(const platform of platforms())if(state.x+24>platform.left&&state.x<platform.right&&state.vy>=0&&oldBottom<=platform.top+EPS&&state.y+32>=platform.top){state.y=platform.top-32;state.vy=0;state.grounded=true;state.lastGroundedTick=state.tick;state.coyoteAvailable=true;break;}
        if(state.grounded&&state.pendingJump&&settings.jump_buffer_ms>0&&age<=settings.jump_buffer_ms+EPS)launch();
        if(state.pendingJump&&age>settings.jump_buffer_ms+EPS)state.pendingJump=false;
        const attack=sentinel.step(state.x).attack;if(attack&&Math.abs(state.y+32-floorAt(sentinel.state.x).top)<40)overlap=true;
      }
      impact.step(overlap);state.tick++;cam.update(state.x+12,reduced);if(state.scenario==='normal'||state.scenario==='movement')cam.contain(state.x+12);
      if(state.y>600){reset();return snapshot();}return snapshot();
    }
    function advanceSteps(count,input){if(!Number.isInteger(count)||count<0||count>600)throw Error('Advance at most 600 explicit simulation steps');for(let i=0;i<count;i++)step(input);return snapshot();}
    function advanceFrame(seconds,input){if(typeof seconds!=='number'||!Number.isFinite(seconds)||seconds<0||seconds>.25)throw Error('Frame duration exceeds reference bounds');if(state.paused){accumulator=0;return {state:snapshot(),steps:0};}accumulator+=seconds;let count=0;while(accumulator+EPS>=DT){step(input);accumulator=Math.max(0,accumulator-DT);count++;}return {state:snapshot(),steps:count};}
    function teleport(x){if(typeof x!=='number'||!Number.isFinite(x)||x<0||x>976)throw Error('Teleport inside the reference level');clearInput();state.x=x;state.y=floorAt(x).top-32;state.vx=0;state.vy=0;state.grounded=true;state.coyoteAvailable=true;state.pendingJump=false;cam.reset(x+12);accumulator=0;return snapshot();}
    function scenario(name){reset();if(name==='start')return snapshot();state.scenario=name;
      if(name==='coyote')Object.assign(state,{x:310,y:328,grounded:false,lastGroundedTick:0,coyoteAvailable:true});
      else if(name==='buffer')Object.assign(state,{x:80,y:320,vy:160,grounded:false,lastGroundedTick:-1000,coyoteAvailable:false});
      else if(name==='landing-next')Object.assign(state,{x:80,y:327,vy:120,grounded:false,lastGroundedTick:-1000,coyoteAvailable:false});
      else if(name==='movement'){}
      else if(name==='camera'){state.x=328;state.y=floorAt(state.x).top-32;}
      else if(name==='damage'){state.x=(level.hazards[0]+.5)*WIDTH/level.sections-12;state.y=floorAt(state.x).top-32;cam.reset(state.x+12);}
      else if(name==='enemy-near'||name==='enemy-far'||name==='enemy-attack'){state.x=sentinel.state.x+(name==='enemy-near'?120:name==='enemy-far'?-500:20);state.y=floorAt(state.x).top-32;cam.reset(state.x+12);}
      else throw Error('Choose a fixed expanded scenario');return snapshot();}
    function setPaused(value){if(typeof value!=='boolean')throw Error('Use a pause state');state.paused=value;clearInput();accumulator=0;return snapshot();}
    function setReducedMotion(value){if(typeof value!=='boolean')throw Error('Use a reduced-motion state');reduced=value;return snapshot();}
    reset();return {settings,level,snapshot,reset,step,advanceSteps,advanceFrame,scenario,teleport,setPaused,setReducedMotion,clearInput,pressJump,releaseJump,get state(){return state;}};
  }
  function verify(config){
    const settings=parameters(config.settings),checks=[],add=(id,passed,observed)=>checks.push({id,status:passed?'passed':'failed',observed}),trial=()=>{const game=create(settings);game.scenario('movement');return game;};
    let m=trial(),ramp=Math.max(1,Math.ceil(settings.acceleration_ms/STEP_MS-EPS)),first=m.step({right:true}).vx;m.advanceSteps(ramp-1,{right:true});
    add('acceleration',Math.abs(m.state.vx-settings.max_speed)<EPS&&(settings.acceleration_ms===0||first<settings.max_speed),{first_velocity:first,full_velocity:m.state.vx,steps:ramp,configured_ms:settings.acceleration_ms});
    const stop=Math.max(1,Math.ceil(settings.stopping_ms/STEP_MS-EPS));let minimum=m.state.vx;for(let i=0;i<stop;i++){m.step({right:false});minimum=Math.min(minimum,m.state.vx);}
    add('friction',Math.abs(m.state.vx)<EPS&&minimum>=-EPS,{velocity:m.state.vx,minimum_velocity:minimum,steps:stop});
    m=trial();m.advanceSteps(ramp,{right:true});const reversing=settings.stopping_ms===0?1:Math.ceil(settings.stopping_ms/settings.reversal_multiplier/STEP_MS-EPS);m.advanceSteps(reversing,{right:false,left:true});const braked=m.state.vx;m.step({left:true});const reversed=m.state.vx;m.step({left:true,right:true});
    add('reversal',Math.abs(braked)<EPS&&reversed<0&&Math.abs(m.state.vx)<=Math.abs(reversed)+EPS,{braked_velocity:braked,reversed_velocity:reversed,neutral_velocity:m.state.vx,braking_steps:reversing});
    const distances=[30,60,120].map(fps=>{const game=trial();for(let i=0;i<fps;i++)game.advanceFrame(1/fps,{right:true});return game.state.x;});
    add('render-rates',Math.max(...distances)-Math.min(...distances)<=2,{fps:[30,60,120],positions:distances,tolerance_px:2});
    const coyoteAt=count=>{const game=create(settings);game.scenario('coyote');game.advanceSteps(count);game.pressJump();game.step();return game.state.jumpCount;},inside=Math.floor(settings.coyote_ms/STEP_MS+EPS),outside=inside+1,cInside=coyoteAt(inside),cOutside=coyoteAt(outside),cZero=coyoteAt(0);
    add('coyote',cInside===(settings.coyote_ms>0?1:0)&&cOutside===0,{inside_steps:inside,inside_jumps:cInside,outside_steps:outside,outside_jumps:cOutside,zero_age_jumps:cZero,inclusive:true});
    const bufferAt=count=>{const game=create(settings);game.scenario('landing-next');game.state.tick=count;game.state.pendingJump=true;game.state.queuedAt=0;game.step();return game.state.jumpCount;},bi=Math.floor(settings.jump_buffer_ms/STEP_MS+EPS),bInside=bufferAt(bi),bOutside=bufferAt(bi+1);m=create(settings);m.scenario('buffer');m.pressJump();m.advanceSteps(6);
    add('buffer',bInside===(settings.jump_buffer_ms>0?1:0)&&bOutside===0,{inside_steps:bi,inside_jumps:bInside,outside_steps:bi+1,outside_jumps:bOutside,natural_landing_jumps:m.state.jumpCount,inclusive:true});
    m=trial();m.pressJump();m.step();for(let i=0;i<20;i++){m.pressJump();m.step();}const held=m.state.jumpCount;m.releaseJump();m.pressJump();m.step();const repeated=m.state.jumpCount;m.reset();
    add('single-jump',held===1&&repeated===1&&m.state.jumpCount===0,{held_jumps:held,repressed_in_air_jumps:repeated,reset_jumps:m.state.jumpCount});
    const plain=Object.fromEntries(Object.keys(base.BASE).map(key=>[key,settings[key]])),old=base.create(plain),current=create(settings);old.pressJump();current.pressJump();let difference=0;
    for(let i=0;i<70;i++){const a=old.step(),b=current.step();difference=Math.max(difference,Math.abs(a.y-b.y),Math.abs(a.vy-b.vy));}add('trajectory',difference<EPS,{maximum_difference:difference,steps:70});
    const c=camera(settings);c.update(199);const interior=c.x,firstCamera=c.update(700);for(let i=1;i<120;i++)c.update(700);const settled=c.x,positions=[30,60,120].map(fps=>{const cam=camera(settings);let acc=0;for(let i=0;i<fps;i++){acc+=1/fps;while(acc+EPS>=DT){cam.update(700);acc-=DT;}}return cam.x;});
    const bounds=[c.reset(-1000),c.reset(3000)],teleported=c.reset(40),reduced=camera(settings).update(700,true);
    add('camera',interior===0&&firstCamera>=0&&settled<=600&&Math.max(...positions)-Math.min(...positions)<EPS&&bounds[0]===0&&bounds[1]===600&&teleported===0,{inside:interior,first:firstCamera,settled,positions,bounds,teleport:teleported,reduced_motion:reduced});
    const d=damage(settings);d.contact();const afterHit=d.state.health,initialStop=d.state.stopUntil,N=steps(settings.invincibility_ms),H=steps(settings.hit_stop_ms),count=Math.max(1,N);for(let i=0;i<count;i++)d.step(true);const beforeExpiry=d.state.health,actors=d.state.actorsAdvanced;d.contact();const atExpiry=d.state.health,notExtended=d.state.stopUntil===initialStop,tick=d.state.tick;d.step(true,true);const pauseSame=d.state.tick===tick;d.reset();
    add('damage',afterHit===4&&beforeExpiry===4&&atExpiry===3&&notExtended&&pauseSame&&d.state.health===5,{invincible_steps:N,hit_stop_steps:H,after_hit:afterHit,inside:beforeExpiry,at_expiry:atExpiry,stop_not_extended:notExtended,actors_advanced:actors,pause_tick_unchanged:pauseSame,reset_health:d.state.health});
    const e=enemy(settings),initial=e.state.mode,noticed=e.sense(settings.enemy_detection_px),near=e.sense(settings.enemy_attack_px),boundary=e.sense(settings.enemy_attack_px+settings.enemy_hysteresis_px),exited=e.sense(settings.enemy_attack_px+settings.enemy_hysteresis_px+1),disengaged=e.sense(settings.enemy_detection_px+settings.enemy_hysteresis_px+1);e.reset();e.sense(Math.max(0,settings.enemy_detection_px-1));const jitter=[-1,1,-1,1].map(offset=>e.sense(Math.max(0,settings.enemy_detection_px+offset)));e.reset();const cooldown=steps(settings.enemy_cooldown_ms);for(let i=0;i<2*cooldown+1;i++)e.step(e.state.x);const attacks=e.state.attacks;e.reset();
    add('enemy',['patrol','chase','attack'].includes(e.state.mode)&&attacks===(settings.enemy_detection_px>0?3:0),{initial,noticed,near,attack_boundary:boundary,attack_exit:exited,disengaged,jitter,attacks,cooldown_steps:cooldown,reset_state:e.state.mode,reset_attacks:e.state.attacks});
    const layout=generate(settings.level_seed,settings.level_sections),again=generate(settings.level_seed,settings.level_sections),examples=[17,29].map(seed=>generate(seed,settings.level_sections)),different=examples.map(row=>row.hash),differentShape=JSON.stringify([examples[0].tops,examples[0].hazards])!==JSON.stringify([examples[1].tops,examples[1].hazards]);m=create(settings);m.advanceSteps(20,{right:true});m.reset();
    add('level',layout.reachable&&layout.spawn_safe&&layout.goal_safe&&layout.hash===again.hash&&differentShape&&m.level.hash===layout.hash,{seed:layout.seed,version:1,sections:layout.sections,width:WIDTH,hash:layout.hash,platform_tops:layout.tops,hazard_sections:layout.hazards,reachable:layout.reachable,spawn_safe:layout.spawn_safe,goal_safe:layout.goal_safe,repeat_equal:layout.hash===again.hash,distinct_hashes:different,distinct_layouts:differentShape,reset_equal:m.level.hash===layout.hash});
    return {profile:PROFILE,scenario_version:1,step_ms:STEP_MS,settings,recipe_sha256:(config.recipes||[]).map(row=>row.sha256),checks,outcome:checks.every(row=>row.status==='passed')?'passed':'failed'};
  }
  return {PROFILE,HZ,STEP_MS,BASE:{...BASE},WIDTH,VIEW,parameters,generate,camera,damage,enemy,create,verify};
});
