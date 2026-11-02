"""Entity-plan integration fixture using the existing sprite browser rehearsal."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime,timezone
from io import BytesIO,StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from unittest.mock import patch
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ember_harness import asset_2d,asset_library,chat_build,polish_runtime,project_versions,sprite_project
from ember_harness.local_ui import App,server
from tools.sprite_check import fixture,html


def character():
    spec,raw=fixture()
    spec['animations'].update(hurt=dict(frames=[9,10],fps=8,loop=False,next='idle'),
        jump=dict(frames=[2],fps=8,loop=True),fall=dict(frames=[3],fps=8,loop=True))
    return spec,raw


def machine():
    def state(clip,priority,interruptible=True,on_complete=None,terminal=False,markers=None):
        return dict(clip=clip,priority=priority,interruptible=interruptible,on_complete=on_complete,terminal=terminal,markers=markers or [])
    def eq(signal,value):return dict(signal=signal,op='eq',value=value)
    def rule(source,to,event=None,when=None):return {'from':source,'to':to,'event':event,'when':when or []}
    return dict(initial='idle',signals=dict(moving=dict(type='boolean',default=False),grounded=dict(type='boolean',default=True),
        dead=dict(type='boolean',default=False),vy=dict(type='number',default=0)),states=dict(
            idle=state('idle',0),walk=state('walk',1),jump=state('jump',20),fall=state('fall',20),
            attack=state('attack',50,False,'idle',markers=[dict(event='hit',frame=1)]),
            hurt=state('hurt',100,False,'idle'),death=state('death',1000,False,None,True)),transitions=[
                rule(['*'],'death',when=[eq('dead',True)]),rule(['*'],'hurt','hurt'),
                rule(['*'],'attack','attack',[eq('grounded',True)]),
                rule(['*'],'jump',when=[eq('grounded',False),dict(signal='vy',op='lt',value=0)]),
                rule(['*'],'fall',when=[eq('grounded',False),dict(signal='vy',op='gte',value=0)]),
                rule(['*'],'walk',when=[eq('moving',True),eq('grounded',True)]),
                rule(['walk','jump','fall'],'idle',when=[eq('moving',False),eq('grounded',True)])])


def plan(hero_ref,effect_ref):
    return dict(version=1,entities=[
        dict(id='hero',role='player',purpose='The controllable courier',activation='startup',
            required_clips=['idle','walk','jump','fall','attack','hurt','death'],asset_ref=hero_ref,generation=None,
            binding=dict(file='game.js',replace='ctx.fillRect(x-12,y-40,24,40);'),machine=machine()),
        dict(id='impact',role='effect',purpose='A short impact when the attack connects',activation='on_demand',
            required_clips=['default'],asset_ref=effect_ref,generation=None,binding=dict(file='game.js',replace=''),machine=None)])


def game_files():
    document='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{background:#101820;color:white;font:16px system-ui;margin:0;padding:20px}canvas{width:100%;max-width:700px;background:#192b39;display:block}button{font:inherit;padding:12px;margin:5px;touch-action:none}p{max-width:700px}</style></head><body>
<h1>Courier animation test</h1><p>Walk, jump, attack and take a hit. The game retains its score and target health.</p>
<canvas id="stage" width="700" height="280"></canvas><button id="left">Left</button><button id="right">Right</button><button id="jump">Jump</button><button id="attack">Attack</button><button id="hurt">Take hit</button><button id="die">Death</button><button id="respawn">Respawn</button>
<p id="load-state">Game ready</p><p>Animation: <span id="state">idle</span> · Score: <span id="score">7</span> · Target health: <span id="health">3</span> · Hits: <span id="hits">0</span> · Position: <span id="position">160</span></p><p id="error" role="alert"></p><script src="game.js"></script></body></html>'''
    source='''(()=>{'use strict';const canvas=document.querySelector('#stage'),ctx=canvas.getContext('2d');
let x=160,y=220,vy=0,moving=0,score=7,health=3,hits=0,dead=false,previous=null;const keys=new Set(),events=[];
let scene=null,hero=null;const effects=[];
function attack(){events.push('attack');}function hurt(){events.push('hurt');}
document.querySelector('#attack').onclick=attack;document.querySelector('#hurt').onclick=hurt;
function jump(){if(y===220&&!dead){vy=-260;}}document.querySelector('#jump').onclick=jump;
document.querySelector('#die').onclick=()=>{dead=true;};document.querySelector('#respawn').onclick=()=>{dead=false;y=220;vy=0;hero?.reset();};
for(const[id,d]of[['left',-1],['right',1]]){const b=document.getElementById(id);b.onpointerdown=e=>{e.preventDefault();b.setPointerCapture(e.pointerId);moving=d;};b.onpointerup=b.onpointercancel=b.onlostpointercapture=()=>{moving=0;};}
window.onkeydown=e=>{if(/INPUT|BUTTON/.test(e.target.tagName))return;if(['ArrowLeft','ArrowRight','ArrowUp','a','d',' '].includes(e.key)){e.preventDefault();keys.add(e.key);if(!e.repeat&&e.key===' ')attack();if(!e.repeat&&e.key==='ArrowUp')jump();}};window.onkeyup=e=>keys.delete(e.key);window.onblur=()=>{keys.clear();moving=0;};
function updateArt(dt){events.length=0;}
function draw(){ctx.fillRect(x-12,y-40,24,40);}
function tick(now){const dt=previous===null?0:Math.min(.05,(now-previous)/1000);previous=now;
const direction=Math.sign(moving+(keys.has('ArrowRight')||keys.has('d')?1:0)-(keys.has('ArrowLeft')||keys.has('a')?1:0));
if(!dead){x=Math.max(30,Math.min(650,x+direction*140*dt));vy+=600*dt;y=Math.min(220,y+vy*dt);if(y===220)vy=0;}
updateArt(dt,direction);ctx.clearRect(0,0,700,280);ctx.fillStyle='#7894a8';ctx.fillRect(0,220,700,3);ctx.fillStyle='#e9a249';draw();
document.querySelector('#score').textContent=score;document.querySelector('#health').textContent=health;document.querySelector('#hits').textContent=hits;document.querySelector('#position').textContent=Math.round(x);requestAnimationFrame(tick);}
requestAnimationFrame(tick);
})();'''
    return {'index.html':document,'game.js':source}


def integration_edits():
    return dict(title='Bind courier artwork and animation states',summary='Preserve movement, score and target health; replace the courier draw site and trigger one impact per attack hit.',edits=[
        dict(path='game.js',before='function updateArt(dt){events.length=0;}',after='''function updateArt(dt,direction){if(!hero){events.length=0;return;}
const emitted=hero.update(dt,{moving:direction!==0,grounded:y===220,vy,dead},events.splice(0));
for(const event of emitted)if(event.name==='hit'){hits++;score++;health=Math.max(0,health-1);effects.push({actor:scene.createEntity('impact'),x:x+45,y:y-20});}
for(let i=effects.length-1;i>=0;i--){effects[i].actor.update(dt);if(effects[i].actor.completed){effects[i].actor.dispose();effects.splice(i,1);}}
document.querySelector('#state').textContent=hero.state;}'''),
        dict(path='game.js',before='ctx.fillRect(x-12,y-40,24,40);',after="hero?.draw(ctx,x,y,{scale:1,flipX:keys.has('ArrowLeft')||moving<0});for(const effect of effects)effect.actor.draw(ctx,effect.x,effect.y);"),
        dict(path='game.js',before='requestAnimationFrame(tick);\n})();',after="EmberSprites.createScene(EMBER_SPRITE_PLAN,EMBER_SPRITE_ASSETS).then(loaded=>{scene=loaded;hero=scene.createEntity('hero');document.querySelector('#load-state').textContent='Asset ready';requestAnimationFrame(tick);}).catch(error=>{document.querySelector('#error').textContent=error.message;});\n})();")])


def main():
    runtime=polish_runtime.discover(ROOT,fingerprints=False)
    output=ROOT/'.harness/sprite-scene-checks'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]);output.mkdir(parents=True)
    root=output/'fixture';(root/'examples').mkdir(parents=True);(root/'examples/product_demo.py').touch()
    char,raw=character();effect=asset_2d.effect_spec();effect_raw=asset_2d.render_effect(effect)
    refs=[]
    for name,spec,png in [('hero',char,raw),('impact',effect,effect_raw)]:
        source=root/'.harness/asset-source'/name;asset_2d.write_source(source,png,spec);refs.append(asset_library.register(root,source))
    app=App(root);app.start('SYNTHETIC existing game sprite integration',chat_only=True);folder=app.sessions_dir/app.session['id']
    files=game_files()
    with redirect_stdout(StringIO()):
        baseline=chat_build.propose_build(root,folder,'baseline','Synthetic game',dict(title='Existing courier',summary='Synthetic existing game',files=[dict(path=k,content=v) for k,v in files.items()]))
        app.respond(baseline,'approve','SYNTHETIC TEST: isolated baseline')
    planned=plan(*refs);spec=deepcopy(char)
    spec['production']=dict(method='generated',tool='muse_image',prompt='Original revised courier animation',seed=None)
    planned['entities'][0].update(asset_ref=None,generation=spec)
    planning=dict(message='Synthetic artwork inventory only.',build=None,
        sprite_project=dict(intent='plan',expected_revision=0,plan=planned))
    with redirect_stdout(StringIO()),patch('ember_harness.session_chat.run_muse',return_value=dict(response=json.dumps(planning))),patch('ember_harness.muse_image.generate') as generate:
        app.chat('Plan the courier artwork first','synthetic-entity-plan-12345678');generate.assert_not_called()
    response=dict(message='Review the entity artwork plan and state machine.',build=integration_edits(),
        sprite_project=dict(intent='implement',expected_revision=1,plan=plan(*refs)))
    def prepare_from_saved_plan(*args,**kwargs):
        prompt=json.loads(args[2].split('\n',1)[1])
        assert prompt['conversation'][-1]['content'].startswith('Generate the missing artwork from this saved entity plan')
        # Reuse compatible fixture art; no live generation or credit use.
        return dict(response=json.dumps(response))
    assert {r['path']:r['content'] for r in chat_build.context(root,folder)['files']}==files
    env=dict(os.environ,EMBER_PLAYWRIGHT_MODULE=runtime['module'],EMBER_BROWSER_EXECUTABLE=runtime['browser'])
    review=output/'review-input.json';review.write_text(json.dumps(dict(variant='review')),encoding='utf-8')
    http=server(app);worker=threading.Thread(target=http.serve_forever,daemon=True);worker.start()
    try:
        review_env=dict(env,EMBER_BROWSER_URL=f'http://127.0.0.1:{http.server_port}/',EMBER_BROWSER_TOKEN=app.token)
        with (output/'review-browser.log').open('wb') as log,redirect_stdout(StringIO()),patch('ember_harness.session_chat.run_muse',side_effect=prepare_from_saved_plan),patch('ember_harness.proposal_quality.run',return_value=dict(status='unavailable',issues=['SYNTHETIC: verification tested separately'])):
            result=subprocess.run([runtime['node'],str(ROOT/'tools/sprite_check.js'),str(review),str(output)],env=review_env,stdout=log,stderr=log,timeout=75)
        if result.returncode:print(str(output/'review-browser.log'));return result.returncode
        (output/'report.json').rename(output/'review-report.json')
    finally:http.shutdown();http.server_close();worker.join(timeout=5)
    request=chat_build.list_requests(folder)[-1];body=request['payload']['body'];assert len(body['asset_actions'])==2
    preview=json.loads((output/'pending-preview.json').read_text(encoding='utf-8'))['html']
    assert chat_build.verify(root,folder)['passed']
    accepted=[e for e in chat_build.harness(folder)._entries() if e['kind']=='decision' and e.get('action',{}).get('tool')=='asset.accept' and e.get('decision')=='allow']
    assert len(accepted)==2
    archive,_=project_versions.export(root,folder,request['ref']);(output/'sprite-game.zip').write_bytes(archive)
    with zipfile.ZipFile(BytesIO(archive)) as zipped:
        exported={name:zipped.read(name).decode() for name in ('index.html','game.js','sprite-assets.js','sprite-plan.js','sprite-player.js')}
        for ref,png in zip(refs,[raw,effect_raw]):assert any(zipped.read(name)==png for name in zipped.namelist() if name.startswith('sprites/'+ref+'/') and name.endswith('.png'))
    source=output/'input.json';source.write_text(json.dumps(dict(variant='entities',preview=preview,exported=html(exported))),encoding='utf-8')
    with (output/'browser.log').open('wb') as log:
        result=subprocess.run([runtime['node'],str(ROOT/'tools/sprite_check.js'),str(source),str(output)],env=env,stdout=log,stderr=log,timeout=100)
    if result.returncode==0:
        report=json.loads((output/'report.json').read_text())
        checks=[]
        for name,broken in [('startup-visible',False),('startup-missing',True)]:
            area=output/name;area.mkdir();candidate=deepcopy(exported)
            if broken:
                draw="hero?.draw(ctx,x,y,{scale:1,flipX:keys.has('ArrowLeft')||moving<0});"
                assert draw in candidate['game.js'];candidate['game.js']=candidate['game.js'].replace(draw,'')
            request_input=area/'input.json';request_input.write_text(json.dumps(dict(html=html(candidate))),encoding='utf-8')
            with (area/'driver.log').open('wb') as log:
                observed=subprocess.run([runtime['node'],runtime['driver'],str(request_input),str(area/'output')],env=env,stdout=log,stderr=log,timeout=60)
            if observed.returncode:print(str(area/'driver.log'));return 1
            observed_report=json.loads((area/'output/report.json').read_text())
            for viewport in observed_report['viewports']:
                missing=viewport['sprites']['missingEntities']
                assert ('hero' in missing)==broken
                assert 'impact' not in missing,'An effect that activates on demand must not be required at startup'
            checks.append(dict(name=name,detectedCorrectly=True))
        report.update(startup_binding_checks=checks,separate_acceptance_receipts=2,
            basis='Synthetic model replies and original fixture artwork. Real desktop/touch input in sandboxed proposal and exported game, UI per-asset choices and separate acceptance receipts, plus production browser-driver detection of an intentionally undrawn entity. No live provider calls.')
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(str(output/('report.json' if result.returncode==0 else 'browser.log')))
    return result.returncode


if __name__=='__main__':raise SystemExit(main())
