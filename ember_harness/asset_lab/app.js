/* Original asset workshop. The GLB is parsed from reviewed bytes; no resource fetches. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id), {THREE:T,GLTFLoader}=globalThis.Ember3D;
  const asset=globalThis.EMBER_ASSET, canvas=$('scene'), stage=$('stage');
  const config=asset.spec.interaction||{pivot_node:'LidPivot',axis:'x',open_angle_rad:-1.85,
    collision_node:'COLLISION_Chest',socket_node:'Socket_Delivery',noun:'chest',success_text:'Delivery complete',passage:false};
  const name=asset.spec.display_name||'Delivery chest',extent=Math.max(...asset.report.dimensions_m),viewScale=Math.max(1,extent/1.21);
  document.title=name+' · Ember asset workshop';$('asset-name').textContent=name;
  canvas.setAttribute('aria-label','3D '+name);$('interact').textContent='Open '+config.noun;
  if(asset.spec.profile){$('asset-heading').replaceChildren(document.createTextNode('Made to move.'),document.createElement('br'),document.createTextNode('Ready to play.'));
    $('asset-description').textContent='Study the silhouette. Try the movement. Approach the '+config.noun+' and put it through its paces.';}
  let renderer;
  try { renderer=new T.WebGLRenderer({canvas,antialias:true,alpha:true}); }
  catch(error){$('load-state').textContent='WebGL unavailable';$('status').textContent='This scene needs a WebGL browser';throw error;}
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;renderer.shadowMap.type=T.PCFSoftShadowMap;
  renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.25;
  const scene=new T.Scene(),camera=new T.PerspectiveCamera(34,1,.05,40);
  scene.add(new T.HemisphereLight(0xe5f5e7,0x293029,2.5));
  const key=new T.DirectionalLight(0xffdda4,4.8);key.position.set(-3,6,4).multiplyScalar(viewScale);key.castShadow=true;
  key.shadow.mapSize.set(1024,1024);Object.assign(key.shadow.camera,{left:-3*viewScale,right:3*viewScale,top:3*viewScale,bottom:-3*viewScale,near:.1,far:15*viewScale});
  key.shadow.bias=-.0003;key.shadow.normalBias=.025;scene.add(key);
  const rim=new T.DirectionalLight(0x8dc4ba,2);rim.position.set(3,3,-3);scene.add(rim);
  const glow=new T.PointLight(0xffa83d,0,3);glow.position.set(0,.7,0);scene.add(glow);
  const ground=new T.Mesh(new T.CylinderGeometry(2.3*viewScale,2.3*viewScale,.08,96),new T.MeshStandardMaterial({color:0x304b3b,roughness:.95}));
  ground.position.y=-.045;ground.receiveShadow=true;scene.add(ground);
  const ring=new T.Mesh(new T.RingGeometry(1.82*viewScale,1.83*viewScale,96),new T.MeshBasicMaterial({color:0x72907a,side:T.DoubleSide}));
  ring.rotation.x=-Math.PI/2;ring.position.y=.002;scene.add(ring);
  const actor=new T.Group();actor.name='CourierPlayer';
  const body=new T.Mesh(new T.CapsuleGeometry(.09,.14,4,12),new T.MeshStandardMaterial({color:0xe4c58a,roughness:.6}));
  body.position.y=.17;body.castShadow=true;actor.add(body);
  const halo=new T.Mesh(new T.RingGeometry(.15,.18,32),new T.MeshBasicMaterial({color:0xd2af68,side:T.DoubleSide,transparent:true,opacity:.75}));
  halo.rotation.x=-Math.PI/2;halo.position.y=.008;actor.add(halo);actor.position.set(0,0,1.8);scene.add(actor);
  let loaded=false,motion,proxy,model,collider,closedBounds,socket,closedRotation=0,open=false,delivered=false,angle=0,orbit=.48,drag=null,frameCount=0,frameTotal=0,last=performance.now();
  let proxyNodes=[],proxyBoxes=[];
  const spawn=new T.Vector3(0,0,1.8);
  const keys=new Set(),radius=.16,reach=.50;
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  function distance(){return Math.hypot(actor.position.x-socket.x,actor.position.z-socket.z);}
  function status(){if(!loaded)return;$('status').textContent=open?config.success_text:distance()<=reach?'Ready to open':'Too far to reach';}
  function updateCollision(){model.updateMatrixWorld(true);proxyBoxes.forEach((box,i)=>box.setFromObject(proxyNodes[i]));}
  function overlaps(point,box){return point.y+.34>box.min.y&&point.y<box.max.y&&point.x>box.min.x-radius&&point.x<box.max.x+radius&&point.z>box.min.z-radius&&point.z<box.max.z+radius;}
  function move(dx,dz){
    if(!loaded)return;
    const proposed=actor.position.clone();proposed.x=clamp(proposed.x+dx,-1.7*viewScale,1.7*viewScale);proposed.z=clamp(proposed.z+dz,-1.7*viewScale,Math.max(1.9*viewScale,spawn.z+.1));
    const blocked=proxyBoxes.some(box=>overlaps(proposed,box));
    if(!blocked)actor.position.copy(proposed);
    $('collision-state').textContent=blocked?'Blocked':'Clear';status();
  }
  function approach(){if(!loaded)return;actor.position.set(socket.x,0,closedBounds.max.z+radius+.015);$('collision-state').textContent=open?'Clear':'Blocked';status();}
  function interact(){
    if(!loaded)return;if(distance()>reach){$('status').textContent='Too far to reach';return;}
    if(open&&config.passage&&overlaps(actor.position,closedBounds)){$('status').textContent='Step clear to close';return;}
    open=!open;$('lid-state').textContent=open?'Open':'Closed';$('interact').textContent=(open?'Close ':'Open ')+config.noun;
    if(open&&!delivered){delivered=true;$('deliveries').textContent='1';}status();
  }
  function reset(){open=false;delivered=false;angle=0;keys.clear();actor.position.copy(spawn);
    if(loaded){motion.rotation[config.axis]=closedRotation;updateCollision();}
    $('deliveries').textContent='0';$('lid-state').textContent='Closed';$('collision-state').textContent='Clear';$('interact').textContent='Open '+config.noun;status();}
  $('approach').onclick=approach;$('interact').onclick=interact;$('reset').onclick=reset;
  $('orbit-left').onclick=()=>orbit-=.4;$('orbit-right').onclick=()=>orbit+=.4;
  canvas.addEventListener('pointerdown',e=>{drag=e.clientX;canvas.setPointerCapture(e.pointerId);});
  canvas.addEventListener('pointermove',e=>{if(drag!==null){orbit-=(e.clientX-drag)*.008;drag=e.clientX;}});
  canvas.addEventListener('pointerup',()=>drag=null);canvas.addEventListener('pointercancel',()=>drag=null);
  addEventListener('keydown',e=>{if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight',' ','w','a','s','d','r'].includes(e.key)){e.preventDefault();keys.add(e.key);if(!e.repeat&&e.key===' ')interact();if(!e.repeat&&e.key==='r')reset();}});
  addEventListener('keyup',e=>keys.delete(e.key));addEventListener('blur',()=>keys.clear());
  document.addEventListener('visibilitychange',()=>{if(document.hidden)keys.clear();});
  const bytes=Uint8Array.from(atob(asset.glb_base64),c=>c.charCodeAt(0));
  new GLTFLoader().parse(bytes.buffer,'',gltf=>{
    model=gltf.scene;scene.add(model);model.updateMatrixWorld(true);
    motion=model.getObjectByName(config.pivot_node);proxy=model.getObjectByName(config.collision_node);const anchor=model.getObjectByName(config.socket_node);
    if(!motion||!proxy||!anchor)throw Error('Required asset nodes missing');
    collider=new T.Box3().setFromObject(proxy);socket=anchor.getWorldPosition(new T.Vector3());
    proxyNodes=[proxy,...(config.static_collision_nodes||[]).map(n=>model.getObjectByName(n))];
    if(proxyNodes.some(n=>!n))throw Error('Required static collision nodes missing');
    proxyBoxes=proxyNodes.map(n=>new T.Box3().setFromObject(n));proxyBoxes[0]=collider;
    closedBounds=collider.clone();closedRotation=motion.rotation[config.axis];
    spawn.set(socket.x,0,Math.max(1.8,closedBounds.max.z+1.4));actor.position.copy(spawn);
    model.traverse(o=>{if(o.isMesh){o.castShadow=true;o.receiveShadow=true;}if(o.name.startsWith('COLLISION_'))o.visible=false;});
    loaded=true;$('load-state').textContent='Asset ready · 1 unit = 1 metre';
    $('asset-stats').textContent=asset.report.triangles.toLocaleString()+' triangles · '+asset.report.materials+' materials';
    $('measurements').textContent=JSON.stringify({spec:asset.spec,measured:asset.report},null,2);status();
  },error=>{$('load-state').textContent='Asset failed to load';throw error;});
  function render(now){
    const elapsed=now-last,dt=Math.min(.05,elapsed/1000);last=now;
    const width=stage.clientWidth,height=stage.clientHeight;
    if(canvas.width!==Math.round(width*renderer.getPixelRatio())||canvas.height!==Math.round(height*renderer.getPixelRatio())){
      renderer.setSize(width,height,false);camera.aspect=width/height;camera.updateProjectionMatrix();
    }
    const mobile=width<650;camera.position.set(Math.sin(orbit)*(mobile?3.7:3.25)*viewScale,(mobile?2.5:2.25)*viewScale,Math.cos(orbit)*(mobile?3.7:3.25)*viewScale);
    camera.lookAt(mobile?0:-.32*viewScale,asset.report.dimensions_m[1]*.46,0);
    if(loaded){
      const target=open?config.open_angle_rad:0;angle+=(target-angle)*(1-Math.exp(-dt*11));motion.rotation[config.axis]=closedRotation+angle;
      updateCollision();
      const dx=(keys.has('d')||keys.has('ArrowRight')?1:0)-(keys.has('a')||keys.has('ArrowLeft')?1:0);
      const dz=(keys.has('s')||keys.has('ArrowDown')?1:0)-(keys.has('w')||keys.has('ArrowUp')?1:0);
      if(dx||dz)move(dx*dt,dz*dt);
      glow.intensity=open&&!config.passage?2.4:0;
    }
    renderer.render(scene,camera);frameCount++;frameTotal+=elapsed;
    if(frameCount===45){$('frame-time').textContent=(frameTotal/frameCount).toFixed(1)+' ms';frameCount=0;frameTotal=0;}
    requestAnimationFrame(render);
  }
  requestAnimationFrame(render);
})();
