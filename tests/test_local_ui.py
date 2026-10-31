"""HTTP boundary and real workflow tests; owner responses here are synthetic fixtures."""
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ember_harness.local_ui import App, server
import ember_harness

ROOT = Path(__file__).resolve().parents[1]


class LocalUITest(unittest.TestCase):
    def test_session_history_validation_and_interrupted_worker(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            (root / 'examples').mkdir()
            (root / 'examples/product_demo.py').touch()
            app = App(root)
            with self.assertRaises(ValueError):
                app.save('No session')
            for invalid in ('../outside', '', 'z' * 24):
                with self.assertRaises(ValueError):
                    app.resume(invalid)
            for invalid in ('', ' ' * 10, 'x' * 121, 123):
                with self.assertRaises(ValueError):
                    app.start(invalid)
            sid = 'a' * 24
            session = app.sessions_dir / sid
            session.mkdir(parents=True)
            metadata = dict(id=sid, name='Original', created_at='2026-10-30',
                            updated_at='2026-10-30', mode='Local AI')
            (session / 'session.json').write_text(json.dumps(metadata), encoding='utf-8')
            (session / 'worker.json').write_text(json.dumps(dict(status='running', exit_code=None,
                heartbeat=time.time() - 60)), encoding='utf-8')
            (session / 'execution.log').touch()
            self.assertEqual(app.resume(sid)['status'], 'interrupted')
            app.save('Renamed')
            fresh = App(root)
            self.assertEqual(fresh.history()[0]['name'], 'Renamed')
            self.assertEqual(fresh.resume(sid)['mode'], 'Local AI')
            with self.assertRaises(ValueError):
                fresh.respond('a' * 64, 'approve', 'No worker')

    def test_http_workflow_and_approval_boundary(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            shutil.copytree(ROOT / 'examples', root / 'examples', ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(Path(ember_harness.__file__).parent, root / 'ember_harness', ignore=shutil.ignore_patterns('__pycache__'))
            app = App(root)
            http = server(app)
            worker = threading.Thread(target=http.serve_forever, daemon=True)
            worker.start()
            base = f'http://127.0.0.1:{http.server_port}'

            def request(route, body=None, token=True, origin=None):
                headers = {'Content-Type': 'application/json'}
                if token:
                    headers['X-Ember-Token'] = app.token
                if origin:
                    headers['Origin'] = origin
                req = Request(base + route, data=json.dumps(body).encode() if body is not None else None, headers=headers)
                try:
                    with urlopen(req, timeout=60) as response:
                        return json.load(response)
                except HTTPError as error:
                    error.msg = error.read().decode()
                    raise
            try:
                with self.assertRaises(HTTPError) as denied:
                    request('/api/start', {}, token=False)
                self.assertEqual(denied.exception.code, 403)
                for route in ('/api/state', '/api/sessions'):
                    with self.assertRaises(HTTPError):
                        request(route, token=False)
                with self.assertRaises(HTTPError):
                    request('/api/start', {}, origin='https://example.org')
                self.assertIsNone(app.process)
                request('/api/start', {'name': 'Courier restart test'})
                session_id = app.session['id']
                with self.assertRaises(HTTPError):
                    request('/api/start', {})
                count, deadline, first = 0, time.monotonic() + 120, None
                while time.monotonic() < deadline:
                    state = request('/api/state')
                    if state['status'] != 'running':
                        break
                    pending = [r for r in state['requests'] if not r['decision']]
                    if not pending:
                        time.sleep(.2)
                        continue
                    r = pending[0]
                    if first is None:
                        first = r['ref']
                        self.assertEqual(len(state['audit']), 1)
                        request('/api/save', {'name': 'Saved courier'})
                        original = app.process
                        http.shutdown()
                        http.server_close()
                        worker.join()
                        app = App(root)
                        http = server(app)
                        worker = threading.Thread(target=http.serve_forever, daemon=True)
                        worker.start()
                        base = f'http://127.0.0.1:{http.server_port}'
                        history = request('/api/sessions')
                        self.assertEqual(history[0]['name'], 'Saved courier')
                        resumed = request('/api/resume', {'id': session_id})
                        self.assertEqual(resumed['requests'][0]['ref'], first)
                        self.assertEqual(resumed['audit'], state['audit'])
                        self.assertEqual(resumed['status'], 'running')
                        self.assertIsNone(app.process)
                        request('/api/start', {'name': 'Second session', 'new_session': True})
                        second_worker = app.process
                        second_deadline = time.monotonic() + 30
                        while time.monotonic() < second_deadline:
                            second = request('/api/state')
                            if second['requests']:
                                break
                            time.sleep(.1)
                        self.assertTrue(second['requests'], second['log'])
                        request('/api/decide', dict(ref=second['requests'][0]['ref'], choice='decline',
                            quote='SYNTHETIC TEST: stop the second isolated session'))
                        second_worker.wait(timeout=15)
                        self.assertEqual(len(request('/api/sessions')), 2)
                        resumed = request('/api/resume', {'id': session_id})
                        self.assertEqual(resumed['requests'][0]['ref'], first)
                        self.assertEqual(resumed['status'], 'running')


                        with self.assertRaises(HTTPError):
                            request('/api/decide', dict(ref=first, choice='approve', quote=''))
                    choice = r['payload']['body']['options'][0]['choice'] if r['payload']['kind'] == 'choice' else 'approve'
                    if r['payload']['kind'] == 'choice':
                        req = Request(base + '/api/image?ref=' + r['ref'] + '&choice=' + choice,
                                      headers={'X-Ember-Token': app.token})
                        with urlopen(req) as image:
                            self.assertTrue(image.read().startswith(b'\x89PNG'))
                    response = dict(ref=r['ref'], choice=choice, quote='SYNTHETIC UI TEST approval only')
                    request('/api/decide', response)
                    with self.assertRaises(HTTPError):
                        request('/api/decide', response)
                    count += 1
                self.assertEqual(state['status'], 'completed', state['log'])
                original.wait(timeout=10)
                self.assertEqual(count, 7)
                reopened = App(root)
                restored = reopened.resume(session_id)
                self.assertEqual(restored['status'], 'completed')
                self.assertEqual(len([r for r in restored['requests'] if r['decision']]), 7)
                self.assertTrue(reopened.verify()['passed'])
                self.assertIn('explicit responses', state['report'])
                verified = request('/api/verify', {})
                self.assertTrue(verified['passed'])
                # Verification refreshes bytes; a changed accepted image must fail.
                manifest = json.loads(app.manifest.read_bytes())
                Path(manifest['asset']['path']).write_bytes(b'changed')
                with self.assertRaises(HTTPError):
                    request('/api/verify', {})
            finally:
                http.shutdown()
                http.server_close()
                worker.join()
                if app.process and app.process.poll() is None:
                    app.process.terminate()
                    app.process.wait(timeout=15)
                if app.stream:
                    app.stream.close()


if __name__ == '__main__':
    unittest.main()
