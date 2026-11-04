"""Exercise local settings and both billing paths without calling Meta."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ember_harness import muse_chat, muse_image, muse_settings
from ember_harness.local_ui import App, server


class MuseSettingsTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.binary = self.root / 'synthetic-muse.exe'
        self.binary.touch()

    def test_subscription_uses_local_sign_in_and_replay_needs_no_allowance_check(self):
        def start(args, **kwargs):
            self.assertEqual(args[1], 'exec')
            self.assertEqual(args[args.index('--base-url') + 1], muse_settings.API_BASE_URL)
            self.assertEqual(kwargs['env'], usage.call_args.kwargs['env'])
            self.assertNotIn('META_API_KEY', kwargs['env'])
            self.assertNotIn('MODEL_API_KEY', kwargs['env'])
            for event in (
                dict(payload_type='run.usage', payload=dict(calls=1, failed_calls=0, completed_calls=1,
                     models=[dict(model=muse_chat.MODEL, calls=1, input_tokens=10, output_tokens=10)])),
                dict(payload_type='run.terminal.completed', payload=dict(terminal='completed', text='Connected')),
            ):
                kwargs['stdout'].write(json.dumps(event).encode() + b'\n')
            return Mock(wait=Mock(return_value=0))

        self.assertEqual(muse_settings.mode(self.root), 'subscription')
        result = subprocess.CompletedProcess([], 0, b'{"allowance":{"window":{"used_percent":12.5}}}')
        with patch.dict(os.environ, {'META_API_KEY': 'synthetic-ambient', 'MODEL_API_KEY': 'synthetic-alias'}), \
                patch('ember_harness.muse_settings.subprocess.run', return_value=result) as usage, \
                patch('ember_harness.muse_chat.subprocess.Popen', side_effect=start) as dispatch:
            first = muse_chat.run(self.root, self.root, 'Hello', 'first', binary=self.binary)
            replay = muse_chat.run(self.root, self.root, 'Hello', 'first', binary=self.binary)
        self.assertEqual(first, replay)
        self.assertEqual(first['response'], 'Connected')
        self.assertEqual(usage.call_args.args[0], [str(self.binary), 'usage', '--json'])
        usage.assert_called_once()
        dispatch.assert_called_once()

    def test_missing_or_exhausted_subscription_stops_before_reserving_or_dispatching(self):
        for reply in (b'{"status":"no_allowance"}', b'{"allowance":null}',
                      b'{"window":{"used_percent":15},"weekly":{"used_percent":100}}'):
            with self.subTest(reply=reply), \
                    patch('ember_harness.muse_settings.subprocess.run', return_value=Mock(stdout=reply)), \
                    patch('ember_harness.muse_chat.subprocess.Popen') as dispatch:
                with self.assertRaisesRegex(ValueError, 'subscription'):
                    muse_chat.run(self.root, self.root, 'Hello', 'no-allowance', binary=self.binary)
                dispatch.assert_not_called()
                self.assertFalse(muse_chat.CreditLedger(self.root).path.exists())
        with patch('ember_harness.muse_settings.api_credential') as key:
            self.assertFalse(muse_image.status(self.root)['ready'])
            with self.assertRaisesRegex(muse_image.ImageUnavailable, 'Model API promotional credits'):
                muse_image.verify_coverage(self.root, 1_000_000, no_paid_fallback=True)
            key.assert_not_called()

    def test_api_credit_opt_in_is_bound_to_the_local_key(self):
        with patch.dict(os.environ, {'META_API_KEY': '', 'MODEL_API_KEY': 'synthetic-owner-key'}), \
                patch('ember_harness.muse_settings.subprocess.run') as usage:
            with self.assertRaisesRegex(ValueError, 'Confirm your own promotional credits'):
                muse_settings.save(self.root, 'api_credits')
            self.assertEqual(muse_settings.save(self.root, 'api_credits', no_paid_fallback=True), {'mode': 'api_credits'})
            self.assertEqual(muse_settings.mode(self.root), 'api_credits')
            env = muse_settings.request_environment(self.root, self.binary, self.root)
            self.assertEqual(env['META_API_KEY'], 'synthetic-owner-key')
            self.assertEqual(muse_image.credential(self.root), env['META_API_KEY'])
            self.assertNotIn('synthetic-owner-key', (self.root / '.harness/muse-settings.json').read_text())
            with patch.dict(os.environ, {'META_API_KEY': 'synthetic-other-account'}):
                with self.assertRaisesRegex(ValueError, 'credential changed'):
                    muse_settings.request_environment(self.root, self.binary, self.root)
                self.assertIn('credential changed', muse_image.status(self.root)['reason'])
            usage.assert_not_called()

    def test_settings_routes_are_private_and_do_not_expose_credentials(self):
        (self.root / 'examples').mkdir()
        (self.root / 'examples/product_demo.py').touch()
        app = App(self.root)
        http = server(app)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{http.server_port}/api/'

        def request(path, body=None, token=app.token):
            headers = {'X-Ember-Token': token, 'Content-Type': 'application/json'}
            with urlopen(Request(base + path, data=None if body is None else json.dumps(body).encode(), headers=headers)) as response:
                return json.load(response)

        try:
            for path in ('muse-settings', 'muse-settings/check'):
                with self.assertRaises(HTTPError) as denied:
                    request(path, {}, token='')
                self.assertEqual(denied.exception.code, 403)
            self.assertEqual(request('state')['models']['billing_mode'], 'subscription')
            with patch.dict(os.environ, {'META_API_KEY': 'synthetic-owner-key'}), \
                    patch('ember_harness.local_ui.installed_binary', return_value=self.binary), \
                    patch('ember_harness.muse_settings.subprocess.run', return_value=Mock(stdout=b'{"window":{"used_percent":0}}')):
                self.assertEqual(request('muse-settings/check', {}), {'status': 'available'})
                self.assertEqual(request('muse-settings', {'mode': 'api_credits', 'no_paid_fallback': True}),
                                 {'mode': 'api_credits'})
                state = request('state')
                self.assertEqual(state['models']['billing_mode'], 'api_credits')
                self.assertNotIn('synthetic-owner-key', json.dumps(state))
                self.assertNotIn('credential_sha256', json.dumps(state))
            self.assertEqual(App(self.root).snapshot()['models']['billing_mode'], 'api_credits')
        finally:
            http.shutdown()
            http.server_close()
            worker.join()
