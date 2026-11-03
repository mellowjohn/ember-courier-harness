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
from . import chat_build, playtests, project_versions, project_brief, browser_checks, polish, polish_runtime, gameplay, asset_library, project_locations, project_plan
from . import task_run, task_coverage, asset_run, findings, workspace, project_handoff
from . import mechanic_workflow
from . import git_task, git_automation
from . import muse_image, asset_2d
from . import proposal_quality


class App:
    def __init__(self, root, binary=None, model='qwen2.5-coder:7b'):
        self.root = Path(root).resolve()
        if not (self.root / 'examples/product_demo.py').is_file():
            raise ValueError('Choose the harness source folder containing examples/product_demo.py')
        self.binary, self.model = binary, model
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.picker_lock = threading.Lock()
        self.process = None
        self.store = None
        self.log = None
        self.stream = None
        self.manifest = None
        self.start_count = 0
        self.session = None
        self.assets_discovered = False
        self.sessions_dir = self.root / ".harness/ui/sessions"

    def history(self):
        rows = []
        for path in self.sessions_dir.glob('*/session.json'):
            metadata = read_json(path)
            status = self.worker_state(path.parent) if metadata.get('workflow_started', True) else dict(status='idle', exit_code=None)
            rows.append({**metadata, **status, 'project': str(chat_build.project(self.root, path.parent))})
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

    def start(self, name=None, *, new_session=False, chat_only=False, provider="muse", project_parent=None):
        with self.lock:
            if self.session and self.snapshot()['status'] == 'running' and not new_session:
                raise ValueError('A workflow is already running; open History to switch sessions')
            name = name if name is not None else 'Ember session ' + datetime.now().strftime('%Y-%m-%d %H:%M')
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
                raise ValueError('Enter a session name of 1–120 characters')
            if provider != 'muse':
                raise ValueError('Ember is configured for Muse only')
            parent = project_locations.parent_folder(self.root, project_parent)
            session_id = secrets.token_hex(12)
            folder = self.sessions_dir / session_id
            folder.mkdir(parents=True)
            project_locations.assign(self.root, folder, name.strip(), str(parent))
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
            project_locations.remember(self.root, parent)

    def pick_project_parent(self, parent=None):
        # Only the explicit, authenticated picker button opens a native dialog.
        try:
            initial = project_locations.checked_path(parent or project_locations.default_parent(self.root))
        except ValueError:
            initial = self.root
        if not self.picker_lock.acquire(blocking=False):
            raise ValueError('A folder picker is already open')
        try:
            chosen = project_locations.pick(initial)
        finally:
            self.picker_lock.release()
        return dict(path=str(project_locations.parent_folder(self.root, chosen)) if chosen else None)

    def copy_project(self, session_id, current_ref, name, project_parent):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before saving a project copy')
            source = self.sessions_dir / session_id
            with exclusive(source / 'chat.lock'), exclusive(source / 'build.lock'):
                state = chat_build.status(self.root, source)
                if state['resumable'] or not state['completed'] or state['completed'][-1]['request_ref'] != current_ref:
                    raise ValueError('Choose the latest completed build before saving a copy')
                saved = project_versions.snapshot(self.root, source, current_ref)
                brief, plan = project_brief.load(source), gameplay.load(source)
                self.start(name, new_session=True, chat_only=True, project_parent=project_parent)
                target = self.sessions_dir / self.session['id']
                if brief['revision']:
                    project_brief.save(target, brief['fields'], 0)
                if plan['revision']:
                    gameplay.save(target, plan['plan'], 0)
                ref = chat_build.propose_build(self.root, target, 'save-copy-' + self.session['id'],
                    'Save the latest approved project in the chosen folder',
                    dict(title='Save project copy · ' + self.session['name'],
                         summary='Copy the latest approved files from ' + source.name + '. Review before saving to the new folder.',
                         files=[dict(path=k, content=v) for k,v in saved['files'].items()]))
                return dict(session_id=self.session['id'], request_ref=ref, project=str(chat_build.project(self.root, target)))

    def chat(self, text, turn_id):
        with self.lock:
            if not self.session:
                raise ValueError('Create or select a session first')
            session = dict(self.session)
            folder = self.sessions_dir / session['id']
        messages = send(folder, text, turn_id, 'muse', root=self.root)
        return dict(messages=messages)

    def start_plan_build(self, session_id, plan_ref):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before starting its build')
            folder = self.sessions_dir / session_id
            plan = project_plan.status(self.root, folder)
            if not plan['active'] or plan['approved']['ref'] != plan_ref:
                raise ValueError('Reopen the active approved project plan before starting its build')
            turn_id = 'plan-build-' + plan_ref[:40]
            previous = next((m for m in transcript(folder) if m['id'] == turn_id), None)
            task = next(t for t in plan['tasks'] if t['id'] == plan['selected_task'])
            start = previous['plan_start'] if previous else dict(plan_ref=plan_ref, task_id=task['id'], title=task['title'])
            text = previous['text'] if previous else (
                'My project plan is approved. Start implementing its selected task: ' + task['title'] +
                '. Prepare the build for review using the approved design and art direction. Do not restart planning.')
        # Use the ordinary saved, metered chat/build path, outside the UI lock.
        return dict(messages=send(folder, text, turn_id, 'muse', root=self.root, plan_start=start))

    def review_asset_update(self, session_id, asset_ref, current_ref):
        from .asset_workshop import review_updated_export
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before reviewing its asset update')
            return review_updated_export(self.root, self.sessions_dir / session_id, asset_ref, current_ref)

    def save_brief(self, session_id, fields, revision):
        with self.lock:
            if not self.session or session_id != self.session['id']:
                raise ValueError('Reopen the intended session before saving its brief')
            return project_brief.save(self.sessions_dir / session_id, fields, revision)

    def workspace_control(self, session_id, action, **body):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before reviewing a workspace')
            folder = self.sessions_dir / session_id
            if action == 'scan':
                return workspace.prepare(folder, body['source'])
            if action in ('plan', 'apply', 'import_plan', 'import_apply'):
                return workspace.prepare(folder, stage=action, run_id=body['run_id'])
            if action == 'promote_import':
                with exclusive(folder / 'chat.lock'), exclusive(folder / 'build.lock'):
                    frozen = project_plan.context(self.root, folder)
                    if not frozen:
                        raise ValueError('Approve a project plan before reviewing imported game changes')
                    files = workspace.imported_files(folder, body['run_id'])
                    current = chat_build.context(self.root, folder)
                    if current['manifest'] != body['expected_manifest']:
                        raise ValueError('The current game changed; review the import again')
                    operation = body.get('operation_id', '')
                    if operation and (not isinstance(operation, str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,80}', operation)):
                        raise ValueError('Use a fresh import review request')
                    identity = sha256(json.dumps(dict(manifest=current['manifest'], binding=frozen['binding'], operation=operation), sort_keys=True).encode()).hexdigest()[:16]
                    turn_id = 'import-' + body['run_id'] + '-' + identity
                    prior = next((row for row in chat_build.list_requests(folder) if row['payload']['body']['build']['turn_id'] == turn_id), None)
                    if prior and prior['decision']:
                        raise ValueError('This import review was already decided. Use Review imported game changes again to prepare a fresh review.')
                    ref = chat_build.propose_build(self.root, folder, turn_id, 'Review imported browser game',
                        dict(title='Imported browser game', summary='Review the isolated imported source as exact game changes; original workspace stays unchanged.',
                            files=[dict(path=name, content=content) for name, content in files.items()]),
                        expected_before=current['sha256'], project_scope=frozen['binding'])
                    return dict(request_ref=ref)
            if action == 'resume':
                return workspace.respond(folder, body['ref'], 'approve', 'Resume the previously approved workspace step')
            raise ValueError('Unknown workspace action')

    def mechanic_control(self, session_id, action, **body):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before preparing mechanic work')
            folder = self.sessions_dir / session_id
            if action == 'checks':
                context = chat_build.context(self.root, folder)
                if not context.get('mechanics'):
                    raise ValueError('Reference gameplay checks require the supported platformer')
                return mechanic_workflow.save_checks(folder, body['revision'], context['mechanics']['profile'])
            return mechanic_workflow.prepare(self.root, folder, action=action, **body)

    def git_control(self, session_id, action, **body):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before reviewing Git work')
            folder = self.sessions_dir / session_id
            if action == 'prepare-automated':
                return git_automation.prepare(self.root, folder, finding=body.get('finding'))
            if action == 'advance-automated':
                return git_automation.advance(self.root, folder, body['task_run_id'])
            if action == 'prepare-proposal':
                with exclusive(folder / 'build.lock'):
                    current = chat_build.context(self.root, folder)
                    if current['manifest'] != body['expected_manifest']:
                        raise ValueError('The current game changed; review the proposal again')
                    candidate = chat_build.proposal_snapshot(self.root, folder, body['request_ref'])
                    request = next(row for row in chat_build.list_requests(folder) if row['ref'] == body['request_ref'])
                    binding = project_plan.context(self.root, folder)
                    if not binding or request['payload']['body']['build'].get('project_scope') != binding['binding']:
                        raise ValueError('Choose a proposal for the selected task under the active project plan')
                return git_task.prepare(self.root, folder, candidate_files=candidate['files'],
                    expected_manifest=current['manifest'], origin=dict(proposal_ref=body['request_ref']),
                    goal=candidate['title'])
            if action == 'prepare':
                current = chat_build.context(self.root, folder)
                if current['manifest'] != body['expected_manifest']:
                    raise ValueError('The current game changed; review the edit again')
                base = {row['path']: row['content'] for row in current['files']}
                build = chat_build.materialize_build(dict(title='Local Git repair', summary=body['goal'], edits=[
                    dict(path=body['path'], before=body['before'], after=body['after'])]), base)
                return git_task.prepare(self.root, folder, candidate_files={row['path']: row['content'] for row in build['files']},
                    expected_manifest=current['manifest'], goal=body['goal'])
            if action in ('start', 'resume'):
                return git_task.launch(self.root, folder, body['run_id'])
            if action == 'stop':
                return git_task.stop(self.root, folder, body['run_id'])
            if action == 'promote':
                return git_task.promote(self.root, folder, body['run_id'])
            if action == 'escalate':
                _, h, _, plan = git_task.load(folder, body['run_id'])
                from .attempts import TaskAttempts, Attempts
                if (plan.get('origin') or {}).get('task_run_id'):
                    _, _, _, source_plan = git_automation.audited_source(folder, plan['origin'])
                    if source_plan.get('kind') == 'finding':
                        return Attempts(h).decide(source_plan['finding']['bug']['id'], choice=body['choice'],
                            expected_state_hash=body['state_hash'], approver='johnathan',
                            quote='Owner chose ' + body['choice'] + ' after reviewing the blocked Git finding attempts')
                return TaskAttempts(h, plan['task_identity']).decide(body['choice'], body['state_hash'],
                    'Owner chose ' + body['choice'] + ' after reviewing the blocked Git task attempts')
            raise ValueError('Unknown Git workflow action')

    def git_preview(self, session_id, run_id, stage=None, image_name=None):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before inspecting Git evidence')
            folder = self.sessions_dir / session_id
            if image_name is not None:
                return git_task.image(folder, run_id, stage, image_name)
            return git_task.preview(folder, run_id)

    def plan_control(self, session_id, action, **body):
        with self.lock:
            if not self.session or session_id != self.session['id']:
                raise ValueError('Reopen the intended session before changing its project plan')
            folder = self.sessions_dir / session_id
            if action == 'prepare':
                return project_plan.prepare(self.root, folder, body['document'], body.get('expected_ref'))
            if action == 'acknowledge':
                return project_plan.acknowledge(self.root, folder, body['ref'], 'Acknowledge the reviewed scope changes')
            if action in ('select', 'accept'):
                result = project_plan.task_action(self.root, folder, body['plan_ref'], body['task_id'], action, body.get('build_ref'))
                if action == 'accept' and result.get('next_task_id'):
                    continuation = dict(plan_ref=body['plan_ref'], completed_task_id=body['task_id'],
                        next_task_id=result['next_task_id'])
                    try:
                        run = task_run.prepare(self.root, folder)
                        continuation.update(status='awaiting_approval', run_id=run['id'],
                            reason='Next task is ready. Review and approve its run to start the agents.')
                    except (ValueError, OSError) as error:
                        continuation.update(status='blocked', reason=str(error))
                    h = project_plan.authority(folder)
                    with h._lock():
                        h._append('project_task_continuation', **continuation)
                    result['continuation'] = continuation
                return result
            raise ValueError('Unknown project plan action')

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

    def check_proposal(self, session_id, revision, request_ref, report_id):
        with self.lock:
            if not self.session or session_id != self.session['id']:
                raise ValueError('Reopen the intended session before checking its proposal')
            folder = self.sessions_dir / session_id
        return gameplay.run_proposal(self.root, folder, revision, request_ref, report_id)

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
                image_generation=muse_image.status(self.root),
                credit_budget=CreditLedger(self.root).summary(),
                project_settings=dict(parent=project_locations.default_parent(self.root)),
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
                result['project_plan'] = project_plan.status(self.root, session_folder)
                result['workspace'] = workspace.status(session_folder)
                result['task_runs'] = task_run.history(self.root, session_folder)
                result['git_runs'] = git_task.history(self.root, session_folder)
                result['git_automation'] = git_automation.history(self.root, session_folder, tasks=result['task_runs'])
                result['findings'] = findings.history(self.root, session_folder)
                result['finding_requests'] = findings.requests(session_folder)
                result['gameplay_plan'] = gameplay.load(session_folder)
                selected = next((task for task in result['project_plan'].get('tasks', [])
                    if task['id'] == result['project_plan'].get('selected_task')), None)
                if selected:
                    result['coverage_review'] = task_coverage.analyze(selected['title'],
                        result['project_brief'], result['gameplay_plan'])
                result['messages'] = transcript(session_folder)
                result['chat_activity'] = chat_activity(session_folder)
                result['build'] = chat_build.status(self.root, session_folder)
                if not self.assets_discovered:
                    asset_library.discover(self.root); self.assets_discovered = True
                result['asset_library'] = asset_library.context(self.root, session_folder, result['messages'])
                from .sprite_project import context as sprite_context
                sprite_issue=None
                try:
                    project_files={f['path']:f['content'] for f in chat_build.context(self.root,session_folder)['files']}
                except (ValueError,OSError,UnicodeError) as error:
                    # Recovery and historical version inspection must remain available
                    # while a write is incomplete or the current game was modified.
                    project_files={};sprite_issue=str(error)
                try:
                    result['sprite_project']=sprite_context(self.root,session_folder,project_files)
                except (ValueError,OSError,UnicodeError) as error:
                    result['sprite_project']=dict(revision=None,plan=None,applied_plan=None,inventory=[])
                    sprite_issue=str(error)
                if sprite_issue:result['sprite_project']['inspection_required']=sprite_issue
                result['mechanics'] = mechanic_workflow.status(project_files)
                result['project_file_names'] = sorted(project_files)
                if sprite_issue:
                    result['mechanics'].update(supported=False, can_prepare_sample=False, reason=sprite_issue)
                result['build']['playtests'] = playtests.reports(session_folder)
                result['build']['versions'] = project_versions.history(session_folder)
                result['build']['smoke_checks'] = browser_checks.reports(session_folder)
                result['build']['gameplay_checks'] = gameplay.reports(session_folder)
                result['build']['proposal_check'] = gameplay.proposal_status(self.root, session_folder)
                result['build']['quality_check'] = proposal_quality.status(self.root, session_folder)
                result['polish_runs'] = polish.history(self.root, session_folder)
                try:
                    polish_runtime.discover(self.root, fingerprints=False)
                    result['polish_available'] = dict(ready=True, reason='Browser tooling is ready')
                except ValueError as error:
                    result['polish_available'] = dict(ready=False, reason=str(error))
                result['requests'].extend(result['build']['requests'])
                result['requests'].extend(project_plan.requests(session_folder))
                result['requests'].extend(result['workspace']['requests'])
                result['requests'].extend(git_task.requests(session_folder))
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
            if self.session:
                folder = self.sessions_dir / self.session['id']
                request = next((row for row in git_task.requests(folder) if row['ref'] == ref), None)
                if request:
                    run_id = request['payload']['body']['git_task']['id']
                    result = git_task.respond(self.root, folder, run_id, choice, quote)
                    return git_task.launch(self.root, folder, run_id) if choice == 'approve' and result['status'] in ('ready', 'interrupted') else result
            if self.session and any(r['ref'] == ref for r in workspace.requests(self.sessions_dir / self.session['id'])):
                return workspace.respond(self.sessions_dir / self.session['id'], ref, choice, quote)
            if self.session and any(r['ref'] == ref for r in project_plan.requests(self.sessions_dir / self.session['id'])):
                return project_plan.respond(self.root, self.sessions_dir / self.session['id'], ref, choice, quote)
            if self.session and any(r['ref'] == ref for r in findings.requests(self.sessions_dir / self.session['id'])):
                return findings.respond(self.root, self.sessions_dir / self.session['id'], ref, choice, quote)
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

    def verify_image_credits(self, session_id, balance_usd, no_paid_fallback):
        from decimal import Decimal
        with self.lock:
            if not self.session or session_id != self.session['id']:
                raise ValueError('Select the intended session before verifying image credits')
            if not isinstance(balance_usd, str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,6})?', balance_usd):
                raise ValueError('Enter the promotional balance shown in Meta billing')
            balance = int(Decimal(balance_usd) * 1_000_000)
            return muse_image.verify_coverage(self.root, balance, no_paid_fallback=no_paid_fallback)

    def generate_saved_image(self, session_id, turn_id):
        with self.lock:
            if not self.session or session_id != self.session['id']:
                raise ValueError('Select the intended artwork session')
            folder = self.sessions_dir / session_id
        from .session_chat import generate_saved_image
        return generate_saved_image(self.root, folder, turn_id)

    def generated_image_preview(self, session_id, turn_id, ref):
        with self.lock:
            if not self.session or session_id != self.session['id']:
                raise ValueError('Select the intended artwork session')
            messages = transcript(self.sessions_dir / session_id)
            if not any(m.get('reply_to') == turn_id and ((m.get('image_generation') or {}).get('asset_ref') == ref or
                    any(i['generation'].get('asset_ref') == ref for i in (m.get('image_batch') or {}).get('items', [])) or
                    any(g.get('asset_ref')==ref for g in (m.get('sprite_project') or {}).get('generated',[]))) for m in messages):
                raise ValueError('Choose generated artwork recorded in this session')
            record, spec, _ = asset_library.load(self.root, ref)
            if spec.get('profile') != 'sprite-atlas-v1':
                raise ValueError('Choose a generated PNG asset')
            return asset_2d.unpack(record['package'])[0]

    def asset_image_preview(self, session_id, ref):
        """Preview verified PNG snapshots, including reused and historical artwork."""
        with self.lock:
            if not self.session or session_id != self.session['id']:
                raise ValueError('Select the intended artwork session')
            folder = self.sessions_dir / session_id
            messages = transcript(folder)
            known = {a['ref'] for a in asset_library.context(self.root, folder, messages)['assets']}
            from .sprite_project import load_draft
            plans = [load_draft(folder)['plan']]
            for message in messages:
                known.add(message.get('asset_ref'))
                plans.append((message.get('sprite_project') or {}).get('plan'))
                known.add((message.get('image_generation') or {}).get('asset_ref'))
                known.update(i['generation'].get('asset_ref') for i in (message.get('image_batch') or {}).get('items', []))
            known.update(e['asset_ref'] for plan in plans if plan for e in plan['entities'] if e['asset_ref'])
            if ref not in known:
                raise ValueError('Choose artwork recorded in this session or its known assets')
            record, spec, _ = asset_library.load(self.root, ref)
            if spec.get('profile') != 'sprite-atlas-v1':
                raise ValueError('Choose a PNG asset')
            return asset_2d.unpack(record['package'])[0]

    def quality_image_preview(self, session_id, ref, name):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Select the intended game session')
            return proposal_quality.image(self.root,self.sessions_dir/session_id,ref,name)

    def request_changes(self, ref, note, turn_id, gameplay_report_id=None):
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
            text = ('Revise the proposed build "' + request['payload']['body']['build']['title'] +
                    '" with these changes:\n' + note.strip())
            previous = next((m for m in transcript(folder) if m['id'] == turn_id), None)
            if previous and (previous['text'] != text or previous['provider'] != 'muse'):
                raise ValueError('Message ID already belongs to another prompt')
            revision = None
            if gameplay_report_id is not None:
                if previous:
                    revision = previous.get('proposal_context')
                    if not revision or revision['report_id'] != gameplay_report_id or revision['request_ref'] != ref:
                        raise ValueError('Message ID already belongs to another proposal report')
                else:
                    revision = gameplay.revision_context(self.root, folder, ref, gameplay_report_id,
                                                         allow_declined=bool(request['decision']))
            elif previous:
                revision = previous.get('proposal_context')
            else:
                revision = proposal_quality.revision_context(self.root,folder,ref,allow_declined=bool(request['decision']))
            quote = 'Request changes: ' + note.strip()
            if request['decision']:
                if request['decision']['choice'] != 'decline' or request['decision']['quote'] != quote:
                    raise ValueError('This proposal already has a different decision')
            else:
                chat_build.respond(self.root, folder, ref, 'decline', quote)
        # Keep this bound to its original session while allowing UI polling during inference.
        return dict(messages=send(folder, text, turn_id, 'muse', root=self.root, proposal_context=revision))

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

    def fix_playtest(self, session_id, report_id, *, request_ref=None, note=None, observations=None):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before fixing its playtest')
            folder = self.sessions_dir / session_id
            if note is not None:
                playtests.record(self.root, folder, report_id, request_ref, 'problem', note, [] if observations is None else observations)
        # Inference must not hold the app lock: progress remains readable and a
        # session switch cannot redirect this request into a different project.
        return playtests.request_fix(self.root, folder, report_id)

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

    def export_handoff(self, session_id, ref):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before downloading its handoff')
            return project_handoff.export(self.root, self.sessions_dir / session_id, ref)

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

    def task_control(self, session_id, action, **body):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before changing a task run')
            folder = self.sessions_dir / session_id
            if action == 'prepare':
                return task_run.prepare(self.root, folder)
            if action == 'prepare-asset':
                return task_run.prepare(self.root,folder,asset_profile=body['profile'])
            if action == 'prepare-fix':
                return task_run.prepare(self.root, folder, finding=dict(bug_id=body['bug_id'], bug_hash=body['bug_hash'], scenario=body['scenario']))
            if action == 'choose-direction':
                return asset_run.choose(self.root,folder,body['run_id'],body['choice'])
            if action == 'refine-asset':
                return asset_run.refine(self.root,folder,body['run_id'],body['note'])
            if action == 'decide':
                return task_run.respond(self.root, folder, body['run_id'], body['choice'],
                    'Owner chose ' + body['choice'] + ' for the reviewed task run')
            if action == 'resume':
                return task_run.launch(self.root, folder, body['run_id'])
            if action == 'stop':
                _, _, _, plan = task_run.load(folder, body['run_id'])
                return (git_automation.stop if plan.get('git_repair') else task_run.stop)(self.root, folder, body['run_id'])
            if action == 'promote':
                return task_run.promote(self.root, folder, body['run_id'])
            if action == 'escalate':
                _, h, _, plan = task_run.load(folder, body['run_id'])
                from .attempts import TaskAttempts, Attempts
                if plan.get('kind') == 'finding':
                    return Attempts(h).decide(plan['finding']['bug']['id'], choice=body['choice'], expected_state_hash=body['state_hash'],
                        approver='johnathan', quote='Owner chose ' + body['choice'] + ' after reviewing the blocked finding attempts')
                return TaskAttempts(h, plan['task_identity']).decide(body['choice'], body['state_hash'],
                    'Owner chose ' + body['choice'] + ' after reviewing the blocked task attempts')
            raise ValueError('Unknown task run action')

    def finding_control(self, session_id, action, **body):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before changing its findings')
            folder = self.sessions_dir / session_id
            if action == 'describe':
                return findings.describe(self.root, folder, **body)
            if action == 'prepare':
                return findings.prepare(self.root, folder, **body)
            if action == 'close':
                return findings.prepare_close(self.root, folder, body['run_id'])
            return findings.qa(self.root, folder, action, **body)

    def asset_concept_image(self,session_id,run_id,choice,view):
        with self.lock:
            if not self.session or self.session['id']!=session_id:
                raise ValueError('Reopen the intended session before viewing concept renders')
            return asset_run.image(self.sessions_dir/session_id,run_id,choice,view)

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

    def task_preview(self, session_id, run_id, index, image_name=None, stage='candidate'):
        with self.lock:
            if not self.session or self.session['id'] != session_id:
                raise ValueError('Reopen the intended session before viewing a task run')
            folder = self.sessions_dir / session_id
            if image_name is not None:
                return task_run.image(folder, run_id, index, image_name, stage=stage)
            if stage != 'candidate':
                raise ValueError('Choose a saved task candidate')
            return task_run.preview(folder, run_id, index)

    def verify(self):
        with self.lock:
            state = self.snapshot()
            if not self.manifest and state.get('build', {}).get('completed'):
                folder = self.sessions_dir / self.session['id']
                result = chat_build.verify(self.root, folder)
                if state.get('findings'):
                    from .contract_lock import verify as verify_contracts
                    result['finding_history'] = verify_contracts(chat_build.harness(folder).root)
                    result['passed'] = result['passed'] and result['finding_history']['ok']
                return result
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
            try:
                self.end_headers()
                self.wfile.write(raw)
            except ConnectionError:
                # A closed tab must not trigger a second response or undo saved work.
                self.close_connection = True

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
            # Only these public UI resources are served without the private API token.
            ui_resources = {'/ui-library.css': ('ui_library.css', 'text/css; charset=utf-8'),
                            '/voice-input.js': ('voice_input.js', 'text/javascript; charset=utf-8'),
                            '/ui-library.js': ('ui_library.js', 'text/javascript; charset=utf-8')}
            if url.path in ui_resources:
                if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                    return self.reply(403, {'error': 'Invalid host'})
                filename, mime = ui_resources[url.path]
                return self.reply(200, (Path(__file__).parent / filename).read_bytes(), mime)
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
                if url.path == '/api/asset-concept-image':
                    q=parse_qs(url.query)
                    return self.reply(200,app.asset_concept_image(q['session_id'][0],q['run_id'][0],q.get('choice',[''])[0],q['view'][0]),'image/png')
                if url.path == '/api/generated-image':
                    q = parse_qs(url.query)
                    return self.reply(200, app.generated_image_preview(q['session_id'][0], q['turn_id'][0], q['ref'][0]), 'image/png')
                if url.path == '/api/asset-image':
                    q = parse_qs(url.query)
                    return self.reply(200, app.asset_image_preview(q['session_id'][0], q['ref'][0]), 'image/png')
                if url.path == '/api/quality-image':
                    q = parse_qs(url.query)
                    return self.reply(200,app.quality_image_preview(q['session_id'][0],q['ref'][0],q['name'][0]),'image/png')
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
                if url.path in ('/api/task-preview', '/api/task-image'):
                    q = parse_qs(url.query)
                    result = app.task_preview(q['session_id'][0], q['run_id'][0], int(q['index'][0]),
                        q['name'][0] if url.path == '/api/task-image' else None,
                        stage=q.get('stage', ['candidate'])[0])
                    return self.reply(200, result, 'image/png' if url.path == '/api/task-image' else 'application/json')
                if url.path in ('/api/git-preview', '/api/git-image'):
                    q = parse_qs(url.query)
                    result = app.git_preview(q['session_id'][0], q['run_id'][0], q.get('stage', [None])[0],
                        q['name'][0] if url.path == '/api/git-image' else None)
                    return self.reply(200, result, 'image/png' if url.path == '/api/git-image' else 'application/json')
                if url.path == '/api/export-git':
                    q = parse_qs(url.query)
                    with app.lock:
                        if not app.session or app.session['id'] != q['session_id'][0]:
                            raise ValueError('Reopen the intended session before exporting Git work')
                        data, filename = git_task.export(app.sessions_dir / app.session['id'], q['run_id'][0])
                    return self.reply(200, data, 'application/zip', download=filename)
                if url.path == '/api/export-version':
                    q = parse_qs(url.query)
                    data, filename = app.export_version(q['ref'][0])
                    return self.reply(200, data, 'application/zip', download=filename)
                if url.path == '/api/export-handoff':
                    q = parse_qs(url.query)
                    data, filename = app.export_handoff(q['session_id'][0], q['ref'][0])
                    return self.reply(200, data, 'application/zip', download=filename)
                if url.path == '/api/image':
                    q = parse_qs(url.query)
                    return self.reply(200, app.image(q['ref'][0], q.get('choice', [None])[0]), 'image/png')
                self.reply(404, {'error': 'Unknown route'})
            except Exception as error:
                self.reply(400, {'error': str(error)})

        def do_POST(self):
            if not self.authorized() or self.headers.get('Content-Type') != 'application/json':
                # Closing with unread request bytes can reset the socket on Windows,
                # hiding the 403 from the caller. Drain only bounded bodies; never parse
                # or dispatch them, and do not wait indefinitely for a missing body.
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                except ValueError:
                    size = 0
                if 0 < size <= 64000:
                    timeout = self.connection.gettimeout()
                    try:
                        self.connection.settimeout(1)
                        self.rfile.read(size)
                    except OSError:
                        pass
                    finally:
                        self.connection.settimeout(timeout)
                self.close_connection = True
                return self.reply(403, {'error': 'Local app authorization required'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= (64000 if self.path in ('/api/project-brief', '/api/gameplay-plan', '/api/project-plan') else 16000):
                    raise ValueError('Invalid request size')
                body = json.loads(self.rfile.read(size))
                if self.path == '/api/start':
                    app.start(body.get('name'), new_session=body.get('new_session') is True,
                              chat_only=body.get('chat_only') is True, provider=body.get('provider', 'muse'),
                              project_parent=body.get('project_parent'))
                    result = {'status': 'started'}
                elif self.path == '/api/project-folder-picker':
                    result = app.pick_project_parent(body.get('parent'))
                elif self.path == '/api/project-copy':
                    result = app.copy_project(body['session_id'], body['current_ref'], body['name'], body['project_parent'])
                elif self.path == '/api/workspace':
                    result = app.workspace_control(**body)
                elif self.path == '/api/mechanics':
                    result = app.mechanic_control(**body)
                elif self.path == '/api/git-task':
                    result = app.git_control(**body)
                elif self.path == '/api/asset-update':
                    result = app.review_asset_update(body['session_id'], body['asset_ref'], body['current_ref'])
                elif self.path == '/api/chat':
                    result = app.chat(body['text'], body['id'])
                elif self.path == '/api/plan-build':
                    result = app.start_plan_build(body['session_id'], body['plan_ref'])
                elif self.path == '/api/build-resume':
                    result = app.resume_build(body['ref'])
                elif self.path == '/api/request-changes':
                    result = app.request_changes(body['ref'], body['note'], body['id'], body.get('gameplay_report_id'))
                elif self.path == '/api/playtest':
                    result = app.record_playtest(**body)
                elif self.path == '/api/playtest-fix':
                    result = app.fix_playtest(**body)
                elif self.path == '/api/smoke-check':
                    result = app.record_smoke(**body)
                elif self.path == '/api/restore-version':
                    result = app.restore_version(body['session_id'], body['ref'], body['current_ref'], body['id'])
                elif self.path == '/api/polish':
                    result = app.polish_control(**body)
                elif self.path == '/api/task-run':
                    result = app.task_control(**body)
                elif self.path == '/api/finding':
                    result = app.finding_control(**body)
                elif self.path == '/api/project-brief':
                    result = app.save_brief(body['session_id'], body['fields'], body['revision'])
                elif self.path == '/api/project-plan':
                    result = app.plan_control(**body)
                elif self.path == '/api/gameplay-plan':
                    result = app.save_gameplay(body['session_id'], body['plan'], body['revision'])
                elif self.path == '/api/gameplay-run':
                    result = app.run_gameplay(body['session_id'], body['revision'], body['request_ref'], body['report_id'])
                elif self.path == '/api/proposal-check':
                    result = app.check_proposal(body['session_id'], body['revision'], body['request_ref'], body['report_id'])
                elif self.path == '/api/model':
                    result = app.choose_model(body['provider'])
                elif self.path == '/api/image-credits':
                    result = app.verify_image_credits(body['session_id'], body['balance_usd'], body.get('no_paid_fallback'))
                elif self.path == '/api/generate-image':
                    result = app.generate_saved_image(body['session_id'], body['turn_id'])
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
    parser.add_argument('--open-browser', action='store_true', help='open the private launch link in your default browser')
    parser.add_argument('--local-agent-binary')
    parser.add_argument('--local-agent-model', default='qwen2.5-coder:7b')
    args = parser.parse_args()
    app = App(args.root, args.local_agent_binary, args.local_agent_model)
    http = server(app, args.port)
    print(f'Ember app: http://127.0.0.1:{http.server_port}/#{app.token}', flush=True)
    if args.open_browser:
        import webbrowser
        try:
            webbrowser.open(f'http://127.0.0.1:{http.server_port}/#{app.token}')
        except (webbrowser.Error, OSError):
            print('Could not open your browser. Open the private link above manually.', flush=True)
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
