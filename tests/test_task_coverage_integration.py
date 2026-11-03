"""Real task gates with synthetic models/browser observations; no live requests."""
from copy import deepcopy
import json
import unittest

import test_task_run as tasks
from ember_harness import gameplay, project_plan, task_run
from ember_harness.recovery import atomic_json


class CoverageTaskIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = tasks.TaskRunTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.folder = self.fixture.root, self.fixture.folder

    def test_reset_repeat_and_touch_failures_block_positive_task_reviews(self):
        plan = dict(title='Full interaction loop', scenarios=[
            dict(name='First success', viewport='desktop', coverage=['success'], steps=[
                dict(action='press', key='Enter'), dict(action='visible', selector='#counter')]),
            dict(name='Restart', viewport='desktop', coverage=['reset'], steps=[
                dict(action='click', selector='button'), dict(action='visible', selector='#counter')]),
            dict(name='Play again', viewport='desktop', coverage=['repeated_play'], steps=[
                dict(action='press', key='r'), dict(action='press', key='Enter'),
                dict(action='number_at_least', selector='#counter', value=1)]),
            dict(name='Touch success', viewport='mobile', coverage=['success'], steps=[
                dict(action='tap', selector='button'), dict(action='number_at_least', selector='#counter', value=1)])])
        checks = gameplay.save(self.folder, plan, 1)
        before = deepcopy(plan)
        run_id = self.fixture.prepare()
        frozen = task_run.load(self.folder, run_id)[3]
        coverage = frozen['coverage_review']
        self.assertEqual(coverage['plan_sha256'], checks['sha256'])
        self.assertIn('failure', coverage['missing'])
        self.assertEqual(self.fixture.calls, [])
        self.fixture.approve(run_id)

        def browser(runtime, source, output, **kwargs):
            report = self.fixture.fixture.browser(runtime, source, output, **kwargs)
            index = int(source.parent.name)
            if index:
                result = report['gameplay']
                # Happy path remains green in all rounds; a different secondary
                # interaction fails each time despite enthusiastic AI reviews.
                row = result['scenarios'][index]
                row['steps'][-1].update(status='failed', observed='SYNTHETIC secondary path regression')
                row['outcome'] = 'failed'
                result['outcome'] = 'failed'
                atomic_json(output / 'report.json', report)
            return report

        def model(root, folder, prompt, phase, **kwargs):
            data = json.loads(prompt.split('\n', 1)[1])
            self.assertEqual(data['coverage_review'], coverage)
            return self.fixture.model(root, folder, prompt, phase, **kwargs)

        state = self.fixture.run_worker(run_id, model=model, browser=browser)
        self.assertEqual(state['status'], 'awaiting_decision', state.get('error'))
        self.assertEqual([r['qualified'] for r in state['reports']], [False, False, False])
        for index, report in enumerate(state['reports'], 1):
            self.assertTrue(report['verdict']['meets_task'])
            self.assertTrue(report['verdict']['comparison']['improved'])
            scenarios = report['observations']['gameplay']['scenarios']
            self.assertEqual(scenarios[0]['outcome'], 'passed')
            self.assertEqual(scenarios[index]['outcome'], 'failed')
            self.assertTrue(report['quality']['blockers'])
        self.assertIsNone(project_plan.status(self.root, self.folder)['tasks'][0]['acceptance'])
        self.assertEqual(gameplay.load(self.folder)['plan'], before)
        self.assertEqual(task_run.load(self.folder, run_id)[3]['coverage_review'], coverage)
        with self.assertRaisesRegex(ValueError, 'qualified'):
            task_run.promote(self.root, self.folder, run_id)

    def test_coverage_edit_stops_a_prepared_run_before_any_model_call(self):
        run_id = self.fixture.prepare()
        before = task_run.load(self.folder, run_id)[3]['coverage_review']
        checks = gameplay.load(self.folder)
        changed = deepcopy(checks['plan'])
        changed['scenarios'][0]['coverage'] = ['success']
        gameplay.save(self.folder, changed, checks['revision'])
        with self.assertRaisesRegex(ValueError, 'plan changed'):
            self.fixture.approve(run_id)
        self.assertEqual(self.fixture.calls, [])
        self.assertEqual(task_run.load(self.folder, run_id)[3]['coverage_review'], before)


if __name__ == '__main__':
    unittest.main()
