"""Loopback-only human host for the existing product workflow and owner inbox."""
import argparse
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit, parse_qs

from . import Harness
from .owner_review import load_request, decide
from .recovery import Recovery, exclusive, worker_active, read_json
from .session_chat import transcript, send, activity as chat_activity, MUSE_UNAVAILABLE
from .muse_chat import installed_binary, CreditLedger
from . import chat_build, playtests, project_versions, project_brief, browser_checks, polish, polish_runtime, gameplay


class App:
    def __init__(self, root, binary=None, model='qwen2.5-coder:7b'):
        self.root = Path(root).resolve()
        if not (self.root / 'examples/product_demo.py').is_file():
            raise ValueError('Choose the harness source folder containing examples/product_demo.py')
        self.binary, self.model = binary, model
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.process = None
        self.store = None
        self.log = None
        self.stream = None
        self.manifest = None
        self.start_count = 0
        self.session = None
        self.sessions_dir = self.root / ".harness/ui/sessions"

    def history(self):
        rows = []
        for path in self.sessions_dir.glob('*/session.json'):
            metadata = read_json(path)
            status = self.worker_state(path.parent) if metadata.get('workflow_started', True) else dict(status='idle', exit_code=None)
            rows.append({**metadata, **status})
        return sorted(rows, key=lambda row: row['updated_at'], reverse=True)

    def worker_state(self, folder):
        path = folder / 'worker.json'
        if not path.exists():
            return dict(status='interrupted', exit_code=None)
        data = read_json(path)
        if data['status'] == 'running' and not worker_active(folder):
            # Completion is published before releasing worker.lock. Our first
            # read may have preceded that final write while the lease check
            # followed it; reread before declaring the worker interrupted.
            data = read_json(path)
            if data['status'] == 'running':
                data['status'] = 'interrupted'
        return data

    def save(self, name=None):
        with self.lock:
            if not self.session:
                raise ValueError('Start or open a session first')
            if name is not None:
                if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
                    raise ValueError('Enter a session name of 1–120 characters')
                self.session['name'] = name.strip()
            self.session['updated_at'] = datetime.now(timezone.utc).isoformat()
            folder = self.sessions_dir / self.session['id']
            temp = folder / ('session-' + secrets.token_hex(8) + '.tmp')
            temp.write_text(json.dumps(self.session), encoding='utf-8')
            temp.replace(folder / 'session.json')
            return self.session

    def resume(self, session_id):
        with self.lock:
            if not isinstance(session_id, str) or not re.fullmatch('[0-9a-f]{24}', session_id):
                raise ValueError('Invalid session ID')
            folder = self.sessions_dir / session_id
            metadata = read_json(folder / 'session.json')
            if metadata['id'] != session_id:
                raise ValueError('Session ID mismatch')
            self.session = metadata
            self.session['provider'] = 'muse'
            self.session['local_agent_binary'] = None
            self.save()
            self.log = folder / 'execution.log'
            self.store = self.manifest = None
            self.process = None
            return self.snapshot()

    def start(self, name=None, *, new_session=False, chat_only=False, provider="muse"):
        with self.lock:
            if self.session and self.snapshot()['status'] == 'running' and not new_session:
                raise ValueError('A workflow is already running; open History to switch sessions')
            name = name if name is not None else 'Ember session ' + datetime.now().strftime('%Y-%m-%d %H:%M')
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
                raise ValueError('Enter a session name of 1–120 characters')
            if provider != 'muse':
                raise ValueError('Ember is configured for Muse only')
            session_id = secrets.token_hex(12)
            folder = self.sessions_dir / session_id
            folder.mkdir(parents=True)
            now = datetime.now(timezone.utc).isoformat()
            self.session = dict(id=session_id, name=name.strip(), created_at=now, updated_at=now,
                mode='Muse')
            self.save()
            self.log = folder / 'execution.log'
            self.log.touch()
            self.session['local_agent_binary'] = None
            self.session['local_agent_model'] = self.model
            self.session['recovery_version'] = 1
            self.session['provider'] = provider
            self.session['workflow_started'] = not chat_only
            self.save()
            if not chat_only:
                self.launch(folder)
            self.store = self.manifest = None
            self.start_count += 1

    def chat(self, text, turn_id):
        with self.lock:
            if not self.session:
                raise ValueError('Create or select a session first')
            session = dict(self.session)
            folder = self.sessions_dir / session['id']
        messages = send(folder, text, turn_id, 'muse', root=self.root)
        return dict(messages=messages)

    def save_brief(self, session_id, fields, revision):
        with self.lock:
            if not self.session or session_id != self.session['id']:
                raise ValueError('Reopen the intended session before saving its brief')
            return project_brief.save(self.sessions_dir / session_id, fields, revision)

    def save_gameplay(self, session_id, plan, revision):
        with self.lock:
            if not self.session or session_id != self.session['id']:
                raise ValueError('Reopen the intended session before saving its gameplay plan')
            return gameplay.save(self.sessions_dir / session_id, plan, revision)

    def run_gameplay(self, session_id, revision, request_ref, report_id):
        with self.lock:
            if not self.session or session_id != self.session['id']:
                raise ValueError('Reopen the intended session before running gameplay checks')
            folder = self.sessions_dir / session_id
        return gameplay.run_current(self.root, folder, revision, request_ref, report_id)

    def choose_model(self, provider):
        with self.lock:
            if provider != 'muse':
                raise ValueError('Ember is configured for Muse only')
            if not self.session:
                raise ValueError('Create or select a session first')
            self.session['provider'] = provider
            return self.save()

    def begin_workflow(self):
        with self.lock:
            if not self.session or self.session.get('workflow_started', True):
                raise ValueError('Create a new session for a new workflow')
            self.session['workflow_started'] = True
            self.save()
            self.launch(self.sessions_dir / self.session['id'])
            return self.snapshot()

    def launch(self, folder):
        args = [sys.executable, '-u', str(self.root / 'examples/product_demo.py'), '--checkpoint-dir', str(folder)]
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        for key in ('PYTHONOPTIMIZE', 'PYTHONPATH', 'PYTHONHOME'):
            env.pop(key, None)
        self.process = subprocess.Popen([sys.executable, '-m', 'ember_harness.session_worker', str(folder), *args],
            cwd=self.root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            start_new_session=os.name != 'nt')
        # Give the worker its first heartbeat before returning a running snapshot.
        for _ in range(100):
            if ((folder / 'worker.json').exists() and read_json(folder / 'worker.json').get('pid') == self.process.pid) or self.process.poll() is not None:
                break
            time.sleep(.02)

    def recover(self):
        with self.lock:
            if not self.session:
                raise ValueError('Open a saved session first')
            folder = self.sessions_dir / self.session['id']
            with exclusive(folder / 'launch.lock'):
                if worker_active(folder):
                    return self.snapshot()
                state = self.snapshot()
                if not state['recovery_available']:
                    raise ValueError('No resumable checkpoint for this session')
                journal = Recovery(folder, self.root)
                journal.check_ready()
                self.launch(folder)
                self.save()
                return self.snapshot()

    def snapshot(self):
        with self.lock:
            log = self.log.read_text(encoding='utf-8', errors='replace') if self.log else ''
            # Only a structured waiting message from our own child may register a store.
            for line in log.splitlines():
                try:
                    msg = json.loads(line)
                    if msg.get('status') == 'awaiting_owner':
                        store = Path(msg['store']).resolve()
                        if not store.is_relative_to(self.root / '.harness/demos'):
                            raise ValueError('Workflow store outside demo directory')
                        self.store = store
                except (json.JSONDecodeError, AttributeError):
                    continue
            worker = self.worker_state(self.sessions_dir / self.session['id']) if self.session else dict(status='idle', exit_code=None)
            if self.session and not self.session.get('workflow_started', True):
                worker = dict(status='idle', exit_code=None)
            code = worker['exit_code']
            result = dict(status=worker['status'], session=self.session,
                exit_code=code, log=log[-40000:], requests=[], audit=[], report=None,
                recovery_available=False, recovery_step=None, messages=[],
                models=dict(local=False, muse=bool(installed_binary()), muse_reason=MUSE_UNAVAILABLE),
                credit_budget=CreditLedger(self.root).summary(),
                mode=self.session['mode'] if self.session else 'Deterministic demonstration', store=str(self.store or ''))
            if self.store:
                h = Harness(self.store)
                entries = h._entries()
                result['audit'] = entries[-100:]
                decisions = {e['request_ref']: e for e in entries if e['kind'] == 'owner_decision'}
                for event in entries:
                    if event['kind'] == 'owner_request':
                        ref = event['request_ref']
                        payload = load_request(h, ref)
                        result['requests'].append(dict(ref=ref, payload=payload, decision=decisions.get(ref)))
                path = self.store.parent.parent / 'product.json'
                if path.is_file() and (path.parent / 'PRODUCT_DEMO.md').is_file():
                    self.manifest = path
                    result['report'] = (path.parent / 'PRODUCT_DEMO.md').read_text(encoding='utf-8')
            if self.session:
                session_folder = self.sessions_dir / self.session['id']
                result['project_brief'] = project_brief.load(session_folder)
                result['gameplay_plan'] = gameplay.load(session_folder)
                result['messages'] = transcript(session_folder)
                result['chat_activity'] = chat_activity(session_folder)
                result['build'] = chat_build.status(self.root, session_folder)
                result['build']['playtests'] = playtests.reports(session_folder)
                result['build']['versions'] = project_versions.history(session_folder)
                result['build']['smoke_checks'] = browser_checks.reports(session_folder)
                result['build']['gameplay_checks'] = gameplay.reports(session_folder)
                result['polish_runs'] = polish.history(self.root, session_folder)
                try:
                    polish_runtime.discover(self.root, fingerprints=False)
                    result['polish_available'] = dict(ready=True, reason='Browser tooling is ready')
                except ValueError as error:
                    result['polish_available'] = dict(ready=False, reason=str(error))
                result['requests'].extend(result['build']['requests'])
                checkpoint = session_folder / 'recovery.json'
                declined = any(r['decision'] and r['decision']['choice'] == 'decline' for r in result['requests'])
                result['recovery_available'] = checkpoint.is_file() and result['status'] in ('interrupted', 'stopped') and not declined
                if checkpoint.is_file():
                    try:
                        result['recovery_step'] = read_json(checkpoint)['payload'].get('current_step')
                    except (ValueError, KeyError):
                        result['recovery_error'] = 'Recovery journal is damaged; saved conversation remains available'
            return result

    def respond(self, ref, choice, quote):
        with self.lock:
            state = self.snapshot()
            if self.session and any(r['ref'] == ref for r in state.get('build', {}).get('requests', [])):
                return chat_build.respond(self.root, self.sessions_dir / self.session['id'], ref, choice, quote)
            if state['status'] != 'running' or not self.store:
                raise ValueError('No running workflow awaiting an owner response')
            return decide(Harness(self.store), ref, choice, quote)

    def resume_build(self, ref):
        with self.lock:
            if not self.session:
                raise ValueError('Select a session first')
            return chat_build.resume(self.root, self.sessions_dir / self.session['id'], ref)

    def request_changes(self, ref, note, turn_id):
        """One human gesture discards an exact proposal and requests a replacement."""
        if not isinstance(note, str) or not note.strip() or len(note) > 2000:
            raise ValueError('Describe the changes you want in at most 2000 characters')
        if not isinstance(turn_id, str) or not re.fullmatch('[a-zA-Z0-9-]{16,64}', turn_id):
            raise ValueError('A stable message ID is required')
        with self.lock:
            if not self.session:
                raise ValueError('Select a session first')
            folder = self.sessions_dir / self.session['id']
            request = next((r for r in chat_build.list_requests(folder) if r['ref'] == ref), None)
            if request is None:
                raise ValueError('Select a pending build proposal')
            quote = 'Request changes: ' + note.strip()
            if request['decision']:
                if request['decision']['choice'] != 'decline' or request['decision']['quote'] != quote:
                    raise ValueError('This proposal already has a different decision')
            else:
                chat_build.respond(self.root, folder, ref, 'decline', quote)
            text = ('Revise the proposed build "' + request['payload']['body']['build']['title'] +
                    '" with these changes:\n' + note.strip())
        # Keep this bound to its original session while allowing UI polling during inference.
        return dict(messages=send(folder, text, turn_id, 'muse', root=self.root))

    def build_preview(self, diagnostics=False):
        with self.lock:
            if not self.session:
                raise ValueError('Select a session first')
            folder = self.sessions_dir / self.session['id']
            return playtests.preview(self.root, folder) if diagnostics else dict(html=chat_build.preview(self.root, folder))

    def record_playtest(self, **body):
        with self.lock:
            if not self.session:
                raise ValueError('Select a session first')
            return playtests.record(self.root, self.sessions_dir / self.session['id'], **body)

    def proposal_preview(self, session_id, ref):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before previewing its proposal')
            return chat_build.proposal_preview(self.root, self.sessions_dir / session_id, ref)

    def version_preview(self, ref):
        with self.lock:
            if not self.session:
                raise ValueError('Select a session first')
            return project_versions.preview(self.root, self.sessions_dir / self.session['id'], ref)

    def export_version(self, ref):
        with self.lock:
            if not self.session:
                raise ValueError('Select a session first')
            return project_versions.export(self.root, self.sessions_dir / self.session['id'], ref)

    def restore_version(self, session_id, ref, current_ref, request_id):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before restoring a version')
            proposal = project_versions.propose_restore(self.root, self.sessions_dir / session_id,
                                                        ref, current_ref, request_id)
            return dict(request_ref=proposal)

    def smoke_preview(self, session_id):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before running browser checks')
            return browser_checks.preview(self.root, self.sessions_dir / session_id)

    def record_smoke(self, session_id, **body):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before recording browser checks')
            return browser_checks.record(self.root, self.sessions_dir / session_id, **body)

    def image(self, ref, choice=None):
        with self.lock:
            if not self.store:
                raise ValueError('No active review')
            body = load_request(Harness(self.store), ref)['body']
            if 'options' in body:
                item = next(v for v in body['options'] if v['choice'] == choice)
                path, expected = Path(item['path']), item['sha256']
            else:
                action = body['action']
                if action['tool'] != 'asset.accept':
                    raise ValueError('This review has no image')
                path = Path(action['args']['path'])
                # Acceptance bytes are validated again by the existing gate.
                expected = None
            if not path.resolve().is_relative_to(self.store.parent.resolve()) or path.suffix.lower() != '.png':
                raise ValueError('Image outside current workflow')
            data = path.read_bytes()
            if len(data) > 10 * 1024 * 1024 or (expected and sha256(data).hexdigest() != expected):
                raise ValueError('Image changed or too large')
            return data

    def polish_control(self, session_id, action, **body):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before changing a polish run')
            folder = self.sessions_dir / session_id
            if action == 'prepare':
                return polish.prepare(self.root, folder, **body)
            if action == 'decide':
                return polish.respond(self.root, folder, **body)
            if action == 'resume':
                return polish.launch(self.root, folder, body['run_id'])
            if action == 'stop':
                return polish.stop(self.root, folder, body['run_id'])
            if action == 'promote':
                return polish.promote(self.root, folder, body['run_id'], body['index'])
            raise ValueError('Unknown polish action')

    def polish_preview(self, session_id, run_id, index, image_name=None):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before viewing a polish run')
            folder = self.sessions_dir / session_id
            if image_name is not None:
                return polish.image(folder, run_id, index, image_name)
            return polish.preview(folder, run_id, index)

    def verify(self):
        with self.lock:
            state = self.snapshot()
            if not self.manifest and state.get('build', {}).get('completed'):
                return chat_build.verify(self.root, self.sessions_dir / self.session['id'])
            if not self.manifest or state['status'] != 'completed':
                raise ValueError('Complete the workflow before verification')
            from examples.product_demo import verify_product
            return verify_product(json.loads(self.manifest.read_bytes()))


def server(app, port=0):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, data, mime='application/json', download=None):
            raw = json.dumps(data).encode() if mime == 'application/json' else data
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if download:
                self.send_header('Content-Disposition', 'attachment; filename="' + download + '"')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline' data:; style-src 'self' 'unsafe-inline' data:; img-src 'self' data: blob:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self):
            host = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != host:
                return False
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + host:
                return False
            return secrets.compare_digest(self.headers.get('X-Ember-Token', ''), app.token)

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == '/favicon.ico':
                return self.reply(200, b'', 'image/x-icon')
            if url.path == '/':
                if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                    return self.reply(403, {'error': 'Invalid host'})
                return self.reply(200, (Path(__file__).parent / 'ui.html').read_bytes(), 'text/html; charset=utf-8')
            if not self.authorized():
                return self.reply(403, {'error': 'Open the app using its private launch link'})
            try:
                if url.path == '/api/sessions':
                    return self.reply(200, app.history())
                if url.path == '/api/state':
                    return self.reply(200, app.snapshot())
                if url.path == '/api/build-preview':
                    return self.reply(200, app.build_preview(diagnostics=True))
                if url.path == '/api/proposal-preview':
                    q = parse_qs(url.query)
                    return self.reply(200, app.proposal_preview(q['session_id'][0], q['ref'][0]))
                if url.path == '/api/version-preview':
                    q = parse_qs(url.query)
                    return self.reply(200, app.version_preview(q['ref'][0]))
                if url.path == '/api/smoke-preview':
                    q = parse_qs(url.query)
                    return self.reply(200, app.smoke_preview(q['session_id'][0]))
                if url.path in ('/api/polish-preview', '/api/polish-image'):
                    q = parse_qs(url.query)
                    result = app.polish_preview(q['session_id'][0], q['run_id'][0], int(q['index'][0]),
                        q['name'][0] if url.path == '/api/polish-image' else None)
                    return self.reply(200, result, 'image/png' if url.path == '/api/polish-image' else 'application/json')
                if url.path == '/api/export-version':
                    q = parse_qs(url.query)
                    data, filename = app.export_version(q['ref'][0])
                    return self.reply(200, data, 'application/zip', download=filename)
                if url.path == '/api/image':
                    q = parse_qs(url.query)
                    return self.reply(200, app.image(q['ref'][0], q.get('choice', [None])[0]), 'image/png')
                self.reply(404, {'error': 'Unknown route'})
            except Exception as error:
                self.reply(400, {'error': str(error)})

        def do_POST(self):
            if not self.authorized() or self.headers.get('Content-Type') != 'application/json':
                return self.reply(403, {'error': 'Local app authorization required'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= (64000 if self.path in ('/api/project-brief', '/api/gameplay-plan') else 16000):
                    raise ValueError('Invalid request size')
                body = json.loads(self.rfile.read(size))
                if self.path == '/api/start':
                    app.start(body.get('name'), new_session=body.get('new_session') is True,
                              chat_only=body.get('chat_only') is True, provider=body.get('provider', 'muse'))
                    result = {'status': 'started'}
                elif self.path == '/api/chat':
                    result = app.chat(body['text'], body['id'])
                elif self.path == '/api/build-resume':
                    result = app.resume_build(body['ref'])
                elif self.path == '/api/request-changes':
                    result = app.request_changes(body['ref'], body['note'], body['id'])
                elif self.path == '/api/playtest':
                    result = app.record_playtest(**body)
                elif self.path == '/api/smoke-check':
                    result = app.record_smoke(**body)
                elif self.path == '/api/restore-version':
                    result = app.restore_version(body['session_id'], body['ref'], body['current_ref'], body['id'])
                elif self.path == '/api/polish':
                    result = app.polish_control(**body)
                elif self.path == '/api/project-brief':
                    result = app.save_brief(body['session_id'], body['fields'], body['revision'])
                elif self.path == '/api/gameplay-plan':
                    result = app.save_gameplay(body['session_id'], body['plan'], body['revision'])
                elif self.path == '/api/gameplay-run':
                    result = app.run_gameplay(body['session_id'], body['revision'], body['request_ref'], body['report_id'])
                elif self.path == '/api/model':
                    result = app.choose_model(body['provider'])
                elif self.path == '/api/workflow':
                    result = app.begin_workflow()
                elif self.path == '/api/recover':
                    result = app.recover()
                elif self.path == '/api/save':
                    result = app.save(body.get('name'))
                elif self.path == '/api/resume':
                    result = app.resume(body['id'])
                elif self.path == '/api/decide':
                    result = app.respond(body['ref'], body['choice'], body['quote'])
                elif self.path == '/api/verify':
                    result = app.verify()
                else:
                    return self.reply(404, {'error': 'Unknown route'})
                self.reply(200, result)
            except Exception as error:
                self.reply(400, {'error': str(error)})
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=str(Path.cwd()))
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--local-agent-binary')
    parser.add_argument('--local-agent-model', default='qwen2.5-coder:7b')
    args = parser.parse_args()
    app = App(args.root, args.local_agent_binary, args.local_agent_model)
    http = server(app, args.port)
    print(f'Ember app: http://127.0.0.1:{http.server_port}/#{app.token}', flush=True)
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        http.server_close()
        # Session workers survive launcher shutdown so a new launcher can reconnect.
        if app.session:
            app.save()
        if app.stream:
            app.stream.close()


if __name__ == '__main__':
    main()
