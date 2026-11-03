"""Synthetic provider/owner choices; real source evidence, gates and private Git."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_git_task as git_fixture
from test_findings import FIELDS
from ember_harness import chat_build, findings, git_automation, git_task, gameplay, project_handoff, project_plan, task_run
from ember_harness.attempts import Attempts, TaskAttempts
from ember_harness.contract_lock import verify as contract_lock
from ember_harness.core import content_hash, digest
from ember_harness.core import Harness
from ember_harness.recovery import atomic_json, read_json


class GitAutomationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = git_fixture.GitBrowserTaskTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.task = self.fixture.fixture
        self.root, self.folder, self.app = self.fixture.root, self.fixture.folder, self.fixture.app
        self.calls = []

    def prepare(self, finding=None):
        return git_automation.prepare(self.root, self.folder, finding=finding)['id']

    def model(self, root, folder, prompt, request_id, **kwargs):
        self.calls.append(request_id)
        if request_id.startswith('generate'):
            return dict(response=json.dumps(dict(title='SYNTHETIC two-point repair', summary='SYNTHETIC exact repair',
                files=[dict(path=name, content=text) for name, text in self.fixture.candidate.items()])))
        return self.task.model(root, folder, prompt, request_id, **kwargs)

    def code(self, run_id, *, approve=True):
        if approve:
            self.task.approve(run_id)
        with patch('ember_harness.task_run.run_muse', side_effect=self.model), patch(
                'ember_harness.polish_runtime.inspect', side_effect=self.fixture.inspect):
            task_run.Worker(self.root, self.folder, run_id).run()
        return task_run.history(self.root, self.folder)[-1]

    def verify(self, source_id, *, approve=True):
        row = git_automation.advance(self.root, self.folder, source_id)
        if approve:
            git_task.respond(self.root, self.folder, row['id'], 'approve', 'SYNTHETIC exact generated Git permission review')
        return self.fixture.run_worker(row['id'])

    def bug(self):
        initial = chat_build.status(self.root, self.folder)['completed'][-1]['request_ref']
        self.app.record_playtest(report_id='synthetic-git-finding-001', request_ref=initial,
            outcome='problem', note='SYNTHETIC expected two points, observed one', observations=[])
        ref = self.app.finding_control(self.folder.name, 'prepare', report_id='synthetic-git-finding-001',
            fields={**FIELDS, 'expected':'Two points', 'actual':'One point'})['request_ref']
        result = self.app.respond(ref, 'approve', 'SYNTHETIC reviewed canonical finding intake')
        return findings.intake(self.folder).get(result['bug_id'])

    def test_generated_source_hands_off_to_exact_git_review_with_one_attempt_and_separate_apply(self):
        original = chat_build.context(self.root, self.folder)['manifest']
        run = self.prepare()
        with patch('ember_harness.task_run.run_muse') as provider:
            task_run.Worker(self.root, self.folder, run).run()
            self.assertEqual(task_run.history(self.root, self.folder)[-1]['status'], 'interrupted')
            provider.assert_not_called()
        state = self.code(run)
        self.assertEqual(state['status'], 'ready_review', state.get('error'))
        self.assertEqual(state['git_stage'], 'awaiting_approval')
        self.assertEqual(self.calls, ['generate-1', 'verify-1'])
        linked = git_automation.advance(self.root, self.folder, run)
        self.assertEqual(linked, git_automation.advance(self.root, self.folder, run))
        self.assertFalse((git_task.run_folder(self.folder, linked['id'])/'baseline/.git').exists())
        self.assertEqual(len(git_task.requests(self.folder)), 1)
        self.assertEqual(state['attempts']['attempts'][0]['outcome'], 'running')
        self.assertEqual(chat_build.context(self.root, self.folder)['manifest'], original)
        with self.assertRaisesRegex(ValueError, 'clean Git verification'):
            task_run.promote(self.root, self.folder, run)
        with self.assertRaisesRegex(ValueError, 'Approve exact'):
            git_task.Worker(self.root, self.folder, linked['id']).run()
        git = self.verify(run)
        self.assertTrue(git['report']['qualified'], git.get('error'))
        self.assertEqual(len(git['attempts']['attempts']), 1)
        self.assertEqual(git['attempts']['attempts'][0]['run_id'], run)
        self.assertEqual(git['attempts']['attempts'][0]['outcome'], 'qualified')
        self.assertEqual(self.calls, ['generate-1', 'verify-1'])
        ref = git_task.promote(self.root, self.folder, linked['id'])['request_ref']
        self.assertIsNone(chat_build.list_requests(self.folder)[-1]['decision'])
        self.assertEqual(chat_build.context(self.root, self.folder)['manifest'], original)
        self.app.respond(ref, 'approve', 'SYNTHETIC final exact application')
        self.assertEqual(chat_build.context(self.root, self.folder)['manifest'], git['candidate_manifest'])
        self.assertEqual(project_plan.status(self.root, self.folder)['tasks'][0]['state'], 'applied_needs_review')
        self.assertEqual(task_run.history(self.root, self.folder)[-1]['status'], 'promoted')
        handoff = project_handoff.report(self.root, self.folder, ref)
        self.assertEqual(handoff['git_runs'][0]['source_task_run_id'], run)
        self.assertEqual(handoff['task_runs'][0]['git_run_id'], linked['id'])

    def test_non_reproducing_baseline_consumes_one_attempt_without_model_or_git_work(self):
        self.fixture.baseline_fails = False
        run = self.prepare(); state = self.code(run)
        self.assertEqual(state['status'], 'stopped')
        self.assertEqual(self.calls, [])
        self.assertEqual(len(state['attempts']['attempts']), 1)
        self.assertEqual(state['attempts']['attempts'][0]['outcome'], 'stopped')
        self.assertEqual(git_task.requests(self.folder), [])

    def test_existing_pending_git_review_blocks_another_model_worker_before_preparation(self):
        pending = self.fixture.prepare()
        with self.assertRaisesRegex(ValueError, 'existing Git repair'):
            self.prepare()
        self.assertEqual(task_run.requests(self.folder), [])
        self.assertEqual(self.calls, [])
        git_task.respond(self.root, self.folder, pending, 'decline', 'SYNTHETIC discard the prior exact Git review')
        self.assertTrue(self.prepare())

    def test_interrupted_handoff_reuses_source_calls_and_allocation(self):
        run = self.prepare()
        with patch('ember_harness.git_task.prepare', side_effect=ValueError('SYNTHETIC interruption before exact Git packet')):
            self.code(run)
        self.assertEqual(self.calls, ['generate-1', 'verify-1'])
        first = git_automation.advance(self.root, self.folder, run)
        self.assertEqual(first, git_automation.advance(self.root, self.folder, run))
        self.assertEqual(self.calls, ['generate-1', 'verify-1'])
        self.assertEqual(len(task_run.history(self.root, self.folder)[-1]['attempts']['attempts']), 1)

    def test_report_before_source_finish_replays_without_a_model_call_or_free_attempt(self):
        run = self.prepare(); self.task.approve(run)
        original = task_run.Worker.finish
        def interrupted(worker, *args, **kwargs):
            if args[1] == 'ready_review':
                raise ValueError('SYNTHETIC interruption after source report and before finish')
            return original(worker, *args, **kwargs)
        with patch('ember_harness.task_run.Worker.finish', interrupted):
            self.code(run, approve=False)
        self.assertEqual(self.calls, ['generate-1', 'verify-1'])
        self.assertEqual(git_task.requests(self.folder), [])
        state = self.code(run, approve=False)
        self.assertEqual(state['git_stage'], 'awaiting_approval')
        self.assertEqual(self.calls, ['generate-1', 'verify-1'])
        self.assertEqual(len(state['attempts']['attempts']), 1)

    def test_decline_receipt_before_cancellation_requires_explicit_recovery_not_view_side_effects(self):
        run = self.prepare(); self.code(run)
        linked = git_automation.advance(self.root, self.folder, run)
        with patch('ember_harness.git_automation.Ledger.abandon', side_effect=ValueError('SYNTHETIC cancellation receipt gap')):
            with self.assertRaises(ValueError):
                git_task.respond(self.root, self.folder, linked['id'], 'decline', 'SYNTHETIC owner cancels Git handoff')
        h = chat_build.harness(self.folder); before = h._entries()
        row = git_automation.history(self.root, self.folder)[-1]
        self.assertEqual(row['status'], 'cancellation_needed')
        self.assertEqual(h._entries(), before)
        git_automation.advance(self.root, self.folder, run)
        row = git_automation.history(self.root, self.folder)[-1]
        self.assertEqual(row['status'], 'stopped')
        self.assertEqual(task_run.history(self.root, self.folder)[-1]['git_stage'], 'declined')
        self.assertEqual(row['attempts']['attempts'][0]['outcome'], 'stopped')

    def test_discarded_git_permissions_end_the_original_attempt_and_allow_fresh_review(self):
        run = self.prepare(); self.code(run)
        linked = git_automation.advance(self.root, self.folder, run)
        git_task.respond(self.root, self.folder, linked['id'], 'decline', 'SYNTHETIC discard generated Git verification')
        self.assertEqual(task_run.history(self.root, self.folder)[-1]['status'], 'stopped')
        attempts = git_automation.history(self.root, self.folder)[-1]['attempts']['attempts']
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]['outcome'], 'stopped')
        self.assertNotEqual(self.prepare(), run)
        self.assertFalse((git_task.run_folder(self.folder, linked['id'])/'baseline/.git').exists())

    def test_failed_clean_git_result_finishes_same_attempt_as_failed_without_promoting(self):
        run = self.prepare(); self.code(run)
        self.fixture.candidate_passes = False
        row = self.verify(run)
        self.assertFalse(row['report']['qualified'])
        self.assertEqual(len(row['attempts']['attempts']), 1)
        self.assertEqual(row['attempts']['attempts'][0]['outcome'], 'failed')
        with self.assertRaisesRegex(ValueError, 'qualifying'):
            git_task.promote(self.root, self.folder, row['id'])
        self.assertEqual(task_run.history(self.root, self.folder)[-1]['status'], 'awaiting_decision')
        origin = git_task.load(self.folder, row['id'])[3]['origin']
        with self.assertRaisesRegex(ValueError, 'already has its exact Git'):
            git_task.prepare(self.root, self.folder, candidate_files=self.fixture.candidate, origin=origin)

    def test_stale_or_forged_source_handoff_is_refused(self):
        run = self.prepare(); self.code(run)
        request = git_task.requests(self.folder)[-1]
        origin = deepcopy(request['payload']['body']['git_task']['origin'])
        for update in (dict(report_sha256='f'*64), dict(index=2), dict(extra='unreviewed')):
            with self.subTest(update=update), self.assertRaises(ValueError):
                git_automation.source(self.folder, {**origin, **update})
        source = task_run.run_folder(self.folder, run)/'reports/1.json'
        source.write_bytes(b'{}')
        with self.assertRaises(ValueError):
            git_task.respond(self.root, self.folder, request['payload']['body']['git_task']['id'], 'approve', 'SYNTHETIC stale source')

    def test_missing_source_control_and_tampered_report_never_trap_owner_cancellation(self):
        bug = self.bug()
        run = self.prepare(dict(bug_id=bug['id'], bug_hash=bug['record_hash'], scenario=0)); self.code(run)
        work = task_run.run_folder(self.folder, run)
        (work/'reports/1.json').write_bytes(b'{}')
        (work/'run.json').unlink()
        git = git_task.history(self.root, self.folder)[-1]
        self.assertEqual(git['status'], 'inspection_required')
        self.app.task_control(self.folder.name, 'stop', run_id=run)
        state = Attempts(chat_build.harness(self.folder)).status(bug['id'])
        self.assertEqual(len(state['attempts']), 1)
        self.assertNotEqual(state['status'], 'in_progress')
        self.assertEqual(task_run.history(self.root, self.folder)[-1]['status'], 'stopped')
        self.assertNotEqual(self.prepare(dict(bug_id=bug['id'], bug_hash=bug['record_hash'], scenario=0)), run)

    def test_declined_exact_finding_application_can_end_same_attempt_and_prepare_again(self):
        bug = self.bug()
        run = self.prepare(dict(bug_id=bug['id'], bug_hash=bug['record_hash'], scenario=0)); self.code(run)
        git = self.verify(run)
        ref = git_task.promote(self.root, self.folder, git['id'])['request_ref']
        self.app.respond(ref, 'decline', 'SYNTHETIC discard exact candidate after independent Git proof')
        source = task_run.history(self.root, self.folder)[-1]
        self.assertEqual(source['status'], 'ready_review')
        self.assertEqual(source['git_stage'], 'application_declined')
        self.app.task_control(self.folder.name, 'stop', run_id=run)
        state = Attempts(chat_build.harness(self.folder)).status(bug['id'])
        self.assertEqual(len(state['attempts']), 1)
        self.assertNotEqual(state['status'], 'in_progress')
        self.assertNotEqual(findings.intake(self.folder).get(bug['id'])['state'], 'closed')
        self.assertNotEqual(self.prepare(dict(bug_id=bug['id'], bug_hash=bug['record_hash'], scenario=0)), run)

    def test_partial_source_finding_approval_can_be_discarded_after_scope_renewal(self):
        bug = self.bug()
        run = self.prepare(dict(bug_id=bug['id'], bug_hash=bug['record_hash'], scenario=0))
        work, h, packet, plan = task_run.load(self.folder, run)
        item = packet['body']['contracts'][0]; coder = item['contract']
        h.approve(coder['id'], coder['version'], approver='johnathan', quote='SYNTHETIC partial first child receipt',
            expected_hash=content_hash(coder), parent_id=item['parent_id'])
        self.assertEqual(Attempts(h).status(bug['id'])['status'], 'in_progress')
        saved = project_plan.status(self.root, self.folder)
        renewal = project_plan.prepare(self.root, self.folder, saved['approved']['document'], saved['latest_ref'])['request_ref']
        project_plan.acknowledge(self.root, self.folder, renewal, 'SYNTHETIC scope renewal')
        self.app.respond(renewal, 'approve', 'SYNTHETIC renewed project scope')
        self.assertEqual(task_run.history(self.root, self.folder)[-1]['status'], 'scope_inactive')
        self.app.task_control(self.folder.name, 'decide', run_id=run, choice='decline')
        self.assertEqual(len(Attempts(h).status(bug['id'])['attempts']), 1)
        self.assertNotEqual(Attempts(h).status(bug['id'])['status'], 'in_progress')
        self.assertNotEqual(self.prepare(dict(bug_id=bug['id'], bug_hash=bug['record_hash'], scenario=0)), run)
        self.assertEqual(self.calls, [])

    def test_partial_source_decline_receipt_recovery_is_explicit_and_never_reapproves(self):
        bug = self.bug()
        run = self.prepare(dict(bug_id=bug['id'], bug_hash=bug['record_hash'], scenario=0))
        work, h, packet, plan = task_run.load(self.folder, run)
        item = packet['body']['contracts'][0]; coder = item['contract']
        h.approve(coder['id'], coder['version'], approver='johnathan', quote='SYNTHETIC partial coding receipt',
            expected_hash=content_hash(coder), parent_id=item['parent_id'])
        with patch('ember_harness.findings.FixAttempts.abandon', side_effect=ValueError('SYNTHETIC decline-before-cancellation interruption')):
            with self.assertRaises(ValueError):
                self.app.task_control(self.folder.name, 'decide', run_id=run, choice='decline')
        entries = h._entries()
        self.assertEqual(git_automation.history(self.root, self.folder)[-1]['status'], 'cancellation_needed')
        self.assertEqual(h._entries(), entries)
        git_automation.advance(self.root, self.folder, run)
        self.assertNotEqual(Attempts(h).status(bug['id'])['status'], 'in_progress')
        self.assertEqual(len(Attempts(h).status(bug['id'])['attempts']), 1)
        self.assertEqual(len([e for e in h._entries() if e['kind'] == 'owner_decision' and e['request_ref'] == digest(packet)]), 1)

    def test_canonical_finding_gets_clean_git_witness_and_explicit_owner_closure(self):
        bug = self.bug()
        run = self.prepare(dict(bug_id=bug['id'], bug_hash=bug['record_hash'], scenario=0))
        self.code(run)
        source_plan = task_run.load(self.folder, run)[3]
        self.assertEqual(TaskAttempts(chat_build.harness(self.folder), source_plan['task_identity']).status()['attempts'], [])
        git = self.verify(run)
        original_append = Harness._append
        def interrupted_promotion(h, kind, **fields):
            if kind == 'task_run_promoted':
                raise ValueError('SYNTHETIC exact review published before promotion receipt')
            return original_append(h, kind, **fields)
        with patch.object(Harness, '_append', interrupted_promotion), self.assertRaisesRegex(ValueError, 'promotion receipt'):
            git_task.promote(self.root, self.folder, git['id'])
        ref = chat_build.list_requests(self.folder)[-1]['ref']
        with self.assertRaisesRegex(ValueError, 'apply|Applied|approved|completed'):
            findings.prepare_close(self.root, self.folder, run)
        self.app.respond(ref, 'approve', 'SYNTHETIC exact Git finding repair')
        self.assertEqual(git_task.promote(self.root, self.folder, git['id'])['request_ref'], ref)
        self.assertNotEqual(findings.intake(self.folder).get(bug['id'])['state'], 'closed')
        pending = findings.prepare_close(self.root, self.folder, run)['request_ref']
        with self.assertRaisesRegex(ValueError, 'owner closure'):
            findings.close(self.root, self.folder, run)
        result = self.app.respond(pending, 'approve', 'SYNTHETIC owner reviewed C3 closure')
        self.assertEqual(result['status'], 'closed')
        h = chat_build.harness(self.folder)
        closed = next(e for e in reversed(h._entries()) if e.get('status') == 'closed' and e.get('bug_id') == bug['id'])
        self.assertEqual(closed['git_verification']['head'], git['report']['head'])
        self.assertEqual(len(Attempts(h).status(bug['id'])['attempts']), 1)
        self.assertEqual(findings.validate_history(h, h._entries()), 1)
        self.assertTrue(contract_lock(h.root)['ok'])
        handoff = project_handoff.report(self.root, self.folder, ref)
        self.assertEqual(handoff['findings'][0]['state'], 'closed')
        self.assertEqual(handoff['git_runs'][0]['finding_id'], bug['id'])
        missing_receipt = deepcopy(findings.requests(self.folder))
        for row in missing_receipt:
            if row['payload']['body'].get('finding_closure', {}).get('run_id') == run:
                row['decision'] = None
        with patch('ember_harness.findings.requests', return_value=missing_receipt), self.assertRaisesRegex(ValueError, 'explicit owner'):
            findings.validate_history(h, h._entries())
        work = git_task.run_folder(self.folder, git['id'])
        record = work/'report.json'; report_bytes = record.read_bytes(); record.write_bytes(report_bytes+b' ')
        with self.assertRaises(ValueError): findings.validate_history(h, h._entries())
        with self.assertRaises(ValueError): project_handoff.report(self.root, self.folder, ref)
        record.write_bytes(report_bytes)
        git_fixture.git(work/'candidate', 'update-ref', 'HEAD', git['report']['base'])
        with self.assertRaises(ValueError): findings.validate_history(h, h._entries())
        git_fixture.git(work/'candidate', 'update-ref', 'HEAD', git['report']['head'])
        capture = git_task.run_folder(self.folder, git['id'])/'captures/1/output/desktop.png'
        original = capture.read_bytes(); capture.write_bytes(b'SYNTHETIC changed closed-finding Git capture')
        with self.assertRaises(ValueError):
            findings.validate_history(h, h._entries())
        self.assertFalse(contract_lock(h.root)['ok'])
        capture.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
