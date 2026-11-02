(() => {
  'use strict';
  const s=EMBER_ASSET.spec,canvas=document.querySelector('#stage'),ctx=canvas.getContext('2d');
  const menu=document.querySelector('#tile'),repeat=document.querySelector('#repeat');
  document.querySelector('#title').textContent=s.display_name+' · Tile workshop';
  document.querySelector('#description').textContent=s.art_direction;
  EmberSprites.load(EMBER_ASSET).then(atlas=>{
    const names=Object.keys(atlas.tiles),[w,h]=s.frame_size;
    for (const name of names) {const option=document.createElement('option');option.value=name;option.textContent=name;menu.append(option);}
    function render() {
      ctx.clearRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#edf3f8';ctx.font='16px system-ui';
      ctx.fillText('Atlas · row-major cells',20,28);
      const fit=value=>value>=1?Math.floor(value):value;
      const scale=fit(Math.min(380/(s.grid[0]*w),210/(s.grid[1]*h)));
      for(let i=0;i<s.frames;i++) atlas.drawTile(ctx,i,20+i%s.grid[0]*w*scale,45+Math.floor(i/s.grid[0])*h*scale,{scale});
      const count=repeat.checked?4:1, previewScale=fit(Math.min(380/(count*w),210/(count*h)));
      ctx.fillText(repeat.checked?'Repeat · inspect opposite edges':'Selected tile',470,28);
      atlas.drawMap(ctx,Array.from({length:count},()=>Array(count).fill(menu.value)),470,45,{scale:previewScale});
      ctx.fillText('Sample map · placement of declared cells',20,310);
      const rows=Array.from({length:4},(_,r)=>Array.from({length:12},(_,c)=>names[(r+c)%names.length]));
      atlas.drawMap(ctx,rows,20,330,{scale:Math.min(3,840/(12*w),170/(4*h))});
      const selected=atlas.tiles[menu.value];
      document.querySelector('#status').textContent=`${s.frames} tiles · ${w} × ${h} px · ${menu.value} · Cell ${selected.frame} · ${selected.solid?'Solid':'Passable'}`;
      document.querySelector('#repeat-state').textContent=repeat.checked?'Repeated 4 × 4':'Single tile';
    }
    menu.onchange=repeat.onchange=render;menu.disabled=repeat.disabled=false;render();
    document.querySelector('#load-state').textContent='Asset ready';
  }).catch(error=>{document.querySelector('#load-state').textContent='Asset failed to load';document.querySelector('#error').textContent=error.message;});
})();
