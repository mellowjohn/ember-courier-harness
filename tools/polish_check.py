"""Real-browser overnight rehearsal with synthetic decisions/provider; no live credits."""
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ember_harness import chat_build, polish, polish_runtime
from ember_harness.local_ui import App, server
from tools.browser_check import FILES
from tools.release_check import source_manifest

STYLE = '''*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;align-content:center;justify-items:center;
padding:24px;background:radial-gradient(circle at 20% 10%,#234934,#0e1e18 70%);color:#f2f3df;font:18px/1.5 system-ui;text-align:center}
h1{font-size:clamp(25px,6vw,42px);max-width:16ch;line-height:1.15;letter-spacing:-1px;margin:0 0 28px}button{border:1px solid #ffdca5;
border-radius:16px;padding:16px 40px;background:#ffb86b;color:#272217;font:600 18px system-ui;box-shadow:0 8px 0 #81542e,0 18px 40px #0005;
cursor:pointer;transition:transform .16s,box-shadow .16s}button:active{transform:translateY(6px);box-shadow:0 2px 0 #81542e}button:focus-visible{outline:3px solid #fff;outline-offset:6px}
#score{font-size:72px;font-weight:700;font-variant-numeric:tabular-nums;margin:30px 0 0;color:#ccebc8;text-shadow:0 3px 24px #8deb9444}'''


def main():
    output = ROOT / '.harness/polish-checks' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    before = source_manifest()
    runtime = polish_runtime.discover(ROOT)
    fixture = output/'fixture'; (fixture/'examples').mkdir(parents=True); (fixture/'examples/product_demo.py').touch()
    app = App(fixture); app.start('SYNTHETIC overnight polish rehearsal', chat_only=True)
    folder = app.sessions_dir/app.session['id']
    with redirect_stdout(io.StringIO()):
        ref = chat_build.propose_build(fixture,folder,'initial-polish-fixture','Original counter fixture',
            dict(title='Original counter',summary='SYNTHETIC starting game',files=[dict(path=k,content=v) for k,v in FILES.items()]))
    app.respond(ref,'approve','SYNTHETIC TEST: original fixture')
    binary=fixture/'synthetic-muse.exe'; binary.write_bytes(b'Synthetic identity; never executed')
    calls=[]; workers=[]
    def model(root,folder,prompt,phase,**kwargs):
        calls.append(dict(phase=phase,images=len(kwargs['images'])))
        if phase.startswith('critique'):
            score=4 if phase.endswith('-0') else 8 if phase.endswith('-1') else 9
            result=dict(summary='SYNTHETIC assessment of the real screenshot fixture',scores=dict.fromkeys(('visual','feel','clarity','cohesion'),score),
                        core_preserved=True,prefer_candidate=not phase.endswith('-0'),wins=['More cohesive hierarchy and button feedback'],
                        problems=[],next_changes=['Keep the counter and original controls'])
        else:
            files={**FILES,'style.css':STYLE}
            if phase.endswith('-2'):
                files['app.js']=files['app.js'].replace('if(e.key==="ArrowRight")','if(e.key==="SYNTHETIC_DISABLED_CONTROL")')
            result=dict(title='Warm, responsive counter',summary='Cohesive color, hierarchy and tactile button motion',
                        files=[dict(path=k,content=v) for k,v in files.items()])
        return dict(response=json.dumps(result))
    def launch(root,folder,run_id,**kwargs):
        thread=threading.Thread(target=polish.Worker(root,folder,run_id).run,daemon=True);workers.append(thread);thread.start()
        return dict(status='running',id=run_id)
    http=server(app); host=threading.Thread(target=http.serve_forever,daemon=True);host.start()
    error=None
    try:
        env=dict(os.environ,EMBER_PLAYWRIGHT_MODULE=runtime['module'],EMBER_BROWSER_EXECUTABLE=runtime['browser'],
            EMBER_BROWSER_URL=f'http://127.0.0.1:{http.server_port}/',EMBER_BROWSER_TOKEN=app.token,EMBER_BROWSER_OUTPUT=str(output))
        with patch('ember_harness.polish.installed_binary',return_value=binary),patch('ember_harness.polish.run_muse',side_effect=model),\
                patch('ember_harness.polish.launch',side_effect=launch),redirect_stdout(io.StringIO()):
            with (output/'browser.log').open('w',encoding='utf-8') as log:
                result=subprocess.run([runtime['node'],str(ROOT/'tools/polish_check.js')],cwd=ROOT,env=env,
                                      stdout=log,stderr=subprocess.STDOUT,timeout=180)
            if result.returncode:raise ValueError('Polish browser rehearsal failed; see browser.log')
        row=polish.history(fixture,folder)[0]
        if row['best_index']!=1 or len(row['candidates'])!=3 or len(calls)!=5:
            raise ValueError('The run did not keep the strongest candidate and bounded call count')
        if [c['gameplay']['outcome'] for c in row['candidates']] != ['passed','passed','failed']:
            raise ValueError('Gameplay assertions did not reject the error-free scoring regression')
        if row['candidates'][-1]['failures'] != 1:
            raise ValueError('The broken candidate should fail gameplay without browser startup errors')
        if [c['images'] for c in calls]!=[2,2,4,2,4]:raise ValueError('Screenshot comparisons were not attached as planned')
        work,h,packet,plan=polish.load(folder,row['id'])
        if len([e for e in h._entries() if e['kind']=='owner_decision'])!=1:raise ValueError('Iterations invented an owner approval')
        if len(app.snapshot()['build']['completed'])!=2:raise ValueError('Final exact approval did not create the sole new current version')
    except Exception as failure:
        error=str(failure)
    finally:
        for worker in workers:worker.join(timeout=60)
        http.shutdown();http.server_close();host.join()
    unchanged=source_manifest()==before
    report=dict(passed=error is None and unchanged,error=error,source_unchanged=unchanged,source_manifest=before,calls=calls,
        basis='Synthetic owner decisions and model replies; real Chromium inspection and screenshots. No live Muse calls or credit use.',
        checks='Save desktop/touch gameplay plan → run current game → upfront frozen scope → isolated rounds → screenshot critique → reject higher-rated scoring regression with no startup errors → playable review → separate exact approval → restart persistence')
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (output/'REPORT.md').write_text('# Overnight polish browser rehearsal\n\n**'+('PASS' if report['passed'] else 'FAIL')+'**\n\n'+report['basis']+'\n\n'+report['checks']+'\n\nSource unchanged: '+str(unchanged)+('\n\n'+error if error else '')+'\n',encoding='utf-8')
    print('Report: '+str(output/'REPORT.md'))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
