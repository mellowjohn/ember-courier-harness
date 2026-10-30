import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ember_harness.muse_chat import CreditLedger, MODEL, run, settle_capture, UNEXPECTED_USAGE
from ember_harness.core import digest


def retry_capture(request_id='historical-request'):
    events = [dict(payload_type='run.model.configured', payload=dict(model_id=MODEL, provider_id='meta')),
              dict(payload_type='run.usage', payload=dict(calls=2, failed_calls=1, completed_calls=1, cancelled_calls=0,
                   models=[dict(model=MODEL, calls=1, input_tokens=19641, output_tokens=3061)])),
              dict(payload_type='run.terminal.completed', payload=dict(terminal='completed', text='Saved reply'))]
    capture = dict(events=events, model=MODEL, exit_code=0, reservation_micro_usd=5_000_000,
                   ledger_request_id=request_id, response='Saved reply')
    capture['capture_sha256'] = digest(capture)
    return capture

ROOT = Path(__file__).resolve().parents[1]


class MuseChatTests(unittest.TestCase):
    def test_shared_credit_reservations_survive_restart_and_cannot_exceed_150(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            ledger = CreditLedger(folder)
            for i in range(30):
                ledger.reserve(str(i))
            with self.assertRaisesRegex(ValueError, 'budget'):
                CreditLedger(folder).reserve('31')
            self.assertEqual(CreditLedger(folder).summary()['reserved_usd'], 150)
            ledger.settle('0', 100, 100)
            ledger.settle('1', 100, 100)
            self.assertEqual(ledger.summary()['estimated_spent_usd'], .0011)
            CreditLedger(folder).reserve('31')
            self.assertLessEqual(ledger.summary()['reserved_usd'] + ledger.summary()['estimated_spent_usd'], 150)
            with self.assertRaises(ValueError):
                ledger.reserve('31')

    def test_muse_transport_is_single_step_metered_and_does_not_repeat_saved_reply(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            session = root / 'session'
            session.mkdir()
            binary = root / 'muse-test.exe'
            binary.write_bytes(b'test binary, never executed')
            events = [dict(payload_type='run.terminal.completed', payload=dict(terminal='completed', text='Muse reply')),
                      dict(payload_type='run.usage', payload=dict(calls=1, completed_calls=1, failed_calls=0,
                           models=[dict(model=MODEL, calls=1, input_tokens=100, output_tokens=100)]))]

            def start(args, **kwargs):
                self.assertEqual(args[args.index('--provider') + 1], 'meta')
                self.assertEqual(args[args.index('--max-model-steps') + 1], '1')
                self.assertEqual(args[args.index('--config') + 1], 'provider_retry.max_retries=0')
                for flag in ('--disable-write', '--disable-shell', '--disable-web-tools', '--no-foreign-personal-context'):
                    self.assertIn(flag, args)
                self.assertNotIn('--yolo', args)
                kwargs['stdout'].write(('\n'.join(json.dumps(e) for e in events)).encode())
                kwargs['stdout'].flush()
                from unittest.mock import Mock
                return Mock(wait=Mock(return_value=0))

            with patch('ember_harness.muse_chat.subprocess.Popen', side_effect=start) as process:
                first = run(root, session, 'Hello', 'turn-one', binary=binary)
                second = run(root, session, 'Hello', 'turn-one', binary=binary)
                self.assertEqual(first['response'], 'Muse reply')
                self.assertEqual(first, second)
                self.assertEqual(process.call_count, 1)
            self.assertEqual(CreditLedger(root).summary()['estimated_spent_usd'], .00055)
            self.assertEqual(CreditLedger(root).summary()['reserved_usd'], 0)
            capture = session / 'muse-captures/turn-one.json'
            data = json.loads(capture.read_bytes())
            data['response'] = 'changed'
            capture.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'changed'):
                run(root, session, 'Hello', 'turn-one', binary=binary)

    def test_stream_reports_observed_phases_without_exposing_provider_text(self):
        import subprocess
        from unittest.mock import Mock
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            session = root / 'session'
            session.mkdir()
            binary = root / 'muse-test.exe'
            binary.write_bytes(b'synthetic binary')
            reports = []
            def start(args, **kwargs):
                events = iter([
                    dict(payload_type='run.lifecycle.started', payload=dict(prompt='PRIVATE PROMPT')),
                    dict(payload_type='run.output.delta', payload=dict(text='PRIVATE RESPONSE')),
                    dict(payload_type='run.terminal.completed', payload=dict(terminal='completed', text='Reply')),
                ])
                def wait(timeout):
                    event = next(events)
                    kwargs['stdout'].write((json.dumps(event) + '\n').encode())
                    kwargs['stdout'].flush()
                    if event['payload_type'] != 'run.terminal.completed':
                        raise subprocess.TimeoutExpired(args, timeout)
                    return 0
                return Mock(wait=wait)
            with patch('ember_harness.muse_chat.subprocess.Popen', side_effect=start):
                capture = run(root, session, 'Hello', 'progress-stream', binary=binary,
                              progress=lambda phase, **values: reports.append(dict(phase=phase, **values)))
            self.assertEqual([r['phase'] for r in reports], ['muse_working', 'receiving', 'provider_finished'])
            self.assertEqual(reports[1]['response_chars'], len('PRIVATE RESPONSE'))
            self.assertNotIn('PRIVATE', json.dumps(reports))
            self.assertEqual(capture['response'], 'Reply')
            self.assertEqual(CreditLedger(root).summary()['reserved_usd'], 5)

    def test_progress_failure_stops_cli_and_keeps_credit_reservation(self):
        import subprocess
        from unittest.mock import Mock
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            session = root / 'session'
            session.mkdir()
            binary = root / 'muse-test.exe'
            binary.write_bytes(b'synthetic binary')
            process = Mock(wait=Mock(side_effect=[subprocess.TimeoutExpired('muse', .25), 0]))
            def start(args, **kwargs):
                kwargs['stdout'].write(b'{"payload_type":"run.lifecycle.started"}\n')
                kwargs['stdout'].flush()
                return process
            with patch('ember_harness.muse_chat.subprocess.Popen', side_effect=start):
                with self.assertRaisesRegex(OSError, 'SYNTHETIC disk failure'):
                    run(root, session, 'Hello', 'failed-progress', binary=binary,
                        progress=Mock(side_effect=OSError('SYNTHETIC disk failure')))
            process.kill.assert_called_once()
            self.assertEqual(CreditLedger(root).summary()['reserved_usd'], 5)

    def test_inspected_retry_keeps_full_hold_and_replays_without_dispatch(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            ledger = CreditLedger(root)
            ledger.reserve('historical-request')
            capture = retry_capture()
            with self.assertRaisesRegex(ValueError, 'inspection'):
                settle_capture(ledger, 'unused', capture)
            self.assertEqual(ledger.read()['blocked'], UNEXPECTED_USAGE)
            inspection = ledger.retain_inspected_retry(capture)
            self.assertEqual(inspection['total_bound_micro_usd'], 4_494_009)
            self.assertEqual(ledger.summary()['reserved_usd'], 5)
            self.assertIsNone(ledger.summary()['blocked'])
            session = root / 'session'
            (session / 'muse-captures').mkdir(parents=True)
            (session / 'muse-captures/turn.json').write_text(json.dumps(capture), encoding='utf-8')
            binary = root / 'muse-test.exe'
            binary.write_bytes(b'never executed')
            with patch('ember_harness.muse_chat.subprocess.Popen') as process:
                self.assertEqual(run(root, session, 'Hello', 'turn', binary=binary)['response'], 'Saved reply')
                process.assert_not_called()
            self.assertEqual(ledger.summary()['reserved_usd'], 5)
            self.assertEqual(ledger.summary()['estimated_spent_usd'], 0)

    def test_retry_inspection_rejects_unbounded_usage_and_other_open_reservations(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            ledger = CreditLedger(folder)
            ledger.reserve('historical-request')
            ledger.freeze(UNEXPECTED_USAGE)
            for change in ('hash', 'model', 'calls', 'tokens'):
                capture = retry_capture()
                if change == 'hash':
                    capture['response'] = 'changed'
                else:
                    if change == 'model':
                        capture['events'][0]['payload']['model_id'] = 'other-model'
                    elif change == 'calls':
                        capture['events'][1]['payload']['failed_calls'] = 2
                    else:
                        capture['events'][1]['payload']['models'][0]['output_tokens'] = 500000
                    capture['capture_sha256'] = digest({k: v for k, v in capture.items() if k != 'capture_sha256'})
                with self.subTest(change=change), self.assertRaises(ValueError):
                    ledger.retain_inspected_retry(capture)
            self.assertEqual(ledger.summary()['reserved_usd'], 5)
            self.assertEqual(ledger.read()['blocked'], UNEXPECTED_USAGE)
            # A second unresolved request must not be silently cleared by this inspection.
            data = ledger.read()
            data['requests']['other-request'] = dict(status='reserved', reserved_micro_usd=5_000_000)
            ledger.path.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Other unresolved'):
                ledger.retain_inspected_retry(retry_capture())

    def test_changed_inspected_capture_refreezes_without_releasing_hold(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            ledger = CreditLedger(folder)
            ledger.reserve('historical-request')
            ledger.freeze(UNEXPECTED_USAGE)
            capture = retry_capture()
            ledger.retain_inspected_retry(capture)
            capture['events'][1]['payload']['models'][0]['output_tokens'] += 1
            capture['capture_sha256'] = digest({k: v for k, v in capture.items() if k != 'capture_sha256'})
            with self.assertRaisesRegex(ValueError, 'changed'):
                settle_capture(ledger, 'unused', capture)
            self.assertEqual(ledger.summary()['reserved_usd'], 5)
            self.assertEqual(ledger.read()['blocked'], 'Inspected Muse capture changed')


if __name__ == '__main__':
    unittest.main()
