"""Replay the exact reviewed before/after request after a verifier interruption."""
from copy import deepcopy
from hashlib import sha256
import json
import unittest

import test_task_run as tasks
from ember_harness import chat_build, project_plan, task_run
from ember_harness.recovery import read_json


class TaskComparisonRecoveryTests(unittest.TestCase):
    def test_interrupted_verifier_reuses_completed_baseline_and_identical_request(self):
        fixture = tasks.TaskRunTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        run = fixture.prepare()
        fixture.approve(run)
        work = task_run.run_folder(fixture.folder, run)
        browser_calls, provider_calls = [], []
        interrupted = False

        def browser(runtime, source, output, **kwargs):
            browser_calls.append((source.parent.name, deepcopy(read_json(source))))
            return fixture.fixture.browser(runtime, source, output, **kwargs)

        def provider(root, folder, prompt, phase, **kwargs):
            nonlocal interrupted
            provider_calls.append(dict(phase=phase, prompt=prompt,
                images=[dict(path=str(path), sha256=sha256(path.read_bytes()).hexdigest())
                        for path in kwargs.get('images', [])],
                schema=deepcopy(kwargs['output_schema'])))
            if phase == 'verify-1' and not interrupted:
                interrupted = True
                raise ValueError('SYNTHETIC interruption after preparing the verifier comparison')
            return fixture.model(root, folder, prompt, phase, **kwargs)

        first = fixture.run_worker(run, model=provider, browser=browser)
        self.assertEqual(first['status'], 'interrupted', first.get('error'))
        self.assertEqual([index for index, _ in browser_calls], ['0', '1'])
        self.assertEqual([row['phase'] for row in provider_calls], ['generate-1', 'verify-1'])
        baseline_input = (work / 'captures/0/input.json').read_bytes()
        baseline_result = (work / 'captures/0/output/report.json').read_bytes()
        frozen_request = (work / 'calls/verify-1/input.json').read_bytes()
        original = deepcopy(first['baseline_observations'])
        self.assertEqual(len(first['attempts']['attempts']), 1)

        recovered = fixture.run_worker(run, model=provider, browser=browser)
        self.assertEqual(recovered['status'], 'ready_review', recovered.get('error'))
        self.assertEqual([index for index, _ in browser_calls], ['0', '1'],
                         'Completed before and after captures must replay from their bound checkpoints')
        self.assertEqual([row['phase'] for row in provider_calls], ['generate-1', 'verify-1', 'verify-1'])
        self.assertEqual(provider_calls[1], provider_calls[2])
        payload = json.loads(provider_calls[2]['prompt'].split('\n', 1)[1])
        self.assertEqual(payload['baseline_observations'], original)
        self.assertEqual(recovered['reports'][0]['comparison']['baseline_observations'], original)
        self.assertEqual((work / 'captures/0/input.json').read_bytes(), baseline_input)
        self.assertEqual((work / 'captures/0/output/report.json').read_bytes(), baseline_result)
        self.assertEqual((work / 'calls/verify-1/input.json').read_bytes(), frozen_request)
        self.assertEqual(len(recovered['attempts']['attempts']), 1)
        self.assertEqual(chat_build.context(fixture.root, fixture.folder)['manifest'],
                         task_run.load(fixture.folder, run)[3]['base_manifest'])
        self.assertIsNone(project_plan.status(fixture.root, fixture.folder)['tasks'][0]['acceptance'])


if __name__ == '__main__':
    unittest.main()
