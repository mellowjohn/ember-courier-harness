"""Artwork-first execution with real asset preparation and synthetic providers."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

import test_task_run as tasks
import test_chat_build as builds
import test_muse_image as images
from quality_fixture import assessments, comparison
from ember_harness import asset_2d, chat_build, muse_image, project_plan, sprite_project, task_artwork, task_run
from ember_harness.core import subset
from ember_harness.muse_chat import CreditLedger, IMAGE_MODEL


class ArtworkTaskTests(unittest.TestCase):
    def setUp(self):
        self.fixture = tasks.TaskRunTests(); self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.root, self.app = self.fixture.root, self.fixture.app
        self.app.start('SYNTHETIC first game with artwork', chat_only=True)
        self.folder = self.app.sessions_dir / self.app.session['id']
        self.fixture.folder = self.folder
        from ember_harness import gameplay
        import test_gameplay as checks
        gameplay.save(self.folder, checks.PLAN, 0)
        document = project_plan.starter(self.folder)
        document['scope']['features'] = ['Create the courier scene, player interaction and environment']
        ref = project_plan.prepare(self.root, self.folder, document, None)['request_ref']
        self.app.respond(ref, 'approve', 'SYNTHETIC artwork-first project scope')
        self.network = images.MuseImageTests(); self.network.setUp(); self.addCleanup(self.network.doCleanups)
        muse_image.verify_coverage(self.root, 150_000_000, no_paid_fallback=True)
        self.phases = []
        self.entities = []
        for name, role, kind in [('courier', 'player', 'sprite'), ('world', 'background', 'background')]:
            spec = deepcopy(self.network.spec)
            spec.update(id=name, display_name=name.title(), kind=kind, grid=[1,1], frames=1,
                frame_size=[256,256], require_alpha=role=='player')
            self.entities.append(dict(id=name, role=role, purpose='SYNTHETIC '+role, activation='startup',
                required_clips=['default'], asset_ref=None, generation=spec, binding=dict(file='app.js', replace=''), machine=None))

    def model(self, root, folder, prompt, phase, **kwargs):
        self.phases.append(phase)
        data = json.loads(prompt.split('\n', 1)[1])
        if phase == 'artwork-1':
            self.assertEqual(data['files'], {})
            files = deepcopy(builds.PROJECT)
            files['index.html'] = files['index.html'].replace('<body>', '<body><canvas id="scene" width="256" height="256"></canvas>')
            files['app.js'] += "\nEmberSprites.createScene(EMBER_SPRITE_PLAN,EMBER_SPRITE_ASSETS).then(scene=>{const ctx=document.querySelector('canvas').getContext('2d');const bg=scene.createEntity('world');bg.draw(ctx,0,0);const hero=scene.createEntity('courier');hero.draw(ctx,128,220);});"
            result = dict(build=dict(title='Artwork scene', summary='SYNTHETIC scene bindings',
                files=[dict(path=k,content=v) for k,v in files.items()]),
                sprite_project=dict(intent='implement',expected_revision=0,plan=dict(version=1,entities=self.entities)))
        elif phase.startswith('generate-'):
            self.assertEqual(len(data['sprite_assets']), 2)
            self.assertNotIn(sprite_project.ASSETS_FILE, data['files'])
            self.assertIn("createEntity('courier')", data['files']['app.js'])
            result = dict(title='Playable courier', summary='SYNTHETIC implementation',
                edits=[dict(path='style.css',before=data['files']['style.css'],after='body{background:#243;color:white;padding:20px}')])
        else:
            result = dict(meets_task=True, preserves_scope=True, summary='SYNTHETIC independent check', issues=[], criteria=assessments(data))
            if data.get('comparison'):
                result['comparison'] = comparison(data)
        return dict(response=json.dumps(result))

    def test_generation_precedes_implementation_and_separate_asset_acceptance(self):
        run = self.fixture.prepare()
        work, h, packet, plan = task_run.load(self.folder, run)
        self.assertEqual([s['id'] for s in plan['delegation']['stages']], ['artwork','implement','verify'])
        self.assertEqual(plan['rounds'], 2)
        from ember_harness.muse_chat import RESERVATION_MICRO_USD
        self.assertLessEqual((1 + 2 * plan['rounds']) * RESERVATION_MICRO_USD + plan['artwork']['max_image_micro_usd'], plan['credits'] * 1_000_000)
        parent = project_plan.check_binding(self.root, self.folder, plan['project_plan']['binding'])
        self.assertTrue(all(subset(item['contract'], parent) for item in packet['body']['contracts']))
        self.assertEqual(self.phases, [])
        self.fixture.approve(run)
        with patch('ember_harness.muse_image.build_opener', return_value=self.network.opener):
            state = self.fixture.run_worker(run, model=self.model)
        self.assertEqual(state['status'], 'ready_review', state.get('error'))
        self.assertEqual(self.phases, ['artwork-1','generate-1','verify-1'])
        self.assertEqual(self.network.opener.open.call_count, 2)
        self.assertFalse(chat_build.context(self.root,self.folder)['files'])
        self.assertEqual(CreditLedger(self.root).summary()['estimated_spent_usd'], .02)
        # Replaying the handoff and candidate cannot spend or dispatch again.
        with patch('ember_harness.muse_image.build_opener') as network:
            worker = task_run.Worker(self.root,self.folder,run)
            basis, files = task_artwork.prepare(worker,{})
            network.assert_not_called()
        self.assertEqual(len(sprite_project.asset_rows(files)),2)
        self.assertEqual(basis[sprite_project.ASSETS_FILE],files[sprite_project.ASSETS_FILE])
        actions = [e['action'] for e in h._entries() if e['kind']=='decision' and e.get('decision')=='allow' and e['action']['tool']=='agent.propose']
        self.assertEqual([a['args']['model'] for a in actions][1:3], [IMAGE_MODEL,IMAGE_MODEL])
        coder = worker.contract_for('implement')
        denied = h.check(dict(agent=coder['agent'],contract_id=coder['id'],contract_version=1,tool='agent.propose',
            args=actions[1]['args'],paths=actions[1]['paths'],spend=0))
        self.assertEqual(denied['decision'],'deny')
        ref = task_run.promote(self.root,self.folder,run)['request_ref']
        review = chat_build.list_requests(self.folder)[-1]['payload']['body']
        self.assertEqual(len(review['asset_actions']),2)
        self.assertIsNone(project_plan.status(self.root,self.folder)['tasks'][0]['acceptance'])
        with patch('ember_harness.proposal_quality.require_visible_players'):
            self.app.respond(ref,'approve','SYNTHETIC accept each reviewed sheet and game')
        accepted = self.app.plan_control(self.folder.name,'accept',plan_ref=plan['project_plan']['binding']['ref'],task_id='task-1',build_ref=ref)
        self.assertIsNone(accepted['next_task_id'])
        self.assertEqual(project_plan.status(self.root,self.folder)['continuation']['status'],'complete')

    def test_blocked_image_connection_retains_plan_and_never_falls_back_to_shapes(self):
        run = self.fixture.prepare(); self.fixture.approve(run)
        with patch('ember_harness.muse_image.status',return_value=dict(ready=False,reason='SYNTHETIC no image credits')):
            state = self.fixture.run_worker(run,model=self.model)
        self.assertEqual(state['status'],'interrupted')
        self.assertEqual(len(state['attempts']['attempts']),1)
        self.assertIn('no image credits',state['error'])
        self.assertEqual(self.phases,['artwork-1'])
        self.assertFalse(chat_build.context(self.root,self.folder)['files'])
        self.assertFalse(sprite_project.load_draft(self.folder)['plan']['entities'][0]['asset_ref'])

    def test_art_policy_uses_runtime_limit_and_respects_explicit_art_exclusions(self):
        frozen = project_plan.context(self.root,self.folder)
        self.assertIsNotNone(task_artwork.policy(frozen,dict(files=[])))
        for count in (0,1,100):
            frozen['document']['scope']['asset_budget']={'generated':count}
            self.assertEqual(task_artwork.policy(frozen,dict(files=[]))['max_atlases'],sprite_project.MAX_ATLASES)
        frozen['document']['scope']['asset_budget']={'generated':2}
        self.assertIsNone(task_artwork.policy(frozen,dict(files=[dict(path='asset.js',content='prepared')])) )
        for exclusion in ('No generated art','No generated artwork','No generated images','No generated assets','Text-only','Procedural only'):
            frozen['document']['scope']['out_of_scope']=[exclusion]
            self.assertIsNone(task_artwork.policy(frozen,dict(files=[])), exclusion)


if __name__ == '__main__':
    unittest.main()
