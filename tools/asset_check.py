"""Real Blender -> GLB -> Three.js -> failed playtest -> source refinement rehearsal.

Owner decisions are synthetic and confined to the generated fixture workspace.
"""
from contextlib import redirect_stdout
from datetime import datetime, timezone
from hashlib import sha256
import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ember_harness import asset_pipeline, asset_workshop, chat_build, gameplay, project_versions, polish_runtime
from ember_harness.local_ui import App
from tools.release_check import source_manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender',type=Path,required=True)
    parser.add_argument('--engine',type=Path,required=True)
    parser.add_argument('--asset',choices=('chest','gate'),default='chest')
    args=parser.parse_args()
    output=ROOT/'.harness/asset-checks'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    before=source_manifest();report=dict(passed=False,asset=args.asset,basis='Real Blender exports and Chromium input. Synthetic owner decisions in an isolated fixture; no Muse calls or human asset acceptance.')
    try:
        asset_id='delivery-chest' if args.asset=='chest' else 'courier-waygate'
        generator='blender_delivery_chest.py' if args.asset=='chest' else 'blender_courier_gate.py'
        for name in ('blocked','refined'):
            options=['--collision-padding','.5' if name=='blocked' else '.02'] if args.asset=='chest' else (['--fixed-collider'] if name=='blocked' else [])
            with (output/(name+'-blender.log')).open('wb') as log:
                result=subprocess.run([str(args.blender.resolve()),'--background','--python',str(ROOT/'tools'/generator),
                    '--','--output',str(output/name),*options],stdout=log,stderr=log,timeout=60)
            if result.returncode or not (output/name/(asset_id+'.glb')).is_file():raise ValueError('Blender export failed; inspect retained log')
        if args.asset=='gate':
            try: asset_workshop.files(output/'blocked',args.engine)
            except ValueError as error:
                if 'passage collider' not in str(error): raise
                report['blocked']=dict(outcome='rejected',reason=str(error))
            else: raise ValueError('The fixed passage collider was incorrectly accepted')
        fixture=output/'fixture';(fixture/'examples').mkdir(parents=True);(fixture/'examples/product_demo.py').touch()
        app=App(fixture);app.start('SYNTHETIC asset pipeline rehearsal',chat_only=True)
        folder=app.sessions_dir/app.session['id']
        spec=json.loads((output/'refined/asset-spec.json').read_text())
        saved=gameplay.save(folder,asset_workshop.plan(spec),0)
        refs=[];comparison=None
        variants=('blocked','refined') if args.asset=='chest' else ('refined',)
        for name in variants:
            files=asset_workshop.files(output/name,args.engine)
            with redirect_stdout(io.StringIO()):
                ref=chat_build.propose_build(fixture,folder,name,'SYNTHETIC asset pipeline fixture',
                    dict(title=name+' '+asset_id,summary='Synthetic acceptance rehearsal',files=[dict(path=k,content=v) for k,v in files.items()]),
                    expected_before=chat_build.context(fixture,folder)['sha256'])
            refs.append(ref)
            if name=='refined':
                current=chat_build.context(fixture,folder)['manifest']
                comparison=gameplay.run_proposal(fixture,folder,saved['revision'],ref,'asset-proposal-'+uuid.uuid4().hex)
                if comparison['outcome']!='passed' or (args.asset=='chest' and not any(row['change']=='fixed' for row in comparison['comparison'])):
                    raise ValueError('Refined proposal did not fix the failed baseline: '+json.dumps(comparison['comparison']))
                if chat_build.context(fixture,folder)['manifest']!=current:raise ValueError('Proposal playtest wrote current project')
            app.respond(ref,'approve','SYNTHETIC TEST: accept this fixture asset and exact build')
            observed=gameplay.run_current(fixture,folder,saved['revision'],ref,'asset-'+name+'-'+uuid.uuid4().hex)
            report[name]=dict(request_ref=ref,outcome=observed['outcome'],scenarios=observed['gameplay']['scenarios'])
        if report['blocked']['outcome']!=('failed' if args.asset=='chest' else 'rejected') or report['refined']['outcome']!='passed':
            raise ValueError('Expected the broken asset to fail and refinement to pass')
        chat_build.verify(fixture,folder)
        runtime=polish_runtime.discover(ROOT)
        scene_input=output/'scene-input.json'
        descriptor=asset_pipeline.describe(asset_pipeline.unpack(files['asset.js'])[1])
        scene_input.write_text(json.dumps(dict(html=chat_build.preview(fixture,folder),interaction=descriptor['interaction'],
            frame_probe_node='COLLISION_PostRight' if args.asset=='gate' else None)),encoding='utf-8')
        env=dict(os.environ,EMBER_PLAYWRIGHT_MODULE=runtime['module'],EMBER_BROWSER_EXECUTABLE=runtime['browser'])
        with (output/'scene-check.log').open('wb') as log:
            result=subprocess.run([runtime['node'],str(ROOT/'tools/asset_scene_check.js'),str(scene_input),str(output/'scene-check')],
                env=env,stdout=log,stderr=log,timeout=55)
        if result.returncode:raise ValueError('Actual scene inspection failed; see scene-check.log')
        report['scene_inspection']=json.loads((output/'scene-check/report.json').read_text())
        archive,_=project_versions.export(fixture,folder,refs[-1]);(output/(asset_id+'-game.zip')).write_bytes(archive)
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            if zipped.read(asset_id+'.glb')!=(output/'refined'/(asset_id+'.glb')).read_bytes():raise ValueError('ZIP changed exported GLB bytes')
        # Reopening must retain exact history and acceptance receipts.
        reopened=App(fixture);reopened.resume(app.session['id']);reopened.verify()
        entries=chat_build.harness(folder)._entries()
        accepts=[e for e in entries if e['kind']=='decision' and e.get('decision')=='allow' and e.get('action',{}).get('tool')=='asset.accept']
        if len(accepts)!=len(variants):raise ValueError('Each changed asset needs its own exact acceptance')
        report.update(passed=True,comparison=comparison['comparison'],asset_acceptances=len(accepts),
            session_id=app.session['id'],fixture=str(fixture),exports={name:sha256((output/name/(asset_id+'.glb')).read_bytes()).hexdigest() for name in ('blocked','refined')})
    except Exception as error:
        report['error']=str(error)
    report['source_manifest']=before;report['source_unchanged']=before==source_manifest();report['passed'] &= report['source_unchanged']
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (output/'REPORT.md').write_text('# Asset pipeline rehearsal\n\n**'+('PASS' if report['passed'] else 'FAIL')+'**\n\n'+report['basis']+'\n\n'+
        (('Oversized collision → failed desktop/touch reach checks → Blender collision refinement → passing proposal comparison → exact fixture acceptance → passing current checks → verified GLB ZIP and restart.' if args.asset=='chest' else
          'Fixed passage collider rejected → Blender parenting corrected → unapplied proposal and desktop/touch checks → actual Y-axis hinge, traversable passage and closing obstruction checks → exact GLB ZIP and restart.') if report['passed'] else report.get('error','Source changed'))+'\n',encoding='utf-8')
    print(str(output/'REPORT.md'))
    return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
