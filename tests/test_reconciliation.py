from copy import deepcopy
from pathlib import Path
import contextlib
import io
import json
import tempfile
import unittest
from unittest.mock import patch

from ember_harness import canonical
from ember_harness.attempts import Attempts, status
from ember_harness.contract_lock import verify
from ember_harness.reconciliation import Reconciliation, validate_history
from examples.intake_demo import ingest
from examples.reconciliation_demo import setup, fix, fail, propose, main


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.ctx = setup(Path(self.temp.name).resolve())
        self.h, self.intake = self.ctx['h'], self.ctx['intake']
        self.recon = Reconciliation(self.intake)
        self.a, self.b = ingest(self.ctx, 'a'), ingest(self.ctx, 'b')

    def abandon(self, bug, number):
        c = fix(self.ctx, bug['id'], number)
        self.h.revoke(c['id'], approver='johnathan', reason='Fixture abandons allocated attempt')
        return c

    def proposal(self):
        return propose(self.ctx, self.intake.get(self.a['id']), self.intake.get(self.b['id']))

    def approve(self, plan):
        return self.recon.approve(plan['plan_hash'], approver='johnathan', quote='Fixture owner reviewed exact reconciliation hash')

    def test_combines_terminal_attempts_preserves_snapshot_and_bindings(self):
        c = self.abandon(self.a, 1)
        self.abandon(self.a, 2)
        self.abandon(self.b, 1)
        path = Path(next(x for x in c['inputs'] if x['name'] == 'bug_snapshot')['path'])
        raw, approvals = path.read_bytes(), [e for e in self.h._entries() if e.get('bug_attempt')]
        plan = self.proposal()
        self.assertIsNone(self.intake.get(self.b['id'])['duplicate_of'])
        merged = self.approve(plan)['attempts']
        self.assertEqual(merged['status'], 'awaiting_decision')
        self.assertEqual([(x['number'], x['origin_bug_id'], x['origin_number']) for x in merged['attempts']], [(1, self.a['id'], 1), (2, self.a['id'], 2), (3, self.b['id'], 1)])
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual([e for e in self.h._entries() if e.get('bug_attempt')], approvals)
        self.assertEqual(Attempts(self.h).status(self.b['id'])['state_hash'], merged['state_hash'])
        with self.assertRaisesRegex(ValueError, 'attempt_limit'):
            fix(self.ctx, self.a['id'], 4)
        result = verify(self.h.root)
        self.assertTrue(result['ok'], result)
        self.assertEqual(len(result['bug_attempts']), 1)

    def test_running_attempt_blocks_proposal_until_revoked(self):
        c = fix(self.ctx, self.b['id'], 1)
        with self.assertRaisesRegex(ValueError, 'running'):
            self.proposal()
        self.h.revoke(c['id'], approver='johnathan', reason='Owner ends running attempt')
        self.assertEqual(self.approve(self.proposal())['attempts']['attempts_started'], 1)

    def test_running_attempt_after_proposal_blocks_approval(self):
        plan = self.proposal()
        fix(self.ctx, self.b['id'], 1)
        with self.assertRaisesRegex(ValueError, 'running'):
            self.approve(plan)
        self.assertIsNone(self.intake.get(self.b['id'])['duplicate_of'])

    def test_stale_bug_update(self):
        plan = self.proposal()
        ingest(self.ctx, 'update', bug_id=self.a['id'], expected_hash=self.a['record_hash'])
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.approve(plan)

    def test_stale_attempt_after_proposal(self):
        plan = self.proposal()
        self.abandon(self.b, 1)
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.approve(plan)

    def test_only_owner_and_nonblank_quote(self):
        plan = self.proposal()
        for actor, quote in [('demo-qa', 'approve'), ('johnathan', ' ')]:
            with self.assertRaisesRegex(ValueError, 'Johnathan'):
                self.recon.approve(plan['plan_hash'], approver=actor, quote=quote)

    def test_plan_tampering(self):
        plan = self.proposal()
        data = json.loads(Path(plan['path']).read_text())
        data['attempts_started'] = 0.5
        Path(plan['path']).write_bytes(canonical(data))
        with self.assertRaisesRegex(ValueError, 'hash'):
            self.approve(plan)
        self.assertFalse(verify(self.h.root)['ok'])

    def test_qa_revocation(self):
        plan = self.proposal()
        self.h.revoke(self.ctx['reviewer']['id'], approver='johnathan', reason='End QA authority')
        with self.assertRaisesRegex(ValueError, 'active approved'):
            self.approve(plan)

    def test_repeated_approval_cannot_double_count(self):
        plan = self.proposal()
        self.approve(plan)
        with self.assertRaises(ValueError):
            self.approve(plan)
        self.assertEqual(self.intake.get(self.a['id'])['duplicate_count'], 1)

    def test_retry_credit_canceled_and_stop_preserved(self):
        for bug in (self.a, self.b):
            for n in range(1, 4):
                self.abandon(bug, n)
            st = Attempts(self.h).status(bug['id'])
            Attempts(self.h).decide(bug['id'], choice='stop' if bug == self.a else 'retry', expected_state_hash=st['state_hash'], approver='johnathan', quote='Fixture owner decision')
        plan = self.proposal()
        self.assertEqual(len(plan['plan']['canceled_retry_refs']), 1)
        merged = self.approve(plan)['attempts']
        self.assertEqual(merged['attempts_started'], 6)
        self.assertEqual(merged['status'], 'stopped')
        self.assertIsNone(merged['retry_approval_ref'])
        with self.assertRaisesRegex(ValueError, 'stopped'):
            fix(self.ctx, self.a['id'], 7)
        self.assertTrue(verify(self.h.root)['ok'])

    def test_fresh_retry_exactly_one_attempt(self):
        for n in range(1, 4):
            self.abandon(self.a, n)
        st = self.approve(self.proposal())['attempts']
        Attempts(self.h).decide(self.b['id'], choice='retry', expected_state_hash=st['state_hash'], approver='johnathan', quote='Fixture explicit extra attempt')
        self.abandon(self.a, 4)
        with self.assertRaisesRegex(ValueError, 'attempt_limit'):
            fix(self.ctx, self.a['id'], 5)
        self.assertTrue(verify(self.h.root)['ok'])

    def test_chained_merges_count_once_and_resolve_old_alias(self):
        self.abandon(self.b, 1)
        self.approve(self.proposal())
        third = ingest(self.ctx, 'third')
        self.abandon(third, 1)
        plan = propose(self.ctx, third, self.intake.get(self.a['id']))
        st = self.approve(plan)['attempts']
        self.assertEqual(st['attempts_started'], 2)
        self.assertEqual(len(st['merged_bug_ids']), 3)
        self.assertEqual(status(self.h._entries(), self.b['id'])['state_hash'], st['state_hash'])
        self.assertTrue(verify(self.h.root)['ok'])

    def test_audit_failure_is_atomic(self):
        self.abandon(self.b, 1)
        plan = self.proposal()
        original = self.h._append
        def append(kind, **fields):
            if fields.get('scope') == 'duplicate_reconciliation':
                raise OSError('Fixture audit failure')
            return original(kind, **fields)
        with patch.object(self.h, '_append', side_effect=append):
            with self.assertRaises(OSError):
                self.approve(plan)
        self.assertIsNone(self.intake.get(self.b['id'])['duplicate_of'])
        self.assertEqual(status(self.h._entries(), self.b['id'])['attempts_started'], 1)
        self.approve(plan)

    def test_cache_failure_does_not_lose_atomic_history(self):
        plan = self.proposal()
        original = Path.write_bytes
        def write(path, data):
            if path.parent == self.intake.root / 'bugs':
                raise OSError('Fixture cache failure')
            return original(path, data)
        with patch.object(Path, 'write_bytes', new=write):
            result = self.approve(plan)
        self.assertEqual(len(result['cache_warnings']), 2)
        self.assertEqual(self.intake.get(self.b['id'])['duplicate_of'], self.a['id'])
        self.assertTrue(verify(self.h.root)['ok'])

    def test_invalid_hash_and_blank_note(self):
        with self.assertRaisesRegex(ValueError, 'hash'):
            self.recon.approve('../escape', approver='johnathan', quote='Fixture')
        with self.assertRaisesRegex(ValueError, 'note'):
            self.recon.propose(self.a['id'], self.b['id'], contract_id=self.ctx['reviewer']['id'], bug_hash=self.a['record_hash'], target_hash=self.b['record_hash'], note=' ')

    def test_lock_rejects_changed_merge_descriptor(self):
        self.approve(self.proposal())
        entries = deepcopy(self.h._entries())
        entries[-1]['reconciliation']['state_hashes'][0] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'ledger differs'):
            validate_history(self.h, entries)

    def test_high_severity_is_retained_on_oldest(self):
        b = ingest(self.ctx, 'critical', {**self.ctx['finding'], 'impact': 'crash'}, bug_id=self.b['id'], expected_hash=self.b['record_hash'])
        result = self.approve(propose(self.ctx, self.a, b))
        oldest = result['bugs'][0]
        self.assertEqual(oldest['severity_proposed'], 'S0')
        self.assertTrue(oldest['severity_review_required'])
        self.assertEqual(oldest['severity_basis'], 'merged_proposal')
        with self.assertRaisesRegex(ValueError, 'not ready'):
            self.intake.snapshot(self.a['id'], 'ct-fix-blocked-0001')

    def test_cli_and_report_show_combined_provenance(self):
        from ember_harness.__main__ import main as cli
        from ember_harness.reporting import write_attempt_report
        self.abandon(self.b, 1)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = cli(['--store', str(self.h.root), 'bug-reconcile-propose', self.a['id'], self.b['id'], '--root', str(self.intake.root), '--contract', self.ctx['reviewer']['id'], '--bug-hash', self.a['record_hash'], '--target-hash', self.b['record_hash'], '--note', 'Fixture QA confirms same repro'])
        self.assertEqual(rc, 0)
        plan = json.loads(output.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            rc = cli(['--store', str(self.h.root), 'bug-reconcile-approve', plan['plan_hash'], '--root', str(self.intake.root), '--quote', 'Fixture exact-plan owner approval'])
        self.assertEqual(rc, 0)
        report = write_attempt_report(self.h, self.b['id'])
        text = Path(report['path']).read_text()
        self.assertIn('Original bug / number', text)
        self.assertIn(plan['plan_hash'], text)

    def test_conflicting_routes_require_explicit_classification(self):
        self.a = ingest(self.ctx, 'refresh-hint', bug_id=self.a['id'], expected_hash=self.a['record_hash'])
        b = ingest(self.ctx, 'engine', {**self.ctx['finding'], 'area': 'engine'}, bug_id=self.b['id'], expected_hash=self.b['record_hash'])
        # An earlier candidate hint is insufficient to override the engine pause.
        with self.assertRaisesRegex(ValueError, 'routes'):
            propose(self.ctx, self.a, b)

    def test_report_cannot_overwrite_reviewed_plan(self):
        from ember_harness.reporting import write_attempt_report
        plan = self.proposal()
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            write_attempt_report(self.h, self.a['id'], plan['path'])
        self.assertTrue(verify(self.h.root)['ok'])

    def test_outcome_cannot_move_to_unrelated_bug(self):
        fail(self.ctx, self.a['id'], 1)
        entries = deepcopy(self.h._entries())
        entries[-1]['bug_id'] = self.b['id']
        with self.assertRaisesRegex(ValueError, 'unbound'):
            status(entries, self.a['id'])

    def test_real_regression_demo(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = main()
        self.addCleanup(lambda: __import__('shutil').rmtree(result['folder']))
        self.assertIn('Contract-lock and audit verification', result['report'].read_text())


if __name__ == '__main__':
    unittest.main()
