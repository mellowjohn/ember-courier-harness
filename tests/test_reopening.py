"""Lifecycle unit fixtures plus a real two-cycle closure integration demo."""
from copy import deepcopy
from pathlib import Path
import contextlib
import io
import json
import tempfile
import unittest
from unittest.mock import patch

from ember_harness import canonical, content_hash, draft
from ember_harness.attempts import Attempts, status
from ember_harness.contract_lock import verify
from ember_harness.intake import Intake
from ember_harness.reopening import validate_history
from ember_harness.reconciliation import Reconciliation
from examples.intake_demo import ingest
from examples.reconciliation_demo import setup, fix, propose


class ReopeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.ctx = setup(Path(self.temp.name).resolve())
        self.h, self.intake = self.ctx['h'], self.ctx['intake']
        self.bug = ingest(self.ctx, 'initial')

    def close_fixture(self, number=1):
        # Unit-only terminal fixture; real proof/closure is exercised in the integration demo.
        c = fix(self.ctx, self.bug['id'], number)
        with self.h._lock():
            event = self.h._append('state_transition', bug_id=self.bug['id'], severity=self.bug['severity'], status='closed',
                                   fix_contract_id=c['id'], author=c['agent'], build='unit-terminal-fixture')
        self.closed = self.intake.get(self.bug['id'])
        self.state = Attempts(self.h).status(self.bug['id'])
        return c, event

    def reopen(self, **overrides):
        args = dict(contract_id=self.ctx['reviewer']['id'], expected_hash=self.closed['record_hash'],
                    expected_state_hash=self.state['state_hash'], reason='Fixture QA reports recurrence on a later build')
        args.update(overrides)
        return self.intake.reopen(self.bug['id'], **args)

    def retriage(self, finding=None):
        return ingest(self.ctx, 'recurrence', finding, bug_id=self.bug['id'], expected_hash=self.intake.get(self.bug['id'])['record_hash'])

    def test_reopen_preserves_closure_success_snapshot_and_count(self):
        c, closure = self.close_fixture()
        frozen = Path(c['inputs'][0]['path']).read_bytes()
        result = self.reopen()
        bug, state = result['bugs'][0], result['attempts']
        self.assertEqual((bug['state'], bug['owner'], bug['reopen_count']), ('reopened', 'QA', 1))
        self.assertEqual(bug['last_closure_seq'], closure['seq'])
        self.assertEqual((state['attempts_started'], state['next_attempt']), (1, 2))
        self.assertEqual(state['attempts'][0]['status'], 'succeeded')
        self.assertEqual(Path(c['inputs'][0]['path']).read_bytes(), frozen)
        self.assertEqual(self.h._entries()[closure['seq'] - 1], closure)
        self.assertTrue(verify(self.h.root)['ok'])

    def test_only_current_closed_bug_and_nonblank_reason(self):
        with self.assertRaisesRegex(ValueError, 'closed'):
            self.intake.reopen(self.bug['id'], contract_id=self.ctx['reviewer']['id'], expected_hash=self.bug['record_hash'], expected_state_hash=Attempts(self.h).status(self.bug['id'])['state_hash'], reason='Not closed')
        self.close_fixture()
        with self.assertRaisesRegex(ValueError, 'reason'):
            self.reopen(reason=' ')
        self.reopen()
        with self.assertRaisesRegex(ValueError, 'closed'):
            self.reopen()

    def test_stale_hashes_rejected_without_transition(self):
        self.close_fixture()
        for field in ('expected_hash', 'expected_state_hash'):
            with self.assertRaisesRegex(ValueError, 'stale'):
                self.reopen(**{field: '0' * 64})
            self.assertEqual(self.intake.get(self.bug['id'])['state'], 'closed')

    def test_intake_author_cannot_use_QA_reopen(self):
        self.close_fixture()
        with self.assertRaisesRegex(ValueError, 'QA reviewer'):
            self.reopen(contract_id=self.ctx['contract']['id'])

    def test_fix_author_cannot_be_reopening_reviewer(self):
        c, _ = self.close_fixture()
        qa = deepcopy(self.ctx['reviewer'])
        qa.update(id='ct-reopening-self-review-0001', agent=c['agent'])
        self.h.save_draft(qa)
        self.h.approve(qa['id'], 1, approver='johnathan', quote='Fixture QA contract', expected_hash=content_hash(qa), parent_id=self.ctx['scope']['id'])
        with self.assertRaisesRegex(ValueError, 'fix author'):
            self.reopen(contract_id=qa['id'])

    def test_missing_permission_and_revoked_QA_denied(self):
        self.close_fixture()
        qa = deepcopy(self.ctx['reviewer'])
        qa.update(id='ct-reopening-unlisted-0001')
        qa['allowed_actions'] = [a for a in qa['allowed_actions'] if a['action_id'] != 'reopen']
        self.h.save_draft(qa)
        self.h.approve(qa['id'], 1, approver='johnathan', quote='Fixture no-reopen QA contract', expected_hash=content_hash(qa), parent_id=self.ctx['scope']['id'])
        with self.assertRaisesRegex(ValueError, 'denied'):
            self.reopen(contract_id=qa['id'])
        self.h.revoke(self.ctx['reviewer']['id'], approver='johnathan', reason='End QA authority')
        with self.assertRaisesRegex(ValueError, 'active approved'):
            self.reopen()

    def test_reopened_requires_fresh_triage_then_new_snapshot(self):
        self.close_fixture()
        self.reopen()
        with self.assertRaisesRegex(ValueError, 'not ready'):
            self.intake.snapshot(self.bug['id'], 'ct-fix-too-early-0001')
        bug = self.retriage()
        self.assertEqual(bug['state'], 'triaged')
        self.assertEqual(bug['reopen_count'], 1)
        c = fix(self.ctx, self.bug['id'], 2)
        self.assertEqual(Attempts(self.h).status(self.bug['id'])['attempts_started'], 2)
        self.assertTrue(verify(self.h.root)['ok'])

    def test_pre_reopening_snapshot_cannot_start_new_contract(self):
        old, _ = self.close_fixture()
        self.reopen()
        self.retriage()
        old.update(id='ct-fix-stale-snapshot-0002')
        self.h.save_draft(old)
        with self.assertRaisesRegex(ValueError, 'fresh current snapshot'):
            self.h.approve(old['id'], 1, approver='johnathan', quote='Fixture stale snapshot approval attempt', expected_hash=content_hash(old), parent_id=self.ctx['fix_scope']['id'])

    def test_finished_fix_stays_blocked_after_reopening(self):
        c, _ = self.close_fixture()
        self.reopen()
        action = dict(agent=c['agent'], contract_id=c['id'], tool='test.run', args={'script': self.ctx['script'].as_posix()}, paths={'read': [self.ctx['script'].as_posix()], 'write': []}, spend=0)
        self.assertEqual(self.h.check(action)['reason'], 'attempt_succeeded')

    def test_cap_not_reset_and_retry_remains_separate(self):
        for n in (1, 2):
            c = fix(self.ctx, self.bug['id'], n)
            self.h.revoke(c['id'], approver='johnathan', reason='Fixture ends allocated attempt')
        self.close_fixture(3)
        st = self.reopen()['attempts']
        self.assertEqual(st['status'], 'awaiting_decision')
        self.assertEqual(st['attempts_started'], 3)
        self.retriage()
        with self.assertRaisesRegex(ValueError, 'attempt_limit'):
            fix(self.ctx, self.bug['id'], 4)
        Attempts(self.h).decide(self.bug['id'], choice='retry', expected_state_hash=st['state_hash'], approver='johnathan', quote='Separate fixture owner retry decision')
        c = fix(self.ctx, self.bug['id'], 4)
        self.h.revoke(c['id'], approver='johnathan', reason='Fixture ends extra attempt')
        with self.assertRaisesRegex(ValueError, 'attempt_limit'):
            fix(self.ctx, self.bug['id'], 5)
        self.assertTrue(verify(self.h.root)['ok'])

    def test_second_closure_can_reopen_again_and_old_hash_is_stale(self):
        _, first = self.close_fixture()
        self.reopen()
        self.retriage()
        _, second = self.close_fixture(2)
        result = self.reopen()
        self.assertEqual(result['bugs'][0]['reopen_count'], 2)
        self.assertEqual(result['bugs'][0]['last_closure_seq'], second['seq'])
        self.assertEqual(result['attempts']['attempts_started'], 2)
        self.assertNotEqual(first['seq'], second['seq'])
        self.assertTrue(verify(self.h.root)['ok'])

    def test_incomplete_recurrence_stays_in_QA(self):
        self.close_fixture()
        self.reopen()
        finding = deepcopy(self.ctx['finding'])
        finding.pop('steps')
        bug = self.retriage(finding)
        self.assertEqual(bug['state'], 'needs_repro')
        with self.assertRaisesRegex(ValueError, 'not ready'):
            self.intake.snapshot(bug['id'], 'ct-fix-incomplete-0002')

    def test_retriage_retains_engine_and_severity_gates(self):
        self.close_fixture()
        self.reopen()
        bug = self.retriage({**self.ctx['finding'], 'area': 'engine', 'impact': 'crash'})
        self.assertTrue(bug['severity_review_required'])
        self.assertFalse(bug['route']['code_fix_allowed'])
        with self.assertRaisesRegex(ValueError, 'not ready'):
            self.intake.snapshot(bug['id'], 'ct-fix-engine-0002')

    def test_cannot_skip_retriage_through_severity_or_merge(self):
        other = ingest(self.ctx, 'other')
        self.close_fixture()
        self.reopen()
        bug = self.intake.get(self.bug['id'])
        with self.assertRaisesRegex(ValueError, 'current open'):
            self.intake.review_severity(bug['id'], contract_id=self.ctx['reviewer']['id'], expected_hash=bug['record_hash'], severity='S2', demo_impact=False, note='Fixture QA severity')
        with self.assertRaises(ValueError):
            propose(self.ctx, bug, other)

    def test_reopened_successful_history_can_be_reconciled(self):
        other = ingest(self.ctx, 'other')
        self.close_fixture()
        self.reopen()
        bug = self.retriage()
        plan = propose(self.ctx, bug, other)
        result = Reconciliation(self.intake).approve(plan['plan_hash'], approver='johnathan', quote='Fixture owner merge')
        self.assertEqual(result['attempts']['attempts_started'], 1)
        self.assertEqual(result['attempts']['status'], 'ready')
        self.assertEqual(result['attempts']['attempts'][0]['status'], 'succeeded')
        self.assertTrue(verify(self.h.root)['ok'])

    def test_audit_failure_accepts_neither_half(self):
        self.close_fixture()
        append = self.h._append
        def failing(kind, **fields):
            if fields.get('operation') == 'reopen':
                raise OSError('Fixture audit failure')
            return append(kind, **fields)
        with patch.object(self.h, '_append', side_effect=failing):
            with self.assertRaises(OSError):
                self.reopen()
        self.assertEqual(self.intake.get(self.bug['id'])['state'], 'closed')
        self.assertEqual(Attempts(self.h).status(self.bug['id'])['status'], 'closed')

    def test_cache_failure_keeps_audit_truth(self):
        self.close_fixture()
        write = Path.write_bytes
        def failing(path, raw):
            if path.parent == self.intake.root / 'bugs':
                raise OSError('Fixture cache failure')
            return write(path, raw)
        with patch.object(Path, 'write_bytes', new=failing):
            result = self.reopen()
        self.assertEqual(len(result['cache_warnings']), 1)
        self.assertEqual(self.intake.get(self.bug['id'])['state'], 'reopened')
        self.assertEqual(Attempts(self.h).status(self.bug['id'])['status'], 'ready')

    def test_history_validator_rejects_forged_record_and_closure_link(self):
        self.close_fixture()
        self.reopen()
        for field, value in [('closure_seq', 1), ('reason', 'Different reason')]:
            entries = deepcopy(self.h._entries())
            entries[-1][field] = value
            with self.assertRaises(ValueError):
                validate_history(self.h, entries)
        entries = deepcopy(self.h._entries())
        entries[-1]['records'][0]['reopen_count'] = 0
        with self.assertRaises(ValueError):
            validate_history(self.h, entries)

    def test_cli_and_reports_include_reopen_provenance(self):
        from ember_harness.__main__ import main
        from ember_harness.reporting import write_attempt_report, write_intake_report
        self.close_fixture()
        with contextlib.redirect_stdout(io.StringIO()):
            rc = main(['--store', str(self.h.root), 'bug-reopen', self.bug['id'], '--root', str(self.intake.root), '--contract', self.ctx['reviewer']['id'], '--expected-hash', self.closed['record_hash'], '--state-hash', self.state['state_hash'], '--reason', 'Fixture QA recurrence'])
        self.assertEqual(rc, 0)
        report = Path(write_attempt_report(self.h, self.bug['id'])['path']).read_text()
        self.assertIn('Reopening history', report)
        self.assertIn('Fixture QA recurrence', report)
        queue = Path(write_intake_report(self.h, self.intake.root)['path']).read_text()
        self.assertIn('awaiting_fresh_triage', queue)

    def test_S1_close_still_requires_owner_under_approve_all(self):
        self.close_fixture()
        self.reopen()
        c = draft('ct-reopened-critical-verifier-0001', 'qa-critical', 'Fixture critical closure gate', role='verifier')
        c['approval_mode'] = 'approve_all'
        c['limits']['time_window'] = deepcopy(self.ctx['scope']['limits']['time_window'])
        c['allowed_actions'] = [dict(action_id='close', tool='triage.close', **{'class': 'bug_close'}, args_constraints={'bug_id': {'equals': self.bug['id']}, 'severity': {'equals': 'S1'}}, allow_no_evidence=True)]
        parent = deepcopy(c)
        parent.update(id='ct-reopened-critical-scope-0001', agent='planner-critical')
        parent['extensions']['orchestration']['role'] = 'scope'
        self.h.save_draft(parent)
        self.h.approve(parent['id'], 1, approver='johnathan', quote='Fixture critical scope approval', expected_hash=content_hash(parent))
        self.h.save_draft(c)
        self.h.approve(c['id'], 1, approver='johnathan', quote='Fixture verifier approval', expected_hash=content_hash(c), parent_id=parent['id'])
        result = self.h.check(dict(agent=c['agent'], contract_id=c['id'], tool='triage.close', args={'bug_id': self.bug['id'], 'severity': 'S1'}, paths={'read': [], 'write': []}, spend=0))
        self.assertEqual(result['decision'], 'needs_approval')

    def test_real_reopening_and_second_closure_demo(self):
        from examples.reopening_demo import main
        with contextlib.redirect_stdout(io.StringIO()):
            result = main()
        self.assertEqual(result['reopening_closure']['status'], 'closed')
        self.assertEqual(Attempts(result['harness']).status('BUG-0001')['attempts_started'], 2)


if __name__ == '__main__':
    unittest.main()
