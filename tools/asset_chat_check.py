"""Real browser chat-to-asset rehearsal; synthetic model replies and fixture decisions."""
from contextlib import redirect_stdout
from datetime import datetime, timezone
from hashlib import sha256
import argparse
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from unittest.mock import patch
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ember_harness import asset_library, asset_pipeline, chat_build, gameplay, polish_runtime, project_versions, session_chat
from ember_harness.local_ui import App, server
from tools.release_check import source_manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--engine',type=Path,required=True)
    parser.add_argument('--updated-source',type=Path,help='Also rehearse reviewing a revised export in the same scene')
    args=parser.parse_args()
    output=ROOT/'.harness/asset-chat-checks'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True);before=source_manifest()
    fixture=output/'fixture';(fixture/'examples').mkdir(parents=True);(fixture/'examples/product_demo.py').touch()
    runtime_path=fixture/'.harness/asset-tools/engine.js';runtime_path.parent.mkdir(parents=True);shutil.copyfile(args.engine,runtime_path)
    tracked=fixture/'.harness/asset-source/tracked';shutil.copytree(args.source,tracked)
    ref=asset_library.register(fixture,tracked)
    record,spec,asset_report=asset_library.load(fixture,ref)
    updated_report=None
    if args.updated_source:
        updated_spec=json.loads((args.updated_source/'asset-spec.json').read_text(encoding='utf-8'))
        if updated_spec['id']!=spec['id']:raise ValueError('The revised export must use the same asset ID')
        updated_report=asset_pipeline.inspect_glb((args.updated_source/(spec['id']+'.glb')).read_bytes(),updated_spec)
        if updated_report['sha256']==asset_report['sha256']:raise ValueError('Supply a revised GLB with different bytes')
    app=App(fixture);app.start('SYNTHETIC asset-aware conversation',chat_only=True)
    folder=app.sessions_dir/app.session['id'];calls=[]
    def model(root,session,prompt,turn,**kwargs):
        data=json.loads(prompt.split('\n',1)[1]);library=data['asset_library']
        selected=next(v for v in library['assets'] if v['ref']==ref)
        if selected['sources']['blender']['path']!=record['sources']['blender']['path']:
            raise ValueError('The conversation lost the actual Blender source path')
        text=data['conversation'][-1]['content'].lower()
        if 'where' in text:
            reply=dict(message='The '+record['display_name']+' Blender source is '+selected['sources']['blender']['path'],
                       build=None,asset=dict(ref=ref,intent='discuss'))
        elif 'put it' in text:
            if library['focus_ref']!=ref:raise ValueError('The follow-up lost its asset reference')
            reply=dict(message='Review the actual recorded '+record['display_name']+' in this playable scene.',
                       build=None,asset=dict(ref=ref,intent='use'))
        else:
            if any('content' in v for v in data['project']['files'] if v['path'] in ('asset.js','engine.js')):
                raise ValueError('The model was asked to copy binary or vendor payloads')
            files=[]
            for row in data['project']['files']:
                if 'content' not in row:continue
                content=row['content']+'\nbody {background-color:#14271f}' if row['path']=='style.css' else row['content']
                files.append(dict(path=row['path'],content=content))
            reply=dict(message='Review the scene color refinement; the recorded asset stays in place.',
                       build=dict(title='Scene color refinement',summary='Retain the known GLB',files=files))
        calls.append(dict(turn=turn,focus=library['focus_ref'],prompt_chars=len(prompt)))
        return dict(response=json.dumps(reply))
    runtime=polish_runtime.discover(ROOT);http=server(app)
    worker=threading.Thread(target=http.serve_forever,daemon=True);worker.start()
    error=None
    try:
        env=dict(os.environ,EMBER_PLAYWRIGHT_MODULE=runtime['module'],EMBER_BROWSER_EXECUTABLE=runtime['browser'],
            EMBER_BROWSER_URL=f'http://127.0.0.1:{http.server_port}/',EMBER_BROWSER_TOKEN=app.token,
            EMBER_BROWSER_OUTPUT=str(output),EMBER_ASSET_NAME=record['display_name'],EMBER_ASSET_SOURCE=record['sources']['blender']['path'])
        if args.updated_source:
            env.update(EMBER_ASSET_TRACKED_SOURCE=str(tracked),EMBER_ASSET_UPDATE_SOURCE=str(args.updated_source.resolve()),
                       EMBER_ASSET_ID=spec['id'],EMBER_ASSET_OLD_SHA=asset_report['sha256'],EMBER_ASSET_NEW_SHA=updated_report['sha256'])
        with patch('ember_harness.session_chat.run_muse',side_effect=model),redirect_stdout(io.StringIO()):
            with (output/'browser.log').open('wb') as log:
                result=subprocess.run([runtime['node'],str(ROOT/'tools/asset_chat_check.js')],cwd=ROOT,env=env,stdout=log,stderr=log,timeout=240)
            if result.returncode:raise ValueError('Asset conversation browser rehearsal failed; inspect browser.log')
        if len(calls)!=3:raise ValueError('The browser did not exercise discussion, use and revision')
        state=chat_build.status(fixture,folder)
        if len(state['completed'])!=(3 if updated_report else 2):raise ValueError('Expected asset acceptance, code-only acceptance and optional asset update')
        snapshots=[project_versions.snapshot(fixture,folder,v['request_ref']) for v in state['completed']]
        if snapshots[0]['files']['asset.js']!=snapshots[1]['files']['asset.js'] or snapshots[0]['files']['engine.js']!=snapshots[1]['files']['engine.js']:
            raise ValueError('Scene revision changed the retained asset or runtime')
        if updated_report:
            if {k:v for k,v in snapshots[1]['files'].items() if k!='asset.js'}!={k:v for k,v in snapshots[2]['files'].items() if k!='asset.js'}:
                raise ValueError('Asset update changed the customized scene or runtime')
            if asset_pipeline.unpack(snapshots[2]['files']['asset.js'])[2]['sha256']!=updated_report['sha256']:
                raise ValueError('Asset update lost revised GLB identity')
        accepted=[e for e in chat_build.harness(folder)._entries() if e['kind']=='decision' and e.get('decision')=='allow' and e.get('action',{}).get('tool')=='asset.accept']
        if len(accepted)!=(2 if updated_report else 1):raise ValueError('Each changed asset needs its own individual fixture acceptance')
        archive,_=project_versions.export(fixture,folder,state['completed'][-1]['request_ref'])
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            if sha256(zipped.read(spec['id']+'.glb')).hexdigest()!=(updated_report or asset_report)['sha256']:raise ValueError('Export lost exact asset identity')
        (output/'asset-game.zip').write_bytes(archive)
        fresh=App(fixture);fresh.resume(folder.name)
        focus=fresh.snapshot()['asset_library']['focus_ref']
        if asset_library.load(fixture,focus)[2]['sha256']!=(updated_report or asset_report)['sha256']:raise ValueError('Asset focus did not survive restart')
    except Exception as failure:error=str(failure)
    finally:http.shutdown();http.server_close();worker.join()
    report=dict(passed=error is None and before==source_manifest(),error=error,source_unchanged=before==source_manifest(),
        source_manifest=before,calls=calls,asset_sha256=asset_report['sha256'],
        updated_asset_sha256=updated_report['sha256'] if updated_report else None,
        basis='Synthetic model replies and owner decisions in an isolated fixture; real Chromium chat, preview, keyboard/touch input and code revision. No live Muse calls.',
        checks='Known source in chat → discussion reference → reload → put it in scene → unapplied actual GLB preview → saved gameplay checks → separate fixture acceptance → retained asset during code edit → exact ZIP and restarted focus'+
            (' → invalid update rejected → revised GLB preview → unchanged scene and plan → desktop/touch comparison → reloaded pending review → separate updated-asset acceptance' if updated_report else ''))
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (output/'REPORT.md').write_text('# Asset-aware conversation rehearsal\n\n**'+('PASS' if report['passed'] else 'FAIL')+'**\n\n'+report['basis']+'\n\n'+report['checks']+('\n\n'+error if error else '')+'\n',encoding='utf-8')
    print(str(output/'REPORT.md'));return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
