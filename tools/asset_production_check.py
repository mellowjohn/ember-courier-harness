"""Real Blender/concept/UI/refinement rehearsal; synthetic Muse and owner decisions."""
from contextlib import redirect_stdout
import argparse
from datetime import datetime,timezone
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

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ember_harness import asset_run,chat_build,polish_runtime,project_plan,task_run,project_versions
from ember_harness.local_ui import App,server
from ember_harness.recovery import read_json
from tools.release_check import source_manifest


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--integrated',action='store_true',help='Continue the same sample through scope amendment, finding, verified fix and handoff')
    args=parser.parse_args(argv)
    output=ROOT/('.harness/integrated-sample-checks' if args.integrated else '.harness/asset-production-checks')/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True);before=source_manifest();runtime=polish_runtime.discover(ROOT)
    fixture=output/'fixture';(fixture/'examples').mkdir(parents=True);(fixture/'examples/product_demo.py').touch()
    engine=fixture/'.harness/asset-tools/engine.js';engine.parent.mkdir(parents=True)
    shutil.copyfile(ROOT/'.harness/asset-tools/engine.js',engine)
    app=App(fixture);app.start('SYNTHETIC original prop production',chat_only=True);folder=app.sessions_dir/app.session['id']
    document=project_plan.starter(folder)
    document['scope'].update(game_concept='Original courier chest field test',core_loop='Approach, open, deliver and reset',
        features=['Produce and refine an original courier chest'],out_of_scope=['Engine changes','Characters'],asset_budget={'props':1},
        done_criteria=['Approved direction and editable native source','Independent export and keyboard/touch checks','Separate human asset acceptance'])
    document['art_direction'].update(style='Original stylized courier field equipment',palette=['#287566','#BB843C','#FFAD52'])
    with redirect_stdout(io.StringIO()):ref=project_plan.prepare(fixture,folder,document,None)['request_ref']
    app.respond(ref,'approve','SYNTHETIC TEST: original asset project scope')
    binary=fixture/'synthetic-muse.exe';binary.write_bytes(b'Synthetic Muse identity, never executed')
    calls=[];workers=[]
    def model(root,folder,prompt,phase,**kwargs):
        calls.append(dict(phase=phase,images=len(kwargs['images'])))
        if phase=='directions':
            rows=[]
            for i,title in enumerate(('Fieldwork oak','Brass-banded carrier','Fine-slatted dispatch chest')):
                settings={**asset_run.design.DEFAULT,'palette':document['art_direction']['palette'],'slats':(3,5,7)[i],
                    'roughness':(.65,.45,.55)[i],'collision_padding':.5 if i==0 else .02}
                rows.append(dict(title=title,notes='SYNTHETIC direction notes for actual procedural Blender geometry and materials.',design=settings))
            result=dict(directions=rows)
        elif phase.startswith('refine'):
            data=json.loads(prompt.split('\n',1)[1]);result={**data['previous'],'collision_padding':.02,'slats':7,'roughness':.42,'band_width':.07}
        elif phase.startswith('generate'):
            data=json.loads(prompt.split('\n',1)[1]);files=data['files']
            previous="$('deliveries').textContent='1';"
            if files['app.js'].count(previous)!=1:raise ValueError('Expected one original delivery award')
            files['app.js']=files['app.js'].replace(previous,"$('deliveries').textContent='2';")
            result=dict(title='SYNTHETIC two-parcel dispatch fix',summary='Award the two parcels required by the reviewed sample amendment',
                files=[dict(path=k,content=v) for k,v in files.items()])
        else:result=dict(meets_task=True,preserves_scope=True,summary='SYNTHETIC separate assessment of real renders and captures',issues=[])
        return dict(response=json.dumps(result))
    def launch(root,folder,run_id):
        worker=threading.Thread(target=task_run.make_worker(root,folder,run_id).run,daemon=True);workers.append(worker);worker.start()
        return dict(status='running')
    http=server(app);host=threading.Thread(target=http.serve_forever,daemon=True);host.start();error=None
    try:
        env=dict(os.environ,EMBER_PLAYWRIGHT_MODULE=runtime['module'],EMBER_BROWSER_EXECUTABLE=runtime['browser'],
            EMBER_BROWSER_URL=f'http://127.0.0.1:{http.server_port}/',EMBER_BROWSER_TOKEN=app.token,EMBER_BROWSER_OUTPUT=str(output),
            EMBER_INTEGRATED_SAMPLE='1' if args.integrated else '0')
        with patch('ember_harness.asset_run.run_muse',side_effect=model),patch('ember_harness.task_run.run_muse',side_effect=model),patch('ember_harness.task_run.installed_binary',return_value=binary),\
                patch('ember_harness.task_run.launch',side_effect=launch),redirect_stdout(io.StringIO()):
            with (output/'browser.log').open('w',encoding='utf-8') as log:
                result=subprocess.run([runtime['node'],str(ROOT/'tools/asset_production_check.js')],env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=1800 if args.integrated else 600)
            if result.returncode:raise ValueError('Asset production browser rehearsal exited '+str(result.returncode)+'; see browser.log')
        run=task_run.history(fixture,folder)[0]
        if run['status']!='promoted' or len(run['reports'])!=2:raise ValueError('Production and refinement were not retained')
        if [r['qualified'] for r in run['reports']]!=[False,True]:raise ValueError('Real gameplay must block the oversized collision before source refinement')
        if [c['phase'] for c in calls]!=['directions','verify-1','refine-2','verify-2']+(['generate-1','verify-1'] if args.integrated else []):raise ValueError('Unexpected provider request or replay')
        if [c['images'] for c in calls]!=[0,4,2,4]+([0,2] if args.integrated else []):raise ValueError('Independent review did not consume native and runtime renders')
        work,h,packet,plan=task_run.load(folder,run['id'])
        if len([e for e in h._entries() if e['kind']=='asset_direction_locked'])!=1:raise ValueError('The direction requires one explicit pick')
        for index in (1,2):
            if not (work/'production'/str(index)/'export/delivery-chest.blend').is_file():raise ValueError('Editable native sources were not retained')
        current=chat_build.status(fixture,folder)['completed'][-1]['request_ref']
        game=project_versions.snapshot(fixture,folder,current)
        if 'asset.js' not in game['files']:raise ValueError('Final exact asset was not applied')
        exported,_=project_versions.export(fixture,folder,current);(output/'original-prop.zip').write_bytes(exported)
        if args.integrated:
            with zipfile.ZipFile(output/'project-handoff.zip') as archive:
                handoff=json.loads(archive.read('project-report.json'))
                if archive.read('game.zip')!=exported:raise ValueError('Handoff contains a different game')
            if handoff['build']['request_ref']!=current or handoff['project_plan']['approved']['version']!=2:
                raise ValueError('Handoff lost the amended scope or current build')
            original=project_versions.snapshot(fixture,folder,run['proposal_ref'])
            for name in ('asset.js','engine.js'):
                if original['manifest'][name]!=game['manifest'][name]:raise ValueError('Fix changed accepted asset/runtime')
            if len(handoff['findings'])!=1 or not handoff['findings'][0]['closure_applies_to_current_build']:
                raise ValueError('Finding lacks exact-build explicit closure')
            if not handoff['project_plan']['tasks'][1]['acceptance_applies_to_current_build']:
                raise ValueError('Amended task lacks separate outcome acceptance')
            if handoff['gameplay']['current_build_checks'][-1]['outcome']!='passed':raise ValueError('Handoff lacks real current checks')
            if len(handoff['project_plan']['acceptance_history'])!=2:raise ValueError('Historical asset-task acceptance was lost')
            if len(handoff['task_runs'])!=2 or handoff['evidence']['contract_lock']!='passed':raise ValueError('Cross-workflow evidence is incomplete')
            fix=next(row for row in task_run.history(fixture,folder) if row.get('kind')=='finding')
            if task_run.load(folder,fix['id'])[3]['finding']['regression_scenario']!=1:raise ValueError('The selected keyboard regression was not retained')
            from ember_harness import project_handoff
            data,_=app.export_handoff(folder.name,current)
            if data!=(output/'project-handoff.zip').read_bytes():raise ValueError('Handoff is not stable on re-download')
            asset=work/'production/2/export/delivery-chest.glb';raw=asset.read_bytes()
            try:
                asset.write_bytes(raw+b'SYNTHETIC tamper probe')
                try:project_handoff.export(fixture,folder,current)
                except ValueError:pass
                else:raise ValueError('Changed native production evidence did not block handoff')
            finally:asset.write_bytes(raw)
        report_path=work/'production/2/export'
    except Exception as failure:error=str(failure);report_path=None
    finally:
        for worker in workers:worker.join(timeout=30)
        http.shutdown();http.server_close();host.join()
    unchanged=before==source_manifest()
    report=dict(passed=error is None and unchanged,error=error,source_unchanged=unchanged,source_manifest=before,
        basis='Real Blender renders, editable sources, exports and Chromium checks. Muse judgments and owner decisions are synthetic; no live credits or human acceptance.',
        checks='scope → reviewed producer/verifier → three real concept studies → explicit direction pick → oversized collider fails fixed gameplay despite positive AI judgment → bounded Blender source refinement → independent GLB and desktop/touch checks → exact asset acceptance → separate task acceptance → ZIP',
        source=str(report_path) if report_path else None,calls=calls)
    if args.integrated:
        report['checks']+=' → reviewed scope v2 with separate widening acknowledgement → failing two-parcel regression → reviewed finding → scoped fix preserving accepted GLB/runtime → separate Chromium/AI review → exact apply → explicit closure → separate task acceptance → current desktop/touch checks → stable verified handoff → changed production evidence blocks download'
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (output/'REPORT.md').write_text('# Original prop production rehearsal\n\n**'+('PASS' if report['passed'] else 'FAIL')+'**\n\n'+report['basis']+'\n\n'+report['checks']+'\n\n'+(error or 'All source bindings unchanged.')+'\n',encoding='utf-8')
    print('Report: '+str(output/'REPORT.md'));return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
