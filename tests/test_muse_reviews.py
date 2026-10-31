from copy import deepcopy
from hashlib import sha256
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ember_harness import canonical, content_hash
from ember_harness.contract_lock import verify
from ember_harness.muse_reviews import MuseReviews, capture, validate_history, MAX_CAPTURE
from examples.muse_review_demo import setup, intake_findings, main


class MuseReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.ctx = setup(Path(self.temp.name).resolve(), provider='manual')
        self.h = self.ctx['h']
        self.reviews = MuseReviews(self.h)

    def run_review(self, **kwargs):
        return self.reviews.run(self.ctx['request_path'], contract_id=self.ctx['reviewer_contract']['id'], provider=kwargs.pop('provider', 'manual'), **kwargs)

    def reapprove(self, *, request=None, response=None, role=None, max_calls=None):
        if request is not None:
            self.ctx['request_path'].write_bytes(canonical(request))
        if response is not None:
            self.ctx['response'].write_bytes(canonical(response))
        c = deepcopy(self.ctx['reviewer_contract'])
        c['id'] = 'ct-muse-review-updated-0002'
        for item in c['inputs']:
            item['sha256'] = sha256(Path(item['path']).read_bytes()).hexdigest()
        if role:
            c['extensions']['orchestration']['role'] = role
        if max_calls:
            c['limits']['max_calls'] = max_calls
        self.h.save_draft(c)
        self.h.approve(c['id'], 1, approver='johnathan', quote='Updated unit fixture review approval', expected_hash=content_hash(c), parent_id='ct-muse-review-scope-0001')
        self.assertTrue(self.h.verify_inputs(c['id']))
        self.ctx['reviewer_contract'] = c

    def echo(self, side_effect=None):
        request = deepcopy(self.ctx['request'])
        request.pop('response_path')
        request['fixture_findings'] = json.loads(self.ctx['response'].read_text())
        self.reapprove(request=request)
        binary = Path(self.temp.name) / 'muse.exe'
        binary.write_bytes(b'trusted unit transport executable placeholder; never executed')
        self.reviews = MuseReviews(self.h, binary=binary, binary_sha256=sha256(binary.read_bytes()).hexdigest())
        def run(command, **kwargs):
            prompt = Path(command[-1]).read_text(encoding='utf-8')
            kwargs['stdout'].write(canonical({'payload_type': 'run.terminal.completed', 'payload': {'terminal': 'completed', 'text': 'echo: ' + prompt}}) + b'\n')
            if side_effect:
                side_effect(command, kwargs)
            return SimpleNamespace(returncode=0)
        return run

    def test_manual_import_and_separate_gated_intake(self):
        result = self.run_review()
        self.assertEqual((result['status'], result['label']), ('captured', 'self_reported'))
        bugs = intake_findings(self.ctx, self.reviews, result['capture_ref'])
        self.assertEqual((bugs[0]['state'], bugs[0]['owner']), ('needs_repro', 'QA'))
        self.assertIn('independent_repro', bugs[0]['completeness']['missing'])
        self.assertEqual(bugs[0]['review_provenance']['capture_ref'], result['capture_ref'])
        self.assertTrue(verify(self.h.root)['ok'])

    def test_echo_fixed_argv_no_repository_workspace_no_shell(self):
        fake = self.echo()
        original = self.ctx['source'].read_bytes()
        with patch('ember_harness.muse_reviews.subprocess.run', side_effect=fake) as runner:
            result = self.run_review(provider='echo')
        args, kwargs = runner.call_args
        self.assertFalse(kwargs['shell'])
        command = args[0]
        for flag in ('--disable-shell', '--disable-write', '--disable-web-tools', '--disable-reminders', '--no-session-log'):
            self.assertIn(flag, command)
        self.assertNotIn('--workspace', command)
        self.assertIn('--preset', command)
        self.assertIn('empty', command)
        self.assertEqual(result['label'], 'fixture_echo')
        self.assertEqual(self.ctx['source'].read_bytes(), original)
        self.assertTrue(verify(self.h.root)['ok'])

    def test_meta_cannot_bypass_credit_guard_even_with_approve_all(self):
        self.reapprove()
        with patch('ember_harness.muse_reviews.subprocess.run') as runner:
            with self.assertRaisesRegex(ValueError, 'muse_credit_limit_unavailable'):
                self.run_review(provider='meta')
        runner.assert_not_called()
        self.assertEqual(self.h._entries()[-1]['decision'], 'deny')

    def test_non_verifier_and_revoked_contract_rejected(self):
        self.reapprove(role='triage')
        with self.assertRaisesRegex(ValueError, 'read-only verifier'):
            self.run_review()
        self.h.revoke(self.ctx['reviewer_contract']['id'], approver='johnathan', reason='Fixture ends authority')
        with self.assertRaisesRegex(ValueError, 'active approved'):
            self.run_review()

    def test_changed_request_refused_before_transport(self):
        self.ctx['request_path'].write_bytes(b'{}')
        with patch('ember_harness.muse_reviews.subprocess.run') as runner:
            with self.assertRaisesRegex(ValueError, 'changed'):
                self.run_review()
        runner.assert_not_called()

    def test_changed_source_refused(self):
        self.ctx['source'].write_bytes(b'unapproved source')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.run_review()

    def test_out_of_scope_source_is_gated_before_read(self):
        outside = Path(self.temp.name) / 'outside.txt'
        outside.write_text('do not transmit', encoding='utf-8')
        self.reapprove(request={**self.ctx['request'], 'files': [outside.as_posix()]})
        with self.assertRaisesRegex(ValueError, 'path_outside_scope'):
            self.run_review()

    def test_unpinned_source_within_scope_refused(self):
        extra = self.ctx['inputs'] / 'unapproved.py'
        extra.write_text('do not transmit', encoding='utf-8')
        self.reapprove(request={**self.ctx['request'], 'files': [extra.as_posix()]})
        with self.assertRaisesRegex(ValueError, 'must be pinned'):
            self.run_review()

    def test_request_cannot_inject_command_flags(self):
        self.reapprove(request={**self.ctx['request'], 'command': 'anything'})
        with self.assertRaises(Exception):
            self.run_review()

    def test_oversize_input_refused(self):
        self.ctx['source'].write_bytes(b'x' * (64 * 1024 + 1))
        self.reapprove()
        with self.assertRaisesRegex(ValueError, 'byte limit'):
            self.run_review()

    def test_invalid_output_is_captured_failed_without_findings(self):
        self.reapprove(response=[{'summary': 'Attempt to supply authority', 'area': 'balance', 'expected': 'x', 'actual': 'y', 'contract_id': 'ct-untrusted-0001'}])
        result = self.run_review()
        self.assertEqual(result['status'], 'failed')
        with self.assertRaisesRegex(ValueError, 'successful audited'):
            self.reviews.findings(result['capture_ref'])
        self.assertTrue(verify(self.h.root)['ok'])

    def test_missing_or_changed_binary_is_audited_failure(self):
        self.echo()
        self.reviews.binary.write_bytes(b'changed binary')
        with patch('ember_harness.muse_reviews.subprocess.run') as runner:
            result = self.run_review(provider='echo')
        runner.assert_not_called()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('trusted pinned', result['error'])

    def test_timeout_is_audited_without_retry(self):
        self.echo()
        with patch('ember_harness.muse_reviews.subprocess.run', side_effect=subprocess.TimeoutExpired('muse', 1)) as runner:
            result = self.run_review(provider='echo', timeout=1)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('TimeoutExpired', result['error'])
        self.assertTrue(verify(self.h.root)['ok'])

    def test_bad_echo_terminal_cannot_claim_success(self):
        fake = self.echo()
        for invalid in (b'not json\n', b'[]\n'):
            def corrupt(command, **kwargs):
                completed = fake(command, **kwargs)
                kwargs['stdout'].write(invalid)
                return completed
            with patch('ember_harness.muse_reviews.subprocess.run', side_effect=corrupt):
                result = self.run_review(provider='echo')
            self.assertEqual(result['status'], 'failed')

    def test_source_change_during_run_marks_capture_stale(self):
        fake = self.echo(lambda command, kwargs: self.ctx['source'].write_bytes(b'changed during execution'))
        with patch('ember_harness.muse_reviews.subprocess.run', side_effect=fake):
            result = self.run_review(provider='echo')
        self.assertEqual(result['status'], 'failed')
        self.assertIn('changed', result['error'])

    def test_revocation_during_run_cannot_produce_accepted_findings(self):
        fake = self.echo(lambda command, kwargs: self.h.revoke(self.ctx['reviewer_contract']['id'], approver='johnathan', reason='End fixture while running'))
        with patch('ember_harness.muse_reviews.subprocess.run', side_effect=fake):
            result = self.run_review(provider='echo')
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(verify(self.h.root)['ok'])

    def test_call_limit_survives_restart(self):
        self.reapprove(max_calls=2)
        self.run_review()
        self.reviews = MuseReviews(self.h)
        with self.assertRaisesRegex(ValueError, 'limit_exceeded'):
            self.run_review()

    def test_capture_tampering_fails_lock_and_export(self):
        result = self.run_review()
        Path(result['path']).write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'tampered'):
            self.reviews.findings(result['capture_ref'])
        self.assertFalse(verify(self.h.root)['ok'])

    def test_derived_finding_tampering_is_not_overwritten(self):
        result = self.run_review()
        files = self.reviews.findings(result['capture_ref'])
        Path(files[0]['path']).write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'artifact was changed'):
            self.reviews.findings(result['capture_ref'])

    def test_history_rejects_forged_provider_or_input_bytes(self):
        result = self.run_review()
        entries = deepcopy(self.h._entries())
        entries[-1]['provider'] = 'meta'
        with self.assertRaises(ValueError):
            validate_history(self.h, entries)
        self.assertEqual(capture(self.h, result['capture_ref'])['provider'], 'manual')

    def test_report_cannot_overwrite_captured_review(self):
        from ember_harness.reporting import write_intake_report
        result = self.run_review()
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            write_intake_report(self.h, self.ctx['data'], result['path'])

    def test_cli_manual_capture_and_export(self):
        from ember_harness.__main__ import main as cli
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = cli(['--store', str(self.h.root), 'muse-review', str(self.ctx['request_path']), '--contract', self.ctx['reviewer_contract']['id'], '--provider', 'manual'])
        self.assertEqual(rc, 0)
        result = json.loads(output.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli(['--store', str(self.h.root), 'muse-review-findings', result['capture_ref']]), 0)

    def test_code_review_cannot_claim_repro_by_supplying_steps(self):
        from examples.intake_demo import ingest
        finding = {**self.ctx['finding'], 'source': 'code_review', 'frequency': 'always'}
        bug = ingest(self.ctx, 'unverified-repro', finding)
        self.assertEqual(bug['state'], 'needs_repro')
        self.assertIn('independent_repro', bug['completeness']['missing'])

    def test_claim_cannot_be_changed_before_intake(self):
        result = self.run_review()
        files = self.reviews.findings(result['capture_ref'])
        finding = deepcopy(files[0]['finding'])
        finding['actual'] = 'Forged claim not in captured response'
        # The regular fixture intake can read this file; provenance validation must reject it.
        from examples.intake_demo import ingest
        with self.assertRaisesRegex(ValueError, 'differs from captured'):
            ingest(self.ctx, 'forged-review', finding)

    def test_capture_output_bound_is_audited(self):
        fake = self.echo(lambda command, kwargs: kwargs['stdout'].write(b'x' * (MAX_CAPTURE + 1)))
        with patch('ember_harness.muse_reviews.subprocess.run', side_effect=fake):
            result = self.run_review(provider='echo')
        self.assertEqual(result['status'], 'failed')
        self.assertIn('byte limit', result['error'])
        self.assertTrue(verify(self.h.root)['ok'])

    def test_manual_demo(self):
        with contextlib.redirect_stdout(io.StringIO()):
            result = main()
        self.assertIn('no verified hard credit cap', result['report'].read_text())


if __name__ == '__main__':
    unittest.main()
