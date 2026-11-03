"""Specialist dispatch through real gates, checkpoints and synthetic providers."""
from copy import deepcopy
import json
import unittest

import test_task_run as tasks
from quality_fixture import assessments, comparison
from ember_harness import chat_build, orchestration, project_plan, task_run
from ember_harness.core import subset


class RoutingTests(unittest.TestCase):
    def test_routes_and_worker_cap(self):
        for goal, agents in [
            ('One scene', ['ember-task-coder']),
            ('Improve movement', ['ember-gameplay-coder']),
            ('Responsive HUD', ['ember-interface-coder']),
            ('Particle trails', ['ember-effects-coder']),
            ('Movement and HUD', ['ember-gameplay-coder', 'ember-interface-coder']),
            ('Movement, HUD and particles', ['ember-gameplay-coder', 'ember-presentation-coder']),
        ]:
            with self.subTest(goal=goal):
                route = orchestration.plan(goal)
                self.assertEqual([s['agent'] for s in route['stages'][:-1]], agents)
                self.assertEqual(route['stages'][-1]['role'], 'verifier')
                self.assertEqual(route['stages'][-1]['depends_on'], [route['stages'][-2]['id']])
        self.assertEqual(orchestration.plan('Fix HUD and movement', kind='finding')['stages'][0]['agent'], 'ember-fix-coder')
        self.assertEqual([s['id'] for s in orchestration.plan('Chest', kind='asset')['stages']], ['concept', 'production', 'verify'])

    def test_native_profile_requires_unambiguous_production_intent(self):
        self.assertEqual(orchestration.asset_profile('Create original chest prop'), 'chest')
        self.assertEqual(orchestration.asset_profile('Model courier waygate'), 'gate')
        for goal in ('Put an existing chest in the scene', 'Create chest inventory UI', 'Create chest and gate', 'Gate score'):
            self.assertIsNone(orchestration.asset_profile(goal))


class DelegationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = tasks.TaskRunTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.folder = self.fixture.root, self.fixture.folder
        saved = project_plan.status(self.root, self.folder)
        document = deepcopy(saved['approved']['document'])
        document['scope']['features'][0] = 'Improve movement and responsive HUD'
        ref = project_plan.prepare(self.root, self.folder, document, saved['latest_ref'])['request_ref']
        project_plan.acknowledge(self.root, self.folder, ref, 'SYNTHETIC reviewed task amendment')
        self.fixture.app.respond(ref, 'approve', 'SYNTHETIC compound task scope')
        self.design = deepcopy(document)
        self.phases = []

    def model(self, root, folder, prompt, phase, **kwargs):
        data = json.loads(prompt.split('\n', 1)[1])
        self.assertEqual(data['approved_design'], self.design)
        self.assertIn('brief', data)
        self.phases.append(phase)
        if phase.startswith('generate'):
            self.assertEqual(data['assignment']['agent'], 'ember-gameplay-coder')
            result = dict(title='Movement', summary='PRIVATE CODER NARRATIVE', edits=[
                dict(path='app.js', before=' + 1;', after=' + 2;')])
        elif phase.startswith('specialize'):
            self.assertEqual(data['assignment']['agent'], 'ember-interface-coder')
            self.assertIn(' + 2;', data['files']['app.js'])
            result = dict(title='Responsive HUD', summary='PRIVATE SECOND NARRATIVE', edits=[
                dict(path='style.css', before='rgb(20, 30, 40)', after='rgb(30, 40, 50)')])
        else:
            self.assertIn(' + 2;', data['files']['app.js'])
            self.assertIn('rgb(30, 40, 50)', data['files']['style.css'])
            self.assertNotIn('PRIVATE', prompt)
            result = dict(meets_task=True, preserves_scope=True, summary='SYNTHETIC final verification', issues=[])
            result['criteria'] = assessments(data)
            if data.get('comparison'):
                result['comparison'] = comparison(data)
        return dict(response=json.dumps(result))

    def test_automatic_handoff_final_verification_and_exact_promotion(self):
        run = self.fixture.prepare()
        work, h, packet, plan = task_run.load(self.folder, run)
        self.assertEqual(plan['rounds'], 2)
        self.assertEqual(plan['credits'], 30)
        self.assertEqual(len(packet['body']['contracts']), 3)
        parent = project_plan.check_binding(self.root, self.folder, plan['project_plan']['binding'])
        self.assertTrue(all(subset(c['contract'], parent) for c in packet['body']['contracts']))
        self.fixture.approve(run)
        state = self.fixture.run_worker(run, model=self.model)
        self.assertEqual(state['status'], 'ready_review', state.get('error'))
        self.assertEqual(self.phases, ['generate-1', 'specialize-1', 'verify-1'])
        self.assertEqual(state['delegation'], plan['delegation'])
        self.assertIn(' + 2;', task_run.candidate_files(work, 1)['app.js'])
        actions = [e['action'] for e in h._entries() if e['kind'] == 'decision' and e.get('decision') == 'allow'
                   and e['action']['tool'] == 'agent.propose']
        self.assertEqual([a['agent'] for a in actions], ['ember-gameplay-coder', 'ember-interface-coder', 'ember-task-verifier'])
        ref = task_run.promote(self.root, self.folder, run)['request_ref']
        self.fixture.app.respond(ref, 'approve', 'SYNTHETIC exact combined candidate')
        self.assertIn('rgb(30, 40, 50)', (chat_build.project(self.root, self.folder) / 'style.css').read_text())
        self.assertTrue(h.audit_verify()['ok'])

    def test_recovery_replays_completed_specialist_without_another_call(self):
        run = self.fixture.prepare(); self.fixture.approve(run)
        def interrupted(*args, **kwargs):
            if args[3] == 'verify-1':
                raise ValueError('SYNTHETIC verifier interruption')
            return self.model(*args, **kwargs)
        first = self.fixture.run_worker(run, model=interrupted)
        self.assertEqual(first['status'], 'interrupted')
        result = self.fixture.run_worker(run, model=self.model)
        self.assertEqual(result['status'], 'ready_review', result.get('error'))
        self.assertEqual(self.phases, ['generate-1', 'specialize-1', 'verify-1'])
        self.assertEqual(len(result['attempts']['attempts']), 1)

    def test_agent_cannot_take_another_stage_or_write_its_outputs(self):
        run = self.fixture.prepare(); self.fixture.approve(run)
        worker = task_run.Worker(self.root, self.folder, run)
        with self.assertRaisesRegex(ValueError, 'not assigned'):
            worker.model('specialize-1', 'wrong stage', {}, {}, [])
        action = dict(agent=worker.contract['agent'], contract_id=worker.contract['id'], contract_version=1,
            tool='fs.write', args=dict(path=(worker.work/'specialist-candidates/1/app.js').as_posix(), content='bad'),
            paths=dict(read=[], write=[(worker.work/'specialist-candidates/1/app.js').as_posix()]), spend=0)
        self.assertEqual(worker.h.check(action)['decision'], 'deny')
        route = deepcopy(worker.plan['delegation'])
        route['stages'][-1]['agent'] = route['stages'][0]['agent']
        with self.assertRaisesRegex(ValueError, 'Invalid specialist'):
            orchestration.validate(route, worker.packet['body']['contracts'])

    def test_changed_handoff_blocks_promotion(self):
        run = self.fixture.prepare(); self.fixture.approve(run)
        state = self.fixture.run_worker(run, model=self.model)
        self.assertEqual(state['status'], 'ready_review', state.get('error'))
        work = task_run.run_folder(self.folder, run)
        (work/'candidates/1/app.js').write_text('tampered', encoding='utf-8')
        with self.assertRaises(ValueError):
            task_run.promote(self.root, self.folder, run)
