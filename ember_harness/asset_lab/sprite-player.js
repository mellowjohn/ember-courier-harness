/* Ember's offline atlas player. Seconds in, canvas pixels out; gameplay owns collisions and damage. */
(() => {
  'use strict';
  async function load(asset = globalThis.EMBER_ASSET) {
    if (!asset || asset.spec?.profile !== 'sprite-atlas-v1') throw new Error('A sprite-atlas-v1 asset is required.');
    const s = asset.spec, terrain = ['tile','tileset'].includes(s.kind);
    const clips = s.animations || {default: {frames: terrain ? [0] : Array.from({length: s.frames}, (_, i) => i), fps: s.fps, loop: terrain ? false : s.loop}};
    const initial = s.default_animation || (Object.hasOwn(clips, 'idle') ? 'idle' : Object.keys(clips).sort()[0]);
    const image = new Image();
    await new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = () => reject(new Error('The sprite PNG could not be decoded.'));
      image.src = 'data:image/png;base64,' + asset.png_base64;
    });
    const [w, h] = s.frame_size;
    if (image.naturalWidth !== w * s.grid[0] || image.naturalHeight !== h * s.grid[1]) throw new Error('Sprite PNG dimensions do not match its frame layout.');
    function createPlayer(name = initial, {followNext = true} = {}) {
      let current, elapsed = 0, completed = false;
      function select(value) {
        if (!Object.hasOwn(clips, value)) throw new Error('Unknown sprite animation: ' + value);
        current = value; elapsed = 0; completed = false;
      }
      select(name);
      const player = {
        get animation() { return current; },
        get completed() { return completed; },
        get clipFrame() { return Math.min(clips[current].frames.length - 1, Math.floor(elapsed * clips[current].fps + 1e-9)); },
        get frame() { return clips[current].frames[player.clipFrame]; },
        play(value, {restart = false} = {}) {
          if (value !== current || restart) select(value);
          return player;
        },
        seek(index) {
          if (!Number.isInteger(index) || index < 0 || index >= clips[current].frames.length) throw new RangeError('Frame is outside the current animation.');
          elapsed = index / clips[current].fps; completed = false;
          return player;
        },
        update(seconds) {
          if (!Number.isFinite(seconds) || seconds < 0) throw new RangeError('Sprite elapsed time must be nonnegative seconds.');
          const events = [];
          if (completed) return events;
          elapsed += seconds;
          // Bound pathological transition cycles after a suspended tab; keep ordinary playback exact.
          for (let transitions = 0; transitions < 256; transitions++) {
            const clip = clips[current], duration = clip.frames.length / clip.fps;
            if (clip.loop) { elapsed %= duration; if (duration - elapsed < 1e-10) elapsed = 0; break; }
            if (elapsed + 1e-10 < duration) break;
            const rest = Math.max(0, elapsed - duration);
            events.push(current);
            if (!clip.next || !followNext) { elapsed = duration; completed = true; break; }
            select(clip.next); elapsed = rest;
            if (transitions === 255) elapsed = 0;
          }
          return events;
        },
        draw(ctx, x, y, {scale = 1, flipX = false, flipY = false} = {}) {
          if (![x, y, scale].every(Number.isFinite) || scale <= 0) throw new RangeError('Use finite sprite coordinates and a positive scale.');
          const index = player.frame;
          ctx.save();
          try {
            ctx.translate(x, y); ctx.scale(flipX ? -1 : 1, flipY ? -1 : 1);
            ctx.imageSmoothingEnabled = s.sampling === 'smooth';
            ctx.globalCompositeOperation = s.blend;
            ctx.drawImage(image, index % s.grid[0] * w, Math.floor(index / s.grid[0]) * h, w, h,
              -w * scale * s.pivot[0], -h * scale * s.pivot[1], w * scale, h * scale);
          } finally { ctx.restore(); }
        }
      };
      return player;
    }
    const tiles = terrain ? Object.freeze(Object.fromEntries(Object.entries(s.tileset?.tiles ||
      Object.fromEntries(Array.from({length:s.frames},(_,i)=>['tile-'+i,{frame:i,solid:false}])))
      .map(([name,tile])=>[name,Object.freeze({...tile})]))) : Object.freeze({});
    function tileIndex(tile) {
      if (!terrain) throw new Error('Tile drawing requires tile or tileset artwork.');
      const index = typeof tile === 'string' && Object.hasOwn(tiles,tile) ? tiles[tile].frame : tile;
      if (!Number.isInteger(index) || index < 0 || index >= s.frames) throw new RangeError('Unknown tile: '+tile);
      return index;
    }
    function drawTile(ctx,tile,x,y,{scale=1,flipX=false,flipY=false}={}) {
      const index=tileIndex(tile);
      if (![x,y,scale,w*scale,h*scale,x+w*scale,y+h*scale].every(Number.isFinite)||scale<=0)
        throw new RangeError('Use finite tile coordinates and a positive scale.');
      ctx.save();
      try {
        ctx.translate(x+(flipX?w*scale:0),y+(flipY?h*scale:0));ctx.scale(flipX?-1:1,flipY?-1:1);
        ctx.imageSmoothingEnabled=s.sampling==='smooth';ctx.globalCompositeOperation=s.blend;
        ctx.drawImage(image,index%s.grid[0]*w,Math.floor(index/s.grid[0])*h,w,h,0,0,w*scale,h*scale);
      } finally {ctx.restore();}
    }
    function validateMap(rows) {
      if (!terrain) throw new Error('Tilemaps require tile or tileset artwork.');
      if (!Array.isArray(rows)||!rows.length||rows.length>256||!Array.isArray(rows[0])||
          !rows[0].length||rows[0].length>256||rows.length*rows[0].length>16384||
          Array.from(rows).some(row=>!Array.isArray(row)||row.length!==rows[0].length))
        throw new RangeError('Use a rectangular tilemap of at most 256 rows/columns and 16384 cells.');
    }
    function drawMap(ctx,rows,x=0,y=0,{scale=1}={}) {
      validateMap(rows);
      if (![x,y,scale,w*scale,h*scale,x+rows[0].length*w*scale,y+rows.length*h*scale].every(Number.isFinite)||scale<=0)
        throw new RangeError('Use finite tilemap coordinates and a positive scale.');
      // Validate before touching canvas so an invalid map cannot render a partial layer.
      const cells=rows.map(row=>Array.from(row,tile=>tile===null?null:tileIndex(tile)));
      let drawn=0;
      cells.forEach((row,r)=>row.forEach((tile,c)=>{if(tile!==null){drawTile(ctx,tile,x+c*w*scale,y+r*h*scale,{scale});drawn++;}}));
      return drawn;
    }
    function solidAt(rows,column,row) {
      validateMap(rows);
      if (!Number.isInteger(column)||!Number.isInteger(row)) throw new RangeError('Use integer tilemap coordinates.');
      if (row<0||column<0||row>=rows.length||column>=rows[0].length||rows[row][column]===null) return false;
      const tile=rows[row][column],index=tileIndex(tile);
      return typeof tile==='string' ? tiles[tile].solid : Object.values(tiles).some(t=>t.frame===index&&t.solid);
    }
    return Object.freeze({spec: s, image, animations: clips, createPlayer, tiles, drawTile, drawMap, solidAt});
  }
  function createMachine(atlas, definition, identity = {}) {
    const states = definition.states, rules = definition.transitions;
    const defaults = Object.fromEntries(Object.entries(definition.signals).map(([name, spec]) => [name, spec.default]));
    let signals = {...defaults}, state = definition.initial, elapsed = 0, sequence = 0, fired = new Set();
    const player = atlas.createPlayer(states[state].clip, {followNext:false});
    function enter(name) {
      if (!Object.hasOwn(states,name)) throw new Error('Unknown animation state: '+name);
      state=name; elapsed=0; fired=new Set(); sequence++;
      player.play(states[state].clip,{restart:true});
    }
    const compare = {eq:(a,b)=>a===b,ne:(a,b)=>a!==b,gt:(a,b)=>a>b,gte:(a,b)=>a>=b,lt:(a,b)=>a<b,lte:(a,b)=>a<=b};
    function choose(events) {
      const current=states[state];
      if (current.terminal) return;
      const eligible=rules.map((rule,index)=>({rule,index})).filter(({rule})=>
        rule.to!==state && (rule.from.includes('*')||rule.from.includes(state)) &&
        (rule.event===null||events.has(rule.event)) && rule.when.every(c=>compare[c.op](signals[c.signal],c.value)) &&
        (current.interruptible||player.completed||states[rule.to].priority>current.priority));
      eligible.sort((a,b)=>states[b.rule.to].priority-states[a.rule.to].priority||a.index-b.index);
      if (eligible.length) enter(eligible[0].rule.to);
    }
    const actor = {
      get state(){return state;}, get animation(){return player.animation;}, get frame(){return player.frame;},
      get clipFrame(){return player.clipFrame;}, get completed(){return player.completed;}, get sequence(){return sequence;},
      reset(name=definition.initial){signals={...defaults};enter(name);return actor;},
      update(seconds,patch={},events=[]) {
        if (!Number.isFinite(seconds)||seconds<0) throw new RangeError('Use nonnegative animation seconds.');
        for (const [name,value] of Object.entries(patch)) {
          const spec=definition.signals[name];
          if (!spec || typeof value!==spec.type || (typeof value==='number'&&(!Number.isFinite(value)||Math.abs(value)>1e6)))
            throw new Error('Invalid animation signal: '+name);
        }
        if (!Array.isArray(events)||events.length>32||events.some(e=>typeof e!=='string')) throw new Error('Use a bounded list of animation input events.');
        signals={...signals,...patch}; choose(new Set(events));
        const output=[]; let remaining=seconds;
        for (let advances=0;advances<64;advances++) {
          const current=states[state],clip=atlas.animations[current.clip],duration=clip.frames.length/clip.fps;
          const step=clip.loop?remaining:Math.min(remaining,Math.max(0,duration-elapsed));
          const end=elapsed+step;
          current.markers.forEach((marker,index)=>{
            if (!fired.has(index)&&marker.frame/clip.fps<=end+1e-10) {
              fired.add(index); output.push({...identity,name:marker.event,state,sequence,frame:marker.frame});
            }
          });
          player.update(step);elapsed=end;remaining=Math.max(0,remaining-step);
          if (!player.completed||current.terminal||current.on_complete===null) break;
          enter(current.on_complete);
          // Completion may resolve airborne/moving conditions, but never replays this tick's input event.
          choose(new Set());
          if (remaining===0) {
            const next=states[state];
            next.markers.forEach((marker,index)=>{if(marker.frame===0&&!fired.has(index)){
              fired.add(index);output.push({...identity,name:marker.event,state,sequence,frame:0});
            }});
            break;
          }
        }
        return output;
      },
      draw(...args){return player.draw(...args);}
    };
    return actor;
  }

  const scenes=[];
  async function createScene(plan=globalThis.EMBER_SPRITE_PLAN,assets=globalThis.EMBER_SPRITE_ASSETS) {
    if (!plan||plan.version!==1||!Array.isArray(plan.entities)||!assets) throw new Error('A sprite entity plan and atlas collection are required.');
    const definitions=new Map(plan.entities.map(entity=>[entity.id,entity]));
    if(definitions.size!==plan.entities.length) throw new Error('Sprite entity IDs must be unique.');
    const atlases=new Map();
    await Promise.all([...new Set(plan.entities.map(e=>e.asset_ref))].map(async ref=>{
      if(!Object.hasOwn(assets,ref)) throw new Error('A bound sprite atlas is missing: '+ref);
      atlases.set(ref,await load(assets[ref]));
    }));
    const instances=new Map();let serial=0;
    function createEntity(id) {
      const entity=definitions.get(id);
      if(!entity) throw new Error('Unknown sprite entity: '+id);
      if(instances.size>=256) throw new Error('Dispose unused sprite instances before spawning more than 256.');
      const atlas=atlases.get(entity.asset_ref),instanceId=id+'/'+(++serial);
      const actor=entity.machine?createMachine(atlas,entity.machine,{entityId:id,assetRef:entity.asset_ref,instanceId}):atlas.createPlayer(entity.required_clips[0],{followNext:false});
      let draws=0,updates=0,disposed=false;
      const record={entityId:id,assetRef:entity.asset_ref,instanceId};
      const wrapped={...record,
        tiles:atlas.tiles,
        get state(){return actor.state??actor.animation;},get frame(){return actor.frame;},get completed(){return actor.completed;},
        update(...args){if(disposed)throw new Error('Sprite instance was disposed.');updates++;return actor.update(...args);},
        draw(...args){if(disposed)throw new Error('Sprite instance was disposed.');actor.draw(...args);draws++;},
        drawTile(...args){if(disposed)throw new Error('Sprite instance was disposed.');atlas.drawTile(...args);draws++;},
        drawMap(...args){if(disposed)throw new Error('Sprite instance was disposed.');const count=atlas.drawMap(...args);draws+=count;return count;},
        solidAt(...args){if(disposed)throw new Error('Sprite instance was disposed.');return atlas.solidAt(...args);},
        reset(...args){if(disposed)throw new Error('Sprite instance was disposed.');if(actor.reset)actor.reset(...args);else actor.play(actor.animation,{restart:true});return wrapped;},
        dispose(){disposed=true;instances.delete(instanceId);}
      };
      instances.set(instanceId,()=>({...record,state:wrapped.state,frame:wrapped.frame,completed:wrapped.completed,draws,updates}));
      return wrapped;
    }
    const scene=Object.freeze({createEntity,diagnostics:()=>[...instances.values()].map(read=>read())});
    scenes.push(scene);if(scenes.length>16)scenes.shift();
    return scene;
  }
  globalThis.EmberSprites = Object.freeze({load,createMachine,createScene,diagnostics:()=>scenes.flatMap(scene=>scene.diagnostics())});
})();
