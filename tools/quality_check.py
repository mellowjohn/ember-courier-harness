"""Real browser verification and screenshot-feedback rehearsal; synthetic Muse only."""
from contextlib import redirect_stdout
from datetime import datetime,timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from unittest.mock import patch
import uuid

from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from quality_fixture import assessments
from ember_harness import chat_build,polish_runtime,proposal_quality
from ember_harness.local_ui import App,server


FILES={
    'index.html':'<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="style.css"></head><body><h1>Trail tokens</h1><p>Collect tokens. Hold Right to explore.</p><button id="collect">Collect token</button><p>Tokens: <span id="score">0</span></p><p>Position: <span id="position">0</span></p><script src="game.js"></script></body></html>',
    'style.css':'body{margin:0;padding:24px;min-height:100vh;background:#234073;color:#fff;font:18px system-ui;box-sizing:border-box}button{padding:16px;font:inherit}',
    'game.js':"let score=0,position=0,held=false;document.querySelector('#collect').onclick=()=>{score+=0;document.querySelector('#score').textContent=score;};onkeydown=e=>{if(e.key==='ArrowRight'){held=true;e.preventDefault();}};onkeyup=()=>held=false;setInterval(()=>{if(held){position++;document.querySelector('#position').textContent=position;}},30);"
}
CHECKS=dict(title='Token pickup and movement',scenarios=[
    dict(name='Collect a token and move',viewport='desktop',steps=[dict(action='click',selector='#collect'),
        dict(action='text',selector='#score',value='1'),dict(action='hold',key='ArrowRight',ms=400),dict(action='number_at_least',selector='#position',value=3)]),
    dict(name='Touch token pickup',viewport='mobile',steps=[dict(action='tap',selector='#collect'),dict(action='text',selector='#score',value='1')])])


def main():
    runtime=polish_runtime.discover(ROOT,fingerprints=False)
    output=ROOT/'.harness/quality-checks'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]);output.mkdir(parents=True)
    root=output/'fixture';(root/'examples').mkdir(parents=True);(root/'examples/product_demo.py').touch()
    app=App(root);app.start('SYNTHETIC automatic game verification',chat_only=True);folder=app.sessions_dir/app.session['id']
    calls=[];repairs=[]
    def coder(*args,**kwargs):
        data=json.loads(args[2].split('\n',1)[1]);repair=bool(data.get('proposal_context'))
        if repair:
            assert len(kwargs['images'])==4
            repairs.append([str(p) for p in kwargs['images']])
            build=dict(title='Warm working trail tokens',summary='Repair pickup and the requested warm palette',edits=[
                dict(path='game.js',before='score+=0',after='score+=1'),dict(path='style.css',before='#234073',after='#ff914d')])
        else:build=dict(title='Trail tokens',summary='SYNTHETIC incomplete candidate',files=[dict(path=k,content=v) for k,v in FILES.items()])
        return dict(response=json.dumps(dict(message='Review the checked candidate.',build=build,gameplay_checks=CHECKS)))
    def reviewer(*args,**kwargs):
        data=json.loads(args[2].split('\n',1)[1]);assert len(kwargs['images'])==4
        with Image.open(kwargs['images'][0]) as image:pixel=image.convert('RGB').getpixel((1090,730))
        warm=pixel==(255,145,77);calls.append(dict(images=[p.name for p in kwargs['images']],background_pixel=pixel,warm=warm))
        verdict=dict(meets_task=warm,preserves_scope=True,summary='SYNTHETIC pixel-based palette judgment',
            issues=[] if warm else ['The screenshot is blue; the requested palette is warm orange.'],criteria=assessments(data))
        if not warm:
            next(c for c in verdict['criteria'] if c['id']=='presentation').update(status='not_met',reason='Blue screenshot does not match the requested orange palette')
        return dict(response=json.dumps(verdict))
    http=server(app);worker=threading.Thread(target=http.serve_forever,daemon=True);worker.start()
    try:
        env=dict(os.environ,EMBER_PLAYWRIGHT_MODULE=runtime['module'],EMBER_BROWSER_EXECUTABLE=runtime['browser'],
            EMBER_BROWSER_URL=f'http://127.0.0.1:{http.server_port}/',EMBER_BROWSER_TOKEN=app.token,EMBER_BROWSER_OUTPUT=str(output))
        with patch('ember_harness.session_chat.run_muse',side_effect=coder),patch('ember_harness.proposal_quality.run_muse',side_effect=reviewer),redirect_stdout(io.StringIO()):
            app.chat('Build a warm orange token pickup game with an increasing token score, keyboard movement and touch pickup.','quality-real-browser-12345678')
            first=app.snapshot()['build']['quality_check'];assert first['status']=='needs_changes'
            assert first['observations']['candidate']['gameplay']['outcome']=='failed'
            (output/'before-report.json').write_text(json.dumps(first,indent=2),encoding='utf-8')
            with (output/'browser.log').open('wb') as log:
                result=subprocess.run([runtime['node'],str(ROOT/'tools/quality_check.js')],env=env,cwd=ROOT,stdout=log,stderr=log,timeout=120)
            if result.returncode:print(output/'browser.log',file=sys.stderr);return result.returncode
        final=app.snapshot()['build']['quality_check'];assert final['status']=='passed',final['issues']
        assert not chat_build.context(root,folder)['files'];assert len(repairs)==1;assert len(calls)==2
        assert all(len(c['images'])==4 for c in calls)
        report=dict(passed=True,initial_status=first['status'],repaired_status=final['status'],visual_reviews=calls,
            screenshot_feedback_calls=len(repairs),source_unapplied=True,
            basis='Real Chromium screenshots, keyboard holds, mouse and touch assertions, UI image loading, and repair through saved screenshots. Muse replies and visual judgments are synthetic; no live credits used.')
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(output/'report.json');return 0
    finally:http.shutdown();http.server_close();worker.join(timeout=5)


if __name__=='__main__':raise SystemExit(main())
