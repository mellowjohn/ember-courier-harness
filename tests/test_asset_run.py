"""Synthetic Blender/provider fixtures exercise real contracts, files and receipts."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
import test_asset_pipeline as glbs
import test_polish as browser_fixture
import test_project_plan as project_fixture
from ember_harness import asset_run, chat_build, project_plan, task_run
from ember_harness.blender import design
from ember_harness.core import subset
from ember_harness.recovery import atomic_json, read_json


class AssetRunTests(unittest.TestCase):
    def setUp(self):
        quiet=redirect_stdout(io.StringIO());quiet.__enter__();self.addCleanup(quiet.__exit__,None,None,None)
        self.fixture=project_fixture.ProjectPlanTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root,self.folder,self.app=self.fixture.root,self.fixture.folder,self.fixture.app
        self.fixture.document['scope']['asset_budget']={'props':1}
        self.plan_ref=self.fixture.approve()
        engine=self.root/'.harness/asset-tools/engine.js';engine.parent.mkdir(parents=True);engine.write_bytes(b'globalThis.Ember3D={};\r\n')
        self.binary=self.root/'synthetic-blender.exe';self.binary.write_bytes(b'SYNTHETIC identity; never executed')
        self.runtime=dict(node=str(self.binary),browser=str(self.binary),module=str(self.root),driver=str(asset_run.polish_runtime.DRIVER),hashes={})
        for name in ('blender_binary',):
            p=patch('ember_harness.asset_run.'+name,return_value=self.binary);p.start();self.addCleanup(p.stop)
        for name,result in [('ember_harness.task_run.installed_binary',self.binary),('ember_harness.polish_runtime.discover',self.runtime)]:
            p=patch(name,return_value=result);p.start();self.addCleanup(p.stop)
        self.palette=self.fixture.document['art_direction']['palette'];self.calls=[];self.exports=[];self.good=True

    def prepare(self): return task_run.prepare(self.root,self.folder,asset_profile='chest')['id']

    def approve(self,run):
        with patch('ember_harness.task_run.launch',return_value={'status':'ready'}):
            task_run.respond(self.root,self.folder,run,'approve','SYNTHETIC TEST: reviewed original prop production')

    def model(self,root,folder,prompt,phase,**kwargs):
        self.calls.append((phase,kwargs))
        if phase=='directions':
            result=dict(directions=[dict(title='Original direction '+str(i),notes='SYNTHETIC silhouette and material notes',
                design={**design.DEFAULT,'palette':self.palette,'slats':i}) for i in (3,5,7)])
        elif phase.startswith('refine'):
            data=json.loads(prompt.split('\n',1)[1]);result={**data['previous'],'roughness':.4,'collision_padding':.01}
        else: result=dict(meets_task=self.good,preserves_scope=True,summary='SYNTHETIC independent visual judgment',issues=[] if self.good else ['Refine trim readability'])
        return dict(response=json.dumps(result))

    def blender(self,args,**kwargs):
        output=Path(args[args.index('--output')+1]);output.mkdir()
        settings=read_json(args[args.index('--design')+1]);self.exports.append(settings)
        actual=asset_run.spec('chest',self.fixture.document['art_direction']['style'])
        atomic_json(output/'asset-spec.json',actual);atomic_json(output/'production-design.json',settings)
        raw=bytearray(glbs.glb(lambda doc:doc['materials'][0]['pbrMetallicRoughness'].update(roughnessFactor=settings['roughness'])))
        binary_offset=20+struct.unpack_from('<I',raw,12)[0]+8
        struct.pack_into('<9f',raw,binary_offset,-.605,0,-.4105,.605,.81,-.4105,0,0,.4105)
        (output/'delivery-chest.glb').write_bytes(raw)
        (output/'delivery-chest.blend').write_bytes(b'SYNTHETIC native source '+json.dumps(settings).encode())
        for view in ('hero','impact'): Image.new('RGB',(40,30),settings['palette'][0]).save(output/(view+'.png'))
        return SimpleNamespace(poll=lambda:0,returncode=0)

    def browser(self,runtime,source,output,**kwargs):
        # Reuse the canonical complete screenshot/gameplay fixture without starting its setup.
        return browser_fixture.PolishTests.browser(self,runtime,source,output,**kwargs)

    def worker(self,run):
        with patch('ember_harness.asset_run.run_muse',side_effect=self.model),patch('ember_harness.asset_run.subprocess.Popen',side_effect=self.blender),patch(
                'ember_harness.polish_runtime.inspect',side_effect=self.browser):
            asset_run.Worker(self.root,self.folder,run).run()
        return next(r for r in task_run.history(self.root,self.folder) if r['id']==run)

    def choose(self,run,choice='direction-1'):
        with patch('ember_harness.task_run.launch',return_value={'status':'ready'}):
            return asset_run.choose(self.root,self.folder,run,choice)

    def test_concepts_require_explicit_pick_then_independent_verification_and_asset_acceptance(self):
        run=self.prepare();self.approve(run)
        row=self.worker(run)
        self.assertEqual(row['status'],'awaiting_direction',row.get('error'));self.assertEqual(len(self.exports),3)
        self.assertEqual([c[0] for c in self.calls],['directions'])
        self.assertFalse(chat_build.project(self.root,self.folder).exists())
        self.assertTrue(asset_run.image(self.folder,run,'direction-1','hero').startswith(b'\x89PNG'))
        self.choose(run);row=self.worker(run)
        self.assertEqual(row['status'],'ready_review',row.get('error'));self.assertEqual(len(self.exports),4)
        self.assertEqual(len(self.calls[-1][1]['images']),4)
        work,h,packet,plan=task_run.load(self.folder,run)
        self.assertEqual(len([e for e in h._entries() if e['kind']=='asset_direction_locked']),1)
        self.assertFalse([e for e in h._entries() if e['kind']=='asset_acceptance'])
        ref=task_run.promote(self.root,self.folder,run)['request_ref']
        self.assertIn('asset_source',chat_build.list_requests(self.folder)[0]['payload']['body']['build'])
        self.app.respond(ref,'approve','SYNTHETIC TEST: accept exact original asset and game')
        self.assertEqual(project_plan.status(self.root,self.folder)['tasks'][0]['state'],'applied_needs_review')
        decisions=[e for e in h._entries() if e['kind']=='approval' and e.get('scope')=='action']
        self.assertGreaterEqual(len(decisions),2) # chosen direction and separately accepted exact GLB
        self.assertTrue(h.audit_verify()['ok'])

    def test_selected_native_task_automatically_routes_without_manual_profile(self):
        document=deepcopy(self.fixture.document)
        document['scope']['features'][0]='Create original chest prop'
        ref=self.fixture.prepare(document)
        project_plan.acknowledge(self.root,self.folder,ref,'SYNTHETIC native task scope')
        self.app.respond(ref,'approve','SYNTHETIC approve native task')
        self.assertEqual(project_plan.status(self.root,self.folder)['tasks'][0]['production_profile'],'chest')
        run=task_run.prepare(self.root,self.folder)['id']
        plan=task_run.load(self.folder,run)[3]
        self.assertEqual(plan['kind'],'asset');self.assertEqual(plan['profile'],'chest')
        self.approve(run)
        self.assertEqual(self.worker(run)['status'],'awaiting_direction')

    def test_refinement_edits_parametric_source_preserves_direction_and_keeps_native_versions(self):
        run=self.prepare();self.approve(run);self.worker(run);self.choose(run)
        self.good=False;first=self.worker(run);self.assertEqual(first['status'],'awaiting_refinement',first.get('error'))
        work=task_run.run_folder(self.folder,run);native=work/'production/1/export/delivery-chest.blend';before=native.read_bytes()
        with patch('ember_harness.task_run.launch',return_value={'status':'ready'}):
            asset_run.refine(self.root,self.folder,run,'Improve readability and soften the trim')
        self.good=True;second=self.worker(run)
        self.assertEqual(second['status'],'ready_review',second.get('error'));self.assertEqual(len(second['reports']),2)
        self.assertEqual(native.read_bytes(),before)
        self.assertNotEqual((work/'production/2/export/delivery-chest.blend').read_bytes(),before)
        self.assertEqual(second['reports'][0]['design']['palette'],second['reports'][1]['design']['palette'])
        self.assertEqual(len(second['attempts']['attempts']),2)

    def test_direction_and_native_tampering_cannot_supply_a_new_pick_or_promotion(self):
        run=self.prepare();self.approve(run);self.worker(run)
        work=task_run.run_folder(self.folder,run);path=work/'concepts/direction-1/export/hero.png';raw=path.read_bytes();path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'artifact changed'): self.choose(run)
        path.write_bytes(raw);self.choose(run);self.worker(run)
        native=work/'production/1/export/delivery-chest.blend';native.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'artifact changed'): task_run.promote(self.root,self.folder,run)
        self.assertEqual(task_run.history(self.root,self.folder)[0]['status'],'inspection_required')

    def test_verifier_cannot_produce_or_edit_sources_and_contracts_inherit_the_scope(self):
        run=self.prepare();self.approve(run)
        work,h,packet,plan=task_run.load(self.folder,run);active=h._active(h._entries())
        root=h._authority(active[plan['project_plan']['binding']['contract_id']],active)
        coder,verifier,concept=[c['contract'] for c in packet['body']['contracts']]
        self.assertTrue(subset(coder,root));self.assertTrue(subset(verifier,root))
        self.assertTrue(subset(concept,root))
        self.assertEqual(len({c['agent'] for c in (coder,verifier,concept)}),3)
        self.assertEqual(verifier['art_direction'],root['art_direction'])
        action=dict(agent=verifier['agent'],contract_id=verifier['id'],contract_version=1,tool='asset.produce',
            args=dict(script=plan['script'],design=(work/'production/1/design.json').as_posix(),destination=(work/'production/1/export').as_posix(),binary_sha256=plan['blender_sha256']),
            paths=dict(read=[plan['script'],(work/'production/1/design.json').as_posix()],write=[(work/'production/1/export').as_posix()]),spend=0)
        self.assertEqual(h.check(action)['decision'],'deny')
        action.update(agent=concept['agent'],contract_id=concept['id'])
        self.assertEqual(h.check(action)['decision'],'deny')
        concept_design=(work/'concepts/direction-1/design.json').as_posix()
        action.update(agent=coder['agent'],contract_id=coder['id'])
        action['args'].update(design=concept_design,destination=(work/'concepts/direction-1/export').as_posix())
        action['paths']=dict(read=[plan['script'],concept_design],write=[(work/'concepts/direction-1/export').as_posix()])
        self.assertEqual(h.check(action)['decision'],'deny')

    def test_revocation_or_changed_blender_stops_before_external_production(self):
        run=self.prepare();self.approve(run);self.binary.write_bytes(b'Changed executable')
        row=self.worker(run);self.assertEqual(row['status'],'interrupted');self.assertFalse(self.exports)
        self.assertIn('binary changed',row['error']) # Muse and Blender share the synthetic identity in this fixture
        h=chat_build.harness(self.folder);h.revoke(project_plan.status(self.root,self.folder)['approved']['contract_id'],approver='johnathan',reason='SYNTHETIC revoke')
        self.worker(run);self.assertFalse(self.exports)

    def test_unsupported_profile_cannot_start_production(self):
        with self.assertRaisesRegex(ValueError,'chest or gate'): task_run.prepare(self.root,self.folder,asset_profile='character')

    def test_zero_asset_estimate_does_not_block_reviewed_production(self):
        document=deepcopy(self.fixture.document);document['scope']['asset_budget']={'props':0}
        ref=self.fixture.prepare(document);project_plan.acknowledge(self.root,self.folder,ref,'SYNTHETIC acknowledge renewal')
        self.app.respond(ref,'approve','SYNTHETIC zero asset scope')
        run=self.prepare()
        _,_,packet,plan=task_run.load(self.folder,run)
        self.assertEqual(plan['kind'],'asset')
        self.assertFalse(self.calls)
        self.assertFalse(self.exports)
        self.assertIsNotNone(packet['body']['contracts'])

    def test_design_rejects_paths_scripts_nonfinite_values_and_unknown_controls(self):
        for changed in [{**design.DEFAULT,'script':'evil.py'},{**design.DEFAULT,'bevel':float('nan')},
            {**design.DEFAULT,'collision_padding':-1},{**design.DEFAULT,'slats':True},{**design.DEFAULT,'palette':['red']*3}]:
            with self.assertRaises(ValueError):design.validate(changed)

    def test_restart_replays_concepts_without_more_model_calls_or_blender_exports(self):
        run=self.prepare();self.approve(run);self.worker(run)
        self.assertEqual(self.worker(run)['status'],'awaiting_direction')
        self.assertEqual([c[0] for c in self.calls],['directions']);self.assertEqual(len(self.exports),3)
        self.choose(run);self.good=False;self.worker(run)
        for number in (2,3):
            with patch('ember_harness.task_run.launch',return_value={'status':'ready'}):
                asset_run.refine(self.root,self.folder,run,'Refine the source and retain every prior export')
            row=self.worker(run)
        self.assertEqual(row['status'],'awaiting_decision');self.assertEqual(len(row['attempts']['attempts']),3)
        with self.assertRaisesRegex(ValueError,'limit reached'):self.prepare()

    def test_specification_widening_after_blender_export_is_rejected_independently(self):
        original=self.blender
        def wrong_export(args,**kwargs):
            result=original(args,**kwargs)
            if '/production/' in str(Path(args[args.index('--output')+1]).as_posix()):
                path=Path(args[args.index('--output')+1])/'asset-spec.json'
                data=read_json(path);data['dimension_tolerance_m']=.05;atomic_json(path,data)
            return result
        run=self.prepare();self.approve(run);self.worker(run);self.choose(run)
        self.blender=wrong_export
        row=self.worker(run)
        self.assertEqual(row['status'],'interrupted');self.assertIn('locked direction',row['error'])
        self.assertFalse(row['reports']);self.assertFalse(chat_build.list_requests(self.folder))


if __name__=='__main__':unittest.main()
