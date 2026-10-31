"""Synthetic host responses test the protocol; they never count as real owner E2E evidence."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
import threading
from unittest.mock import patch

from ember_harness import Harness, draft, canonical
from ember_harness.owner_review import OwnerReview, decide, validate_history
from ember_harness.contract_lock import verify


class OwnerReviewTests(unittest.TestCase):
    def setUp(self):
        scratch = Path.cwd() / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.h = Harness(Path(self.temp.name) / 'state')
        self.owner = OwnerReview()
        self.c = draft('ct-owner-scope-0001', 'planner', 'Test explicit owner review', role='scope')
        self.c['approval_mode'] = 'approve_all'
        self.c['allowed_actions'] = [dict(action_id='pick', tool='scope.select', **{'class': 'direction_selection'},
            args_constraints=dict(selection={'one_of': ['A', 'B']}), allow_no_evidence=True)]
        self.quote = 'AUTOMATED UNIT TEST RESPONSE ONLY; not a real human approval.'

    def pending(self):
        entries = self.h._entries()
        return next(e['request_ref'] for e in reversed(entries) if e['kind'] == 'owner_request')

    def approve_scope(self):
        def respond(*args):
            decide(self.h, self.pending(), 'approve', self.quote)
        with patch('ember_harness.owner_review.time.sleep', side_effect=respond), redirect_stdout(io.StringIO()):
            return self.owner.contract(self.h, self.c)

    def test_waiting_grants_nothing(self):
        with patch('ember_harness.owner_review.time.sleep', side_effect=RuntimeError('test pause')), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'test pause'):
                self.owner.contract(self.h, self.c)
        self.assertFalse(self.h._active(self.h._entries()))
        self.assertFalse(any(e['kind'] == 'approval' for e in self.h._entries()))

    def test_approval_between_replay_read_and_save_is_observed_without_rewriting(self):
        with patch('ember_harness.owner_review.time.sleep',side_effect=RuntimeError('SYNTHETIC pause')),redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):self.owner.contract(self.h,self.c)
        original_save=self.h.save_draft;approved_bytes=[]
        def race(contract):
            decide(self.h,self.pending(),'approve',self.quote)
            approved_bytes.append(self.h._path(contract['id'],contract['version']).read_bytes())
            return original_save(contract)
        with patch.object(self.h,'save_draft',side_effect=race),redirect_stdout(io.StringIO()):
            result=self.owner.contract(self.h,self.c)
        self.assertEqual(result['status'],'approved')
        self.assertEqual(self.h._path(self.c['id'],1).read_bytes(),approved_bytes[0])
        self.assertEqual(validate_history(self.h,self.h._entries()),1)
        self.assertEqual(len([e for e in self.h._entries() if e['kind']=='approval' and e.get('scope')=='contract']),1)
        with self.assertRaisesRegex(ValueError,'immutable'):self.h.save_draft(self.c)

    def test_replay_save_error_without_an_approval_does_not_grant_authority(self):
        with patch.object(self.h,'save_draft',side_effect=ValueError('SYNTHETIC save failure')):
            with self.assertRaisesRegex(ValueError,'save failure'):self.owner.contract(self.h,self.c)
        self.assertFalse(self.h._active(self.h._entries()))

    def test_explicit_response_binds_exact_review_and_cannot_replay(self):
        c = self.approve_scope()
        self.assertEqual(c['status'], 'approved')
        self.assertEqual(validate_history(self.h, self.h._entries()), 1)
        self.assertTrue(verify(self.h.root)['ok'])
        with self.assertRaisesRegex(ValueError, 'already decided'):
            decide(self.h, self.pending(), 'approve', self.quote)

    def test_decline_stops_without_authority(self):
        def respond(*args):
            decide(self.h, self.pending(), 'decline', self.quote)
        with patch('ember_harness.owner_review.time.sleep', side_effect=respond), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'owner declined'):
                self.owner.contract(self.h, self.c)
        self.assertFalse(self.h._active(self.h._entries()))

    def test_changed_draft_needs_new_review(self):
        def respond(*args):
            changed = dict(self.c, goal='Unreviewed wider goal')
            self.h._path(self.c['id'], 1).write_bytes(canonical(changed))
            decide(self.h, self.pending(), 'approve', self.quote)
        with patch('ember_harness.owner_review.time.sleep', side_effect=respond), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'contract changed'):
                self.owner.contract(self.h, self.c)
        self.assertFalse(self.h._active(self.h._entries()))

    def test_changed_packet_cannot_grant_authority(self):
        def respond(*args):
            ref = self.pending()
            (self.h.root / 'owner-review' / ref / 'request.json').write_bytes(b'{}')
            decide(self.h, ref, 'approve', self.quote)
        with patch('ember_harness.owner_review.time.sleep', side_effect=respond), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'hash or store'):
                self.owner.contract(self.h, self.c)
        self.assertFalse(self.h._active(self.h._entries()))

    def test_blank_response_refused(self):
        def respond(*args):
            decide(self.h, self.pending(), 'approve', ' ')
        with patch('ember_harness.owner_review.time.sleep', side_effect=respond), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'actual owner response'):
                self.owner.contract(self.h, self.c)

    def test_action_approval_is_exact_and_one_use(self):
        c = self.approve_scope()
        action = dict(agent=c['agent'], contract_id=c['id'], contract_version=1, tool='scope.select',
                      args=dict(selection='A'), paths=dict(read=[], write=[]), spend=0)
        def respond(*args):
            decide(self.h, self.pending(), 'approve', self.quote)
        with patch('ember_harness.owner_review.time.sleep', side_effect=respond), redirect_stdout(io.StringIO()):
            self.owner.action(self.h, action)
        self.assertEqual(self.h.check({**action, 'args': dict(selection='B')})['decision'], 'needs_approval')
        self.assertEqual(self.h.check(action)['decision'], 'allow')
        self.assertEqual(self.h.check(action)['decision'], 'needs_approval')
        self.assertTrue(verify(self.h.root)['ok'])

    def test_interrupted_receipt_can_recover_without_duplicate_approval(self):
        original = self.h._append
        def broken(kind, **kwargs):
            if kind == 'owner_decision':
                raise OSError('receipt write failed')
            return original(kind, **kwargs)
        def respond(*args):
            decide(self.h, self.pending(), 'approve', self.quote)
        with patch.object(self.h, '_append', side_effect=broken), patch('ember_harness.owner_review.time.sleep', side_effect=respond), redirect_stdout(io.StringIO()):
            with self.assertRaises(OSError):
                self.owner.contract(self.h, self.c)
        decide(self.h, self.pending(), 'approve', self.quote)
        approvals = [e for e in self.h._entries() if e['kind'] == 'approval' and e.get('scope') == 'contract']
        self.assertEqual(len(approvals), 1)

    def request_scope(self):
        self.h.save_draft(self.c)
        with redirect_stdout(io.StringIO()):
            return self.owner._request(self.h, 'contracts',
                dict(contracts=[dict(contract=self.c, parent_id=None)]), wait=False)

    def test_brief_writer_contention_retries_the_same_explicit_decision(self):
        ref = self.request_scope()
        held, release = threading.Event(), threading.Event()
        def writer():
            with self.h._lock():
                held.set()
                release.wait(3)
        worker = threading.Thread(target=writer)
        worker.start()
        try:
            self.assertTrue(held.wait(2))
            real_sleep = __import__('time').sleep
            def finish_writer(delay):
                release.set()
                worker.join(2)
                real_sleep(delay)
            with patch('ember_harness.core.time.sleep', side_effect=finish_writer):
                result = decide(self.h, ref, 'approve', self.quote)
            self.assertEqual(result['status'], 'approved')
            entries = self.h._entries()
            self.assertEqual(len([e for e in entries if e['kind'] == 'approval']), 1)
            self.assertEqual(validate_history(self.h, entries), 1)
        finally:
            release.set()
            worker.join(3)

    def test_persistent_writer_lock_is_never_removed(self):
        ref = self.request_scope()
        with self.h._lock():
            with patch('ember_harness.core.time.monotonic', side_effect=[0, 3]):
                with self.assertRaises(FileExistsError):
                    decide(self.h, ref, 'approve', self.quote)
            self.assertTrue((self.h.root / '.writer.lock').exists())
        self.assertFalse(any(e['kind'] == 'approval' for e in self.h._entries()))

    def test_other_file_conflicts_are_not_retried(self):
        ref = self.request_scope()
        error = FileExistsError(17, 'existing unrelated file', str(self.h.root / 'unrelated.json'))
        with patch.object(self.h, 'approve', side_effect=error) as approve:
            with self.assertRaises(FileExistsError):
                decide(self.h, ref, 'approve', self.quote)
            self.assertEqual(approve.call_count, 1)

        self.assertTrue(verify(self.h.root)['ok'])
