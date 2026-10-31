"""Conversation durability and explicit model routing without live model calls."""
from pathlib import Path
import tempfile
import unittest
import threading
import json
from unittest.mock import patch

from ember_harness.local_ui import App
from ember_harness.session_chat import send, transcript, activity, MUSE_FREE_CREDITS_USD

ROOT = Path(__file__).resolve().parents[1]


class SessionChatTests(unittest.TestCase):
    def test_muse_turn_is_saved_and_idempotent_after_restart(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            with patch('ember_harness.session_chat.run_muse') as local:
                local.return_value = dict(response='Let us plan the courier route.')
                messages = send(folder, 'Plan a courier game', 'a' * 24, 'muse', root=ROOT)
                self.assertEqual([m['role'] for m in messages], ['user', 'assistant'])
                self.assertEqual(messages[0]['status'], 'complete')
                self.assertEqual(send(folder, 'Plan a courier game', 'a' * 24, 'muse', root=ROOT), messages)
                self.assertEqual(local.call_count, 1)
                self.assertEqual(transcript(folder), messages)
                with self.assertRaisesRegex(ValueError, 'another prompt'):
                    send(folder, 'Different prompt', 'a' * 24, 'muse', root=ROOT)

    def test_new_chat_session_does_not_start_workflow_and_model_choice_survives(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            (root / 'examples').mkdir()
            (root / 'examples/product_demo.py').touch()
            app = App(root)
            app.start('Chat first', chat_only=True, provider='muse')
            sid = app.session['id']
            self.assertIsNone(app.process)
            self.assertEqual(app.snapshot()['status'], 'idle')
            self.assertFalse(app.snapshot()['session']['workflow_started'])
            fresh = App(root)
            self.assertEqual(fresh.resume(sid)['session']['provider'], 'muse')
            with self.assertRaisesRegex(ValueError, 'Muse only'):
                fresh.choose_model('local')
            self.assertEqual(App(root).resume(sid)['session']['provider'], 'muse')
            self.assertFalse(fresh.snapshot()['models']['local'])

    def test_local_provider_cannot_be_started(self):
        self.assertEqual(MUSE_FREE_CREDITS_USD, 150)
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            with patch('ember_harness.session_chat.run_muse') as muse:
                with self.assertRaisesRegex(ValueError, 'Muse only'):
                    send(folder, 'Hello', 'a' * 24, 'local', root=ROOT)
                muse.assert_not_called()
            self.assertEqual(transcript(folder), [])

    def test_active_progress_survives_refresh_and_is_readable_during_inference(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            (root / 'examples').mkdir()
            (root / 'examples/product_demo.py').touch()
            app = App(root)
            app.start('Progress test', chat_only=True)
            sid = app.session['id']
            entered, release = threading.Event(), threading.Event()
            errors = []
            def provider(*args, **kwargs):
                kwargs['progress']('muse_working')
                kwargs['progress']('receiving', response_chars=42)
                entered.set()
                if not release.wait(5):
                    raise TimeoutError('Test did not release inference')
                return dict(response='A saved reply')
            def request():
                try:
                    app.chat('Plan my game', 'progress-test-0001')
                except Exception as error:
                    errors.append(error)
            with patch('ember_harness.session_chat.run_muse', side_effect=provider):
                worker = threading.Thread(target=request)
                worker.start()
                try:
                    self.assertTrue(entered.wait(5))
                    live = app.snapshot()['chat_activity']
                    self.assertEqual((live['state'], live['phase'], live['response_chars']), ('active', 'receiving', 42))
                    fresh = App(root)
                    self.assertEqual(fresh.resume(sid)['chat_activity'], live)
                finally:
                    release.set()
                    worker.join(5)
            self.assertFalse(errors)
            self.assertFalse(worker.is_alive())
            done = app.snapshot()['chat_activity']
            self.assertEqual((done['state'], done['phase']), ('complete', 'complete'))
            self.assertEqual([e['phase'] for e in done['events']],
                             ['saved', 'context', 'provider_starting', 'muse_working', 'receiving', 'validating', 'complete'])

    def test_abandoned_pending_request_is_interrupted_and_failed_retry_resets_status(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            with patch('ember_harness.session_chat.run_muse', side_effect=ValueError('SYNTHETIC provider failure')):
                with self.assertRaises(ValueError):
                    send(folder, 'Hello', 'progress-test-0001', 'muse', root=ROOT)
            self.assertEqual(activity(folder)['state'], 'failed')
            path = Path(folder) / 'chat.json'
            saved = transcript(folder)
            saved[0]['status'] = 'pending'
            path.write_text(json.dumps(saved), encoding='utf-8')
            self.assertEqual(activity(folder)['state'], 'interrupted')
            def retried(*args, **kwargs):
                self.assertEqual(transcript(folder)[0]['status'], 'pending')
                self.assertNotIn('error', transcript(folder)[0])
                return dict(response='Recovered')
            with patch('ember_harness.session_chat.run_muse', side_effect=retried):
                send(folder, 'Hello', 'progress-test-0001', 'muse', root=ROOT)
            self.assertEqual(activity(folder)['state'], 'complete')



if __name__ == '__main__':
    unittest.main()
