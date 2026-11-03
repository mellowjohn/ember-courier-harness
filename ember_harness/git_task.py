"""Reviewed local Git browser repairs; source repositories and native tests never run.

The trusted worker commits exact reviewed bytes in fresh private Git repositories.
A distinct verifier uses the existing frozen Chromium driver on named clean builds.
This is a browser checkpoint adapter, not canonical bug closure or general shell work.
"""
from copy import deepcopy
from datetime import datetime, timezone
import difflib
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
import zipfile

from . import chat_build, gameplay, polish, polish_runtime, project_plan
from .attempts import TaskAttempts
from .contract_lock import git, verify as contract_lock
from .core import content_hash, digest, subset, validate
from .owner_review import OwnerReview, decide, load_request, validate_history
from .recovery import atomic_json, exclusive, read_json, worker_active

CONTENT = r'^[\s\S]{1,4194304}$'
BRANCH = r'^round/1/ct-git-worker-[a-f0-9]{24}-0001$'
MESSAGE = r'^Ember Git (?:baseline|candidate)[\s\S]{1,8000}$'
NOTICE = ('Exact reviewed browser source only; no repository commands, hooks, filters, native tests, '
          'remotes or model calls. Creates a fresh isolated local Git history and runs the same frozen '
          'Chromium regression on clean named baseline/head builds. A failing baseline and passing '
          'candidate support review; human quality, exact game application and bug closure remain separate.')


def add_scope_permissions(scope, folder):
    area = (Path(folder) / 'git-runs').as_posix() + '/**'
    scope['allowed_paths']['read'].append(area)
    scope['allowed_paths']['write'].append(area)
    scope['allowed_actions'] += [
        dict(action_id='git-file', tool='fs.write', **{'class': 'write'}, allow_no_evidence=True,
             args_constraints=dict(path=dict(path_within=area), content=dict(pattern=CONTENT))),
        dict(action_id='git-stage', tool='git.add', **{'class': 'local_commit'}, allow_no_evidence=True,
             args_constraints=dict(branch=dict(pattern=BRANCH), path=dict(path_within=area))),
        dict(action_id='git-commit', tool='git.commit', **{'class': 'local_commit'}, allow_no_evidence=True,
             args_constraints=dict(branch=dict(pattern=BRANCH), message=dict(pattern=MESSAGE))),
        dict(action_id='git-browser', tool='test.run', **{'class': 'compute'}, allow_no_evidence=True,
             args_constraints=dict(script=dict(equals=polish_runtime.DRIVER.resolve().as_posix())))]


def run_folder(folder, run_id):
    if not isinstance(run_id, str) or re.fullmatch('[a-f0-9]{24}', run_id) is None:
        raise ValueError('Choose a saved Git browser run')
    path = Path(folder) / 'git-runs' / run_id
    if path.resolve() != path.absolute():
        raise ValueError('Git run path changed')
    return path


def load(folder, run_id):
    work = run_folder(folder, run_id)
    for name in ('plan.json', 'run.json', 'state.json'):
        path = work / name
        if path.is_symlink() or path.resolve() != path.absolute():
            raise ValueError('Git control path changed')
    h = chat_build.harness(folder)
    if (work / 'run.json').exists():
        control = read_json(work / 'run.json')
        if set(control) != {'request_ref'}:
            raise ValueError('Git control reference changed')
        packet = load_request(h, control['request_ref'])
    else:
        matches = [row['payload'] for row in requests(folder) if row['payload']['body']['git_task']['id'] == run_id]
        if len(matches) != 1:
            raise ValueError('Exactly one audited Git review is required for control recovery')
        packet = matches[0]
    plan = packet['body']['git_task']
    if (plan['id'] != run_id or plan['session_id'] != Path(folder).name or plan['workspace'] != work.as_posix()
            or read_json(work / 'plan.json') != plan):
        raise ValueError('Reviewed Git task inputs changed')
    for item in packet['body']['contracts']:
        if item['contract']['extensions'].get('git_task') != dict(id=run_id, plan_sha256=digest(plan)):
            raise ValueError('Git contract differs from its reviewed plan')
    validate_history(h, h._entries())
    return work, h, packet, plan


def _review_state(work, h, packet):
    state = read_json(work / 'state.json') if (work / 'state.json').exists() else dict(
        status='awaiting_approval', phase='Review exact Git repair and browser checks', error=None)
    if state['status'] == 'awaiting_approval':
        prior = next((e for e in h._entries() if e['kind'] == 'owner_decision' and e['request_ref'] == digest(packet)), None)
        if prior:
            state = dict(status='ready' if prior['choice'] == 'approve' else 'declined',
                phase='Git permissions approved; run explicitly' if prior['choice'] == 'approve' else 'Git review discarded', error=None)
            if prior['choice'] == 'approve' and any(e['kind'] == 'task_attempt_started' and e['run_id'] == packet['body']['git_task']['id'] for e in h._entries()):
                state.update(status='interrupted', phase='Interrupted Git run; resume the same attempt')
            if prior['choice'] == 'approve' and (work / 'stop.json').exists():
                state.update(status='stopped', phase='Stopped by owner')
    return state


def manifest(files):
    return {name: sha256(value.encode('utf-8')).hexdigest() for name, value in files.items()}


def _check_git_paths(work, branch):
    if os.name == 'nt':
        paths = [work / area / '.git/logs/refs/heads' / (branch + '.lock')
                 for area in ('baseline', 'candidate', 'verify-before', 'verify-head')]
        if any(len(str(path).encode('utf-16-le')) // 2 > 248 for path in paths):
            raise ValueError('This Ember project folder is too long for local Git history on Windows. '
                'Choose a shorter Ember workspace location and prepare the repair again. '
                'The original imported source can stay in its current location.')


def prepare(root, folder, *, candidate_files, baseline_files=None, origin=None, goal=None, expected_manifest=None):
    folder = Path(folder)
    with exclusive(folder / 'chat.lock'), exclusive(folder / 'build.lock'):
        frozen = project_plan.context(root, folder)
        if not frozen:
            raise ValueError('Approve a project plan before preparing Git work')
        parent = project_plan.check_binding(root, folder, frozen['binding'])
        if any(row['status'] in ('awaiting_approval', 'ready', 'running', 'interrupted', 'ready_review') for row in history(root, folder)):
            raise ValueError('Finish or discard the existing Git run first')
        build = chat_build.status(root, folder)
        proposal_ref = origin.get('proposal_ref') if isinstance(origin, dict) else None
        if build['resumable'] or any(not row['decision'] and row['ref'] != proposal_ref for row in build['requests']):
            raise ValueError('Finish the pending build before preparing Git work')
        current = chat_build.context(root, folder)
        if expected_manifest is not None and current['manifest'] != expected_manifest:
            raise ValueError('Current game changed while preparing Git edits; review the new source')
        base = {row['path']: row['content'] for row in current['files']} if baseline_files is None else deepcopy(baseline_files)
        candidate = deepcopy(candidate_files)
        source_plan = None
        if isinstance(origin, dict) and 'task_run_id' in origin:
            from .git_automation import source, linked
            source_work, _, source_packet, source_plan, source_report, source_files, source_base = source(folder, origin, root=root, active=True)
            if linked(folder, source_plan['id']):
                raise ValueError('This generated task already has its exact Git verification; resume or review that handoff')
            if source_files != candidate or source_base != base or current['manifest'] != source_plan['base_manifest']:
                raise ValueError('Generated Git source differs from its independently reviewed task handoff')
            frozen = deepcopy(source_plan['project_plan'])
            parent = project_plan.check_binding(root, folder, frozen['binding'])
        for files in (base, candidate):
            if not isinstance(files, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in files.items()):
                raise ValueError('Use complete flat browser source files')
            chat_build.validate_files(files)
        if set(base) - set(candidate) or base == candidate:
            raise ValueError('Git repair must change source without deleting existing files')
        if any(base.get(name) != candidate.get(name) for name in chat_build.PROTECTED_FILES):
            raise ValueError('Git repairs preserve prepared assets and runtime exactly')
        if proposal_ref:
            snapshot = chat_build.proposal_snapshot(root, folder, proposal_ref)
            proposal = load_request(chat_build.harness(folder), proposal_ref)['body']['build']
            if (snapshot['files'] != candidate or snapshot['before_files'] != base or
                    proposal.get('project_scope') != frozen['binding']):
                raise ValueError('Git source differs from the exact pending scoped proposal')
        checks = gameplay.load(folder)
        if not checks['plan']['scenarios']:
            raise ValueError('Save a failing browser regression plan before preparing Git work')
        task = next(item for item in frozen['tasks'] if item['id'] == frozen['selected_task'])
        from .task_run import identity
        task_identity = identity(frozen['binding'], task['title'])
        attempts = TaskAttempts(chat_build.harness(folder), task_identity).status()
        if source_plan is not None:
            if source_plan['task_identity'] != task_identity:
                raise ValueError('Generated Git task identity changed')
            from .git_automation import Ledger
            Ledger(folder, origin).begin(source_plan['id'], origin['index'])
        elif attempts['blocked'] or any(row['outcome'] == 'running' for row in attempts['attempts']):
            raise ValueError('Task attempt allowance needs an owner decision or recovery')
        goal = task['title'] if goal is None else goal
        if not isinstance(goal, str) or not 1 <= len(goal.strip()) <= 2000:
            raise ValueError('Describe the repair in 1–2000 characters')
        run_id = secrets.token_hex(12)
        work = run_folder(folder, run_id)
        worker_id = 'ct-git-worker-' + run_id + '-0001'
        _check_git_paths(work, 'round/1/' + worker_id)
        runtime = polish_runtime.discover(root)
        runtime['driver'] = Path(runtime['driver']).resolve().as_posix()
        from .mechanic_workflow import binding as mechanic_binding
        plan = dict(id=run_id, session_id=folder.name, workspace=work.as_posix(),
            goal=goal, task_identity=task_identity, project_plan=frozen,
            baseline_files=base, candidate_files=candidate, base_manifest=manifest(base), candidate_manifest=manifest(candidate),
            application_manifest=current['manifest'], gameplay_plan=checks, runtime=runtime,
            mechanics=mechanic_binding(base),
            branch='round/1/' + worker_id, origin=deepcopy(origin), notice=NOTICE,
            created_at=datetime.now(timezone.utc).isoformat())
        # Preparation artifacts carry no execution authority and create no Git repo.
        work.mkdir(parents=True)
        atomic_json(work / 'plan.json', plan)
        children = []
        for role, cid, agent in [('worker', worker_id, 'ember-git-browser-worker'),
                                 ('verifier', 'ct-git-verifier-' + run_id + '-0001', 'ember-git-browser-verifier')]:
            c = deepcopy(parent)
            c.update(id=cid, version=1, agent=agent, status='draft', approved_at=None, approved_by=None, content_hash=None,
                goal=role + ': ' + plan['goal'], approval_mode='each')
            c['extensions']['orchestration'] = dict(role=role)
            c['extensions']['lineage'] = dict(supersedes=None, amendment_log=[], derived_from=None)
            c['extensions']['git_task'] = dict(id=run_id, plan_sha256=digest(plan))
            c['allowed_paths'] = dict(read=[work.as_posix() + '/**', Path(runtime['driver']).parent.as_posix() + '/**'],
                write=[(work / name).as_posix() + '/**' for name in
                       (('baseline', 'candidate', 'verify-before', 'verify-head', 'git-meta') if role == 'worker' else ('captures',))])
            if source_plan is not None:
                c['allowed_paths']['read'].append(source_work.as_posix() + '/**')
            if role == 'worker':
                c['allowed_paths']['write'] += [(work / name).as_posix() + '*' for name in ('baseline', 'candidate', 'verify-before', 'verify-head')]
            c['limits']['max_calls'] = min(50, parent['limits']['max_calls'])
            c['allowed_actions'] = []
            if role == 'worker':
                for area, files in [('baseline', base), ('candidate', candidate), ('verify-before', base), ('verify-head', candidate)]:
                    for name, text in files.items():
                        c['allowed_actions'].append(dict(action_id=area + '-' + name.replace('.', '-'), tool='fs.write',
                            **{'class': 'write'}, args_constraints=dict(path=dict(equals=(work / area / name).as_posix()), content=dict(equals=text))))
                c['allowed_actions'] += [
                    dict(action_id='stage', tool='git.add', **{'class': 'local_commit'}, args_constraints=dict(
                        branch=dict(equals=plan['branch']), path=dict(one_of=[(work / name).as_posix() for name in ('baseline', 'candidate', 'verify-before', 'verify-head')]))),
                    dict(action_id='commit', tool='git.commit', **{'class': 'local_commit'}, args_constraints=dict(
                        branch=dict(equals=plan['branch']), message=dict(pattern=MESSAGE)))]
            else:
                c['allowed_actions'] = [
                    dict(action_id='context-write', tool='fs.write', **{'class': 'write'}, args_constraints=dict(
                        path=dict(one_of=[(work / 'captures' / str(i) / 'input.json').as_posix() for i in (0, 1)]), content=dict(pattern=CONTENT))),
                    dict(action_id='browser', tool='test.run', **{'class': 'compute'}, args_constraints=dict(script=dict(equals=runtime['driver'])))]
            c['required_evidence'] = {a['action_id']: [dict(kind='file_hash', params={})] for a in c['allowed_actions']}
            c['inputs'] = [dict(name='git_plan', path=(work / 'plan.json').as_posix(), sha256=polish_runtime.file_digest(work / 'plan.json'))]
            for name in ('git_task.py', 'contract_lock.py', 'polish.py', 'polish_runtime.py', 'polish_browser.js', 'gameplay.py', 'chat_build.py'):
                path = Path(__file__).parent / name
                c['inputs'].append(dict(name='host_' + name.replace('.', '_'), path=path.resolve().as_posix(), sha256=polish_runtime.file_digest(path)))
            if source_plan is not None:
                for name in ('git_automation.py', 'task_run.py', 'findings.py', 'attempts.py'):
                    path = Path(__file__).with_name(name).resolve()
                    c['inputs'].append(dict(name='source_host_' + name.replace('.', '_'), path=path.as_posix(), sha256=polish_runtime.file_digest(path)))
                c['inputs'].append(dict(name='source_report', path=(source_work / 'reports' / (str(origin['index']) + '.json')).as_posix(), sha256=origin['report_sha256']))
            try:
                from . import mechanic_workflow
                for index, path in enumerate(getattr(mechanic_workflow, 'input_paths', lambda: [])()):
                    path = Path(path).resolve()
                    c['inputs'].append(dict(name='mechanic_host_' + str(index), path=path.as_posix(), sha256=polish_runtime.file_digest(path)))
            except ImportError:
                pass
            validate(c)
            if not subset(c, parent):
                raise ValueError('Amend or renew the project plan to review Git worker permissions first')
            children.append(dict(contract=c, parent_id=parent['id']))
        h = chat_build.harness(folder)
        for item in children:
            h.save_draft(item['contract'])
        ref = OwnerReview()._request(h, 'contracts', dict(contracts=children, git_task=plan), wait=False)
        atomic_json(work / 'run.json', dict(request_ref=ref))
        atomic_json(work / 'state.json', dict(status='awaiting_approval', phase='Review exact Git repair and browser checks', error=None))
        return dict(id=run_id, request_ref=ref)


def respond(root, folder, run_id, choice, quote):
    work, h, packet, plan = load(folder, run_id)
    with exclusive(Path(folder) / 'git-review.lock'):
        ref = digest(packet)
        prior = next((e for e in h._entries() if e['kind'] == 'owner_decision' and e['request_ref'] == ref), None)
        if prior:
            if prior['choice'] != choice:
                raise ValueError('Git review is already decided')
            state = _review_state(work, h, packet)
            if not (work / 'state.json').exists() or read_json(work / 'state.json')['status'] == 'awaiting_approval':
                atomic_json(work / 'state.json', state)
            return dict(status=state['status'], id=run_id)
        else:
            if choice != 'decline':
                project_plan.check_binding(root, folder, plan['project_plan']['binding'])
                if isinstance(plan.get('origin'), dict) and 'task_run_id' in plan['origin']:
                    from .git_automation import source
                    source(folder, plan['origin'], root=root, active=True)
            decide(h, ref, choice, quote)
        state = 'ready' if choice == 'approve' else 'declined'
        if choice == 'decline' and isinstance(plan.get('origin'), dict) and 'task_run_id' in plan['origin']:
            from .git_automation import Ledger
            Ledger(folder, plan['origin']).abandon(run_id, 'Owner discarded exact Git verification permissions')
        atomic_json(work / 'state.json', dict(status=state, phase='Git permissions approved; run explicitly' if state == 'ready' else 'Git review discarded', error=None))
        return dict(status=state, id=run_id)


def requests(folder):
    if not (Path(folder) / 'build-authority').exists():
        return []
    h = chat_build.harness(folder)
    entries = h._entries()
    decisions = {e['request_ref']: e for e in entries if e['kind'] == 'owner_decision'}
    result = []
    for event in entries:
        if event['kind'] == 'owner_request':
            packet = load_request(h, event['request_ref'])
            if 'git_task' in packet['body']:
                result.append(dict(ref=event['request_ref'], payload=packet, decision=decisions.get(event['request_ref']), origin='git'))
    return result


def launch(root, folder, run_id):
    worker = Worker(root, folder, run_id)
    with exclusive(worker.work / 'launch.lock'):
        worker.check()
        if (_finished(worker.h, run_id)
                and _review_state(worker.work, worker.h, worker.packet)['status'] not in ('running', 'interrupted')):
            raise ValueError('This Git run already has a completed result')
        if worker_active(worker.work):
            return dict(status='running', id=run_id)
        with (worker.work / 'execution.log').open('ab') as log:
            subprocess.Popen([sys.executable, '-m', 'ember_harness.git_task', str(Path(root).resolve()), str(Path(folder).resolve()), run_id],
                cwd=root, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        for _ in range(100):
            if worker_active(worker.work) or _review_state(worker.work, worker.h, worker.packet)['status'] not in ('ready', 'interrupted'):
                break
            time.sleep(.02)
    return dict(status='running', id=run_id)


def stop(root, folder, run_id):
    work, h, packet, plan = load(folder, run_id)
    if not any(e['kind'] == 'owner_decision' and e['request_ref'] == digest(packet) and e['choice'] == 'approve' for e in h._entries()):
        raise ValueError('Discard an unapproved Git run through its review')
    atomic_json(work / 'stop.json', dict(requested_at=datetime.now(timezone.utc).isoformat()))
    if not worker_active(work):
        Worker(root, folder, run_id).ledger().abandon(run_id, 'Stopped by owner')
        atomic_json(work / 'state.json', dict(status='stopped', phase='Stopped by owner', error=None))
    return dict(status='stop_requested')


def _files(path, expected):
    if path.resolve() != path.absolute() or path.is_symlink():
        raise ValueError('Git source path changed')
    actual = {}
    for item in path.iterdir():
        if item.name == '.git':
            continue
        if item.name not in expected or not item.is_file() or item.is_symlink() or item.resolve() != item.absolute():
            raise ValueError('Git source tree contains an unexpected path')
        actual[item.name] = item.read_bytes().decode('utf-8')
    if actual != expected:
        raise ValueError('Git source bytes differ from reviewed input')
    return actual


def _metadata(repo, expected=None):
    meta = repo / '.git'
    if not meta.is_dir() or meta.is_symlink() or meta.resolve() != meta.absolute():
        raise ValueError('Git metadata directory changed')
    seen, total = 0, 0
    for directory, dirs, files in os.walk(meta, followlinks=False):
        for name in dirs + files:
            item = Path(directory) / name
            info = item.lstat()
            seen += 1
            if (seen > 512 or stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400
                    or item.resolve() != item.absolute() or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode))):
                raise ValueError('Git metadata contains an unsafe or unbounded path')
            total += info.st_size if stat.S_ISREG(info.st_mode) else 0
            if total > 64 * 1024 * 1024 or info.st_size > 16 * 1024 * 1024:
                raise ValueError('Git metadata exceeds the private snapshot allowance')
    for rel in ('config', 'HEAD', 'index'):
        path = meta / rel
        if path.exists() and (path.is_symlink() or path.resolve() != path.absolute()):
            raise ValueError('Git metadata path changed')
    for rel in ('hooks', 'info/attributes', 'objects/info/alternates', 'commondir', 'worktrees'):
        path = meta / rel
        if path.exists() or path.is_symlink():
            raise ValueError('Git helper, attributes or external object metadata is excluded')
    config = (meta / 'config').read_bytes()
    if len(config) > 4096:
        raise ValueError('Only private host-created Git configuration is supported')
    allowed = dict(core=dict(repositoryformatversion={'0'}, bare={'false'}, filemode={'true', 'false'},
        logallrefupdates={'true'}, ignorecase={'true', 'false'}, symlinks={'true', 'false'}, precomposeunicode={'true', 'false'}))
    keys, sections, section = set(), set(), None
    for line in config.decode('utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        heading = re.fullmatch(r'\[(core)\]', line.lower())
        if heading:
            section = heading[1]
            if section in sections:
                raise ValueError('Duplicate Git configuration section')
            sections.add(section)
            continue
        match = re.fullmatch(r'([A-Za-z]+)\s*=\s*([A-Za-z0-9]+)', line)
        if (section is None or not match or match[1].lower() not in allowed[section]
                or (section, match[1].lower()) in keys or match[2].lower() not in allowed[section][match[1].lower()]):
            raise ValueError('Only fixed host-created Git settings are supported')
        keys.add((section, match[1].lower()))
    if not {('core', name) for name in ('repositoryformatversion', 'bare', 'filemode', 'logallrefupdates')} <= keys:
        raise ValueError('Git metadata is not a complete private initialized repository')
    result = sha256(config).hexdigest()
    if expected is not None and result != expected:
        raise ValueError('Git configuration changed')
    return result


class Worker(polish.Worker):
    checkpoint_kind = 'git_checkpoint'

    def __init__(self, root, folder, run_id):
        self.root, self.folder = Path(root), Path(folder)
        self.work, self.h, self.packet, self.plan = load(folder, run_id)
        self.ref = digest(self.packet)
        self.contract = self.packet['body']['contracts'][0]['contract']

    def check(self):
        self.cancel_check()
        project_plan.check_binding(self.root, self.folder, self.plan['project_plan']['binding'])
        if gameplay.load(self.folder) != self.plan['gameplay_plan']:
            raise ValueError('Saved regression plan changed; review a new Git run')
        if chat_build.context(self.root, self.folder)['manifest'] != self.plan['application_manifest']:
            raise ValueError('Current game changed since Git review')
        if isinstance(self.plan.get('origin'), dict) and 'task_run_id' in self.plan['origin']:
            from .git_automation import source
            source(self.folder, self.plan['origin'], root=self.root, active=True)
        proposal_ref = self.plan['origin'].get('proposal_ref') if isinstance(self.plan['origin'], dict) else None
        if proposal_ref:
            snapshot = chat_build.proposal_snapshot(self.root, self.folder, proposal_ref)
            if snapshot['files'] != self.plan['candidate_files'] or snapshot['before_manifest'] != self.plan['application_manifest']:
                raise ValueError('Pending Git source proposal changed')
        active = self.h._active(self.h._entries())
        if not any(e['kind'] == 'owner_decision' and e['request_ref'] == self.ref and e['choice'] == 'approve' for e in self.h._entries()):
            raise ValueError('Approve exact Git permissions before executing')
        for item in self.packet['body']['contracts']:
            c = item['contract']
            if c['id'] not in active or content_hash(self.h._authority(active[c['id']], active)) != content_hash(c):
                raise ValueError('Git authority changed')
        if not self.h.verify_inputs(self.contract['id']):
            raise ValueError('An approved Git input changed')

    def task(self, phase, *args):
        return super().task(self.plan['id'] + ':' + phase, *args)

    def commit(self, area, files, source_repo=None, commit=True):
        repo = self.work / area
        for name, text in files.items():
            self.write(area + '-' + name.replace('.', '-'), repo / name, text, area + '-' + name.replace('.', '-'))
        stage_record = self.work / 'git-meta' / (area + '-stage.json')
        def stage():
            _files(repo, files)
            if (repo / '.git').exists() or (repo / '.git').is_symlink():
                raise ValueError('Unexpected preexisting Git metadata; inspect an interrupted stage or prepare a new run')
            if source_repo is None:
                template = self.work / 'git-meta/empty-template'
                template.mkdir(parents=True, exist_ok=True)
                if any(template.iterdir()):
                    raise ValueError('Git template directory changed')
                git(repo, 'init', '--template=' + str(template), '--initial-branch=' + self.plan['branch'])
            else:
                original = read_json(self.work / 'git-meta' / (source_repo.name + '-stage.json'))
                _metadata(source_repo, original['config_sha256'])
                shutil.copytree(source_repo / '.git', repo / '.git')
            config_hash = _metadata(repo)
            git(repo, 'add', '--', *sorted(files))
            data = dict(config_sha256=config_hash, source_manifest=manifest(files))
            atomic_json(stage_record, data)
            return data
        staged = self.task('stage-' + area, 'stage', 'git.add', dict(branch=self.plan['branch'], path=repo.as_posix()),
            [source_repo.as_posix()] if source_repo else [], [repo.as_posix(), stage_record.as_posix()], stage_record, stage)
        _files(repo, files); _metadata(repo, staged['config_sha256'])
        if not commit:
            if git(repo, 'status', '--porcelain').strip():
                raise ValueError('Verifier checkout is not clean')
            return git(repo, 'rev-parse', 'HEAD').decode().strip()
        message = ('Ember Git ' + ('baseline' if area == 'baseline' else 'candidate') + ': ' + self.plan['goal'] + '\n\n'
            'Author: ' + self.packet['body']['contracts'][0]['contract']['agent'] + '\n'
            'Reviewer: ' + self.packet['body']['contracts'][1]['contract']['agent'] + '\n\n'
            'Round: 1\nContract-Id: ' + self.contract['id'] + '\nContract-Version: 1\nContract-Hash: '
            + content_hash(self.contract) + '\nSubsystem: triage\n')
        artifact = self.work / 'git-meta' / (area + '-commit.json')
        def committed():
            _files(repo, files); _metadata(repo, staged['config_sha256'])
            if area == 'candidate':
                checked = contract_lock(self.h.root, repo=repo, base=git(source_repo, 'rev-parse', 'HEAD').decode().strip(), staged_message=message)
                if not checked['ok']:
                    raise ValueError('Git contract-lock refused staged candidate: ' + '; '.join(checked['errors']))
            message_file = self.work / 'git-meta' / (area + '-message.txt')
            message_file.write_text(message, encoding='utf-8')
            git(repo, '-c', 'user.name=Ember local Git worker', '-c', 'user.email=worker@example.invalid', 'commit', '--file', str(message_file))
            result = dict(commit=git(repo, 'rev-parse', 'HEAD').decode().strip(), manifest=manifest(files), config_sha256=staged['config_sha256'])
            atomic_json(artifact, result)
            return result
        result = self.task('commit-' + area, 'commit', 'git.commit', dict(branch=self.plan['branch'], message=message),
            [repo.as_posix()], [repo.as_posix(), artifact.as_posix()], artifact, committed)
        if (git(repo, 'rev-parse', 'HEAD').decode().strip() != result['commit'] or git(repo, 'status', '--porcelain').strip()):
            raise ValueError('Git commit or clean checkout changed')
        return result['commit']

    def ledger(self):
        if isinstance(self.plan.get('origin'), dict) and 'task_run_id' in self.plan['origin']:
            from .git_automation import Ledger
            return Ledger(self.folder, self.plan['origin'])
        return TaskAttempts(self.h, self.plan['task_identity'])

    def run(self):
        with exclusive(self.work / 'worker.lock'):
            self.check()
            ledger = self.ledger()
            attempt = ledger.begin(self.plan['id'], 1)
            try:
                if _finished(self.h, self.plan['id']):
                    # A recorded report may precede the allowance/status receipts
                    # when the host stops. Recheck it and finalize the same attempt.
                    report = completed_report(self.folder, self.plan['id'])
                    self.check()
                    ledger.finish(attempt, report, self.work / 'report.json')
                    self.status(report['reason'], 'ready_review' if report['qualified'] else 'needs_changes')
                    return
                from .mechanic_workflow import review as mechanic_review
                source_review = mechanic_review(self.plan.get('mechanics'), self.plan['candidate_files'])
                base = self.commit('baseline', self.plan['baseline_files'])
                before = self.commit('verify-before', self.plan['baseline_files'], self.work / 'baseline', commit=False)
                if before != base:
                    raise ValueError('Baseline verifier has the wrong named build')
                self.contract = self.packet['body']['contracts'][1]['contract']
                observations_before = self.browser(0, _files(self.work / 'verify-before', self.plan['baseline_files']))
                if observations_before['gameplay']['outcome'] != 'failed':
                    report = dict(qualified=False, reason='Saved regression did not fail on the baseline; no candidate commit was created.', base=base,
                        head=None, before=observations_before, after=None, author=self.packet['body']['contracts'][0]['contract']['agent'], reviewer=self.contract['agent'])
                else:
                    self.contract = self.packet['body']['contracts'][0]['contract']
                    head = self.commit('candidate', self.plan['candidate_files'], self.work / 'baseline')
                    checked_head = self.commit('verify-head', self.plan['candidate_files'], self.work / 'candidate', commit=False)
                    if checked_head != head:
                        raise ValueError('Candidate verifier has the wrong named build')
                    checked = contract_lock(self.h.root, repo=self.work / 'candidate', base=base)
                    if not checked['ok']:
                        raise ValueError('Git contract-lock failed: ' + '; '.join(checked['errors']))
                    self.contract = self.packet['body']['contracts'][1]['contract']
                    observations_after = self.browser(1, _files(self.work / 'verify-head', self.plan['candidate_files']))
                    passed = (observations_after['gameplay']['outcome'] == 'passed'
                        and all(row.get('loaded') for row in observations_after['viewports'])
                        and polish.failures(dict(observations=observations_after)) == 0
                        and (source_review is None or not source_review['blockers']))
                    reason = ('Frozen baseline failed and clean head passed; exact application and human review remain pending.' if passed
                        else '; '.join(source_review['blockers']) if source_review and source_review['blockers']
                        else 'Required candidate browser checks failed.')
                    report = dict(qualified=passed, reason=reason,
                        base=base, head=head, before=observations_before, after=observations_after, contract_lock=checked,
                        author=self.packet['body']['contracts'][0]['contract']['agent'], reviewer=self.contract['agent'])
                report.update(run_id=self.plan['id'], base_manifest=self.plan['base_manifest'], candidate_manifest=self.plan['candidate_manifest'],
                    gameplay_plan_sha256=self.plan['gameplay_plan']['sha256'], origin=self.plan['origin'],
                    mechanics=source_review,
                    basis='Captured Chromium observations on clean private Git builds; deterministic host review, not AI/human quality or canonical bug closure.')
                path = self.work / 'report.json'
                self.check()
                atomic_json(path, report)
                with self.h._lock():
                    self.h._append('git_task_report', run_id=self.plan['id'], path=path.as_posix(), sha256=polish_runtime.file_digest(path))
                self.check()
                ledger.finish(attempt, report, path)
                self.status(report['reason'], 'ready_review' if report['qualified'] else 'needs_changes')
            except polish.Stopped as error:
                ledger.abandon(self.plan['id'], str(error))
                self.status(str(error), 'stopped')
            except Exception as error:
                if isinstance(error, subprocess.CalledProcessError):
                    detail = error.stderr.decode('utf-8', 'replace') if isinstance(error.stderr, bytes) else error.stderr
                    message = 'Local Git operation failed: ' + ((detail or '').strip() or 'exit status ' + str(error.returncode))
                else:
                    message = str(error)
                self.status('Git run interrupted; inspect and resume the same attempt', 'interrupted', message[:1000])


def _finished(h, run_id):
    return next((e for e in reversed(h._entries()) if e['kind'] == 'git_task_report' and e['run_id'] == run_id), None)


def completed_report(folder, run_id, *, _checking_closure=False):
    work, h, packet, plan = load(folder, run_id)
    event = _finished(h, run_id)
    if not event:
        return None
    if polish_runtime.file_digest(event['path']) != event['sha256']:
        raise ValueError('Git report changed')
    report = read_json(event['path'])
    if isinstance(plan.get('origin'), dict) and 'task_run_id' in plan['origin']:
        from .git_automation import source
        _, _, _, source_plan, source_report, files, baseline = source(folder, plan['origin'])
        if (files != plan['candidate_files'] or baseline != plan['baseline_files']
                or source_plan['task_identity'] != plan['task_identity'] or report.get('origin') != plan['origin']):
            raise ValueError('Git report differs from its frozen automated coding handoff')
    from .mechanic_workflow import binding as mechanic_binding, review as mechanic_review
    source_review = mechanic_review(plan.get('mechanics'), plan['candidate_files'])
    if (mechanic_binding(plan['baseline_files']) != plan.get('mechanics') or source_review != report.get('mechanics')
            or (report['qualified'] and source_review and source_review['blockers'])):
        raise ValueError('Git mechanic source review changed or cannot support qualification')
    entries = h._entries()
    for e in entries:
        if e['kind'] == 'git_checkpoint' and e['phase'].startswith(run_id + ':'):
            polish._checkpoint(h, e['phase'], 'git_checkpoint', entries=entries)
    for area, files, build in [('baseline', plan['baseline_files'], report['base']), ('verify-before', plan['baseline_files'], report['base']),
                                *([('candidate', plan['candidate_files'], report['head']), ('verify-head', plan['candidate_files'], report['head'])] if report['head'] else [])]:
        _files(work / area, files)
        staged = read_json(work / 'git-meta' / (area + '-stage.json'))
        _metadata(work / area, staged['config_sha256'])
        if git(work / area, 'rev-parse', 'HEAD').decode().strip() != build or git(work / area, 'status', '--porcelain').strip():
            raise ValueError('Named Git verification checkout changed')
        for name, text in files.items():
            if git(work / area, 'show', build + ':' + name) != text.encode('utf-8'):
                raise ValueError('Git build source differs from reviewed bytes')
    for index, key in [(0, 'before'), *([(1, 'after')] if report['head'] else [])]:
        source = work / 'captures' / str(index) / 'input.json'
        observed = polish_runtime.verified_report(source, source.parent / 'output')
        if observed != report[key]:
            raise ValueError('Git browser observations changed')
    if report['head'] and not contract_lock(h.root, repo=work / 'candidate', base=report['base'], _skip_browser_findings=_checking_closure)['ok']:
        raise ValueError('Retained Git contract-lock failed')
    return report


def history(root, folder):
    rows = []
    for row in requests(folder):
        work, h, packet, plan = load(folder, row['payload']['body']['git_task']['id'])
        state = _review_state(work, h, packet)
        cancelled = (state['status'] in ('declined', 'stopped') or (work / 'stop.json').exists()
                     or bool(row['decision'] and row['decision']['choice'] == 'decline'))
        if state['status'] == 'running' and not worker_active(work):
            state.update(status='interrupted', phase='Interrupted Git run; resume the same attempt')
        try:
            report = completed_report(folder, plan['id'])
            if report is None and isinstance(plan.get('origin'), dict) and 'task_run_id' in plan['origin']:
                from .git_automation import source
                source(folder, plan['origin'])
        except (ValueError, OSError, KeyError) as error:
            report = None
            state = dict(status='inspection_required', phase='Git evidence needs inspection', error=str(error)[:1000])
        promoted = next((e for e in h._entries() if e['kind'] == 'git_task_promoted' and e['run_id'] == plan['id']), None)
        if promoted and state['status'] != 'inspection_required':
            state['status'] = 'promoted'
        rows.append(dict(id=plan['id'], goal=plan['goal'], notice=plan['notice'], origin=plan['origin'], task_identity=plan['task_identity'],
            request_ref=digest(packet), contracts=packet['body']['contracts'],
            branch=plan['branch'], base_manifest=plan['base_manifest'], candidate_manifest=plan['candidate_manifest'],
            file_names=sorted(plan['baseline_files']), changed_files=[name for name in plan['candidate_files'] if plan['candidate_files'][name] != plan['baseline_files'].get(name)],
            diff=''.join(line for name in sorted(plan['candidate_files']) for line in difflib.unified_diff(
                plan['baseline_files'].get(name, '').splitlines(keepends=True), plan['candidate_files'][name].splitlines(keepends=True),
                fromfile='baseline/' + name, tofile='candidate/' + name))[:131072], gameplay_plan=plan['gameplay_plan'],
            attempts=TaskAttempts(h, plan['task_identity']).status(), proposal_ref=promoted['request_ref'] if promoted else None,
            blocks_new_work=not cancelled and state['status'] not in ('promoted', 'needs_changes'), report=report, **state))
        if isinstance(plan.get('origin'), dict) and 'task_run_id' in plan['origin']:
            from .git_automation import Ledger
            source_plan = Ledger(folder, plan['origin']).plan
            if source_plan.get('kind') == 'finding':
                from .attempts import Attempts
                bug_state = Attempts(h).status(source_plan['finding']['bug']['id'])
                rows[-1].update(finding=source_plan['finding'], attempts=dict(
                    attempts=[dict(number=item['number'], run_id=source_plan['id'], outcome=item['status']) for item in bug_state['attempts']],
                    blocked=bug_state['status'] in ('awaiting_decision', 'stopped'), state_hash=bug_state['state_hash']))
    return rows


def preview(folder, run_id):
    report = completed_report(folder, run_id)
    if report is None or not report['head']:
        raise ValueError('No completed Git candidate is available')
    plan = load(folder, run_id)[3]
    parser = chat_build.ResourcePreview(plan['candidate_files']); parser.feed(plan['candidate_files']['index.html']); parser.close()
    return dict(html=''.join(parser.output), basis='Isolated Git candidate; not applied')


def image(folder, run_id, stage, name):
    if stage not in ('baseline', 'candidate') or not isinstance(name, str):
        raise ValueError('Choose baseline or candidate evidence')
    filename = name if name.endswith('.png') else name + '.png'
    allowed = {view + suffix + '.png' for view in ('desktop', 'mobile') for suffix in ('', '-before', '-action', '-panel')}
    if filename not in allowed:
        raise ValueError('Choose a saved Git screenshot')
    report = completed_report(folder, run_id)
    observed = report.get('before' if stage == 'baseline' else 'after') if report else None
    if not observed or not any(row.get(prefix + 'screenshot') == filename for row in observed['viewports'] for prefix in ('', 'before_', 'action_', 'panel_')):
        raise ValueError('This Git screenshot was not observed')
    target = run_folder(folder, run_id) / 'captures' / str(0 if stage == 'baseline' else 1) / 'output' / filename
    if target.is_symlink() or target.resolve() != target.absolute():
        raise ValueError('Git capture path changed')
    return target.read_bytes()


def promote(root, folder, run_id):
    with exclusive(Path(folder) / 'chat.lock'), exclusive(Path(folder) / 'build.lock'):
        return _promote_locked(root, folder, run_id)


def _promote_locked(root, folder, run_id):
    report = completed_report(folder, run_id)
    if not report or not report['qualified']:
        raise ValueError('A qualifying independently checked Git head is required')
    worker = Worker(root, folder, run_id)
    plan = worker.plan
    # A crash can publish the exact review packet before its promotion receipts.
    # If that already-approved packet was applied, recover only those receipts
    # from verified historical writes; never replay execution or create new work.
    if not (isinstance(plan.get('origin'), dict) and plan['origin'].get('proposal_ref')):
        published = [request for request in chat_build.list_requests(folder)
                     if request['payload']['body']['build']['turn_id'] == 'git-' + run_id]
        if len(published) > 1:
            raise ValueError('Conflicting exact Git application reviews need inspection')
        if published and any(e['kind'] == 'chat_build_completed' and e['request_ref'] == published[0]['ref'] for e in worker.h._entries()):
            from .project_versions import snapshot
            prior = published[0]; body = prior['payload']['body']['build']
            saved = snapshot(root, folder, prior['ref'])
            if (saved['files'] != plan['candidate_files'] or body.get('before_manifest') != plan['application_manifest']
                    or body.get('project_scope') != plan['project_plan']['binding']):
                raise ValueError('Applied Git review differs from its frozen verification')
            _record_promotion(worker, prior['ref'])
            return dict(request_ref=prior['ref'])
    worker.check()
    proposal_ref = plan['origin'].get('proposal_ref') if isinstance(plan['origin'], dict) else None
    if proposal_ref:
        snapshot = chat_build.proposal_snapshot(root, folder, proposal_ref)
        proposal = load_request(worker.h, proposal_ref)['body']['build']
        if (snapshot['manifest'] != plan['candidate_manifest'] or snapshot['before_manifest'] != plan['application_manifest']
                or proposal.get('project_scope') != plan['project_plan']['binding']):
            raise ValueError('Verified Git head no longer matches the pending scoped proposal')
        ref = proposal_ref
    else:
        ref = chat_build.propose_build(root, folder, 'git-' + run_id, plan['goal'],
            dict(title='Git-verified browser repair', summary=report['reason'],
                 files=[dict(path=name, content=text) for name, text in plan['candidate_files'].items()]),
            expected_before=chat_build.manifest_hash(plan['application_manifest']), project_scope=plan['project_plan']['binding'])
    _record_promotion(worker, ref)
    return dict(request_ref=ref)


def _record_promotion(worker, ref):
    plan = worker.plan; run_id = plan['id']
    with worker.h._lock():
        if isinstance(plan.get('origin'), dict) and 'task_run_id' in plan['origin']:
            source_id = plan['origin']['task_run_id']
            prior = next((e for e in worker.h._entries() if e['kind'] == 'task_run_promoted' and e['run_id'] == source_id), None)
            if prior and prior['request_ref'] != ref:
                raise ValueError('Automated source handoff already has a different exact proposal')
            if prior is None:
                worker.h._append('task_run_promoted', run_id=source_id, request_ref=ref, index=plan['origin']['index'], git_run_id=run_id)
        if not any(e['kind'] == 'git_task_promoted' and e['run_id'] == run_id for e in worker.h._entries()):
            worker.h._append('git_task_promoted', run_id=run_id, request_ref=ref)


def export(folder, run_id):
    report = completed_report(folder, run_id)
    if not report or not report['qualified']:
        raise ValueError('A verified Git repair is required before export')
    plan = load(folder, run_id)[3]
    content = io.BytesIO()
    with zipfile.ZipFile(content, 'w', zipfile.ZIP_DEFLATED) as archive:
        files = {name: text.encode('utf-8') for name, text in plan['candidate_files'].items()}
        files['git-verification.json'] = json.dumps({key: report[key] for key in ('base', 'head', 'base_manifest', 'candidate_manifest', 'gameplay_plan_sha256', 'author', 'reviewer', 'basis')}, indent=2).encode('utf-8')
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    return content.getvalue(), 'ember-git-repair-' + run_id[:8] + '.zip'


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('Git browser workers are launched through the reviewed local host')
    Worker(*sys.argv[1:]).run()
