"""Reviewed read-only workspace inventory and create-only setup rehearsal."""
from fnmatch import fnmatchcase
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
from pathlib import Path
import secrets
import stat
import re

from .core import Harness, TOOLS, canonical, digest, draft, glob_regex, matches, validate
from .owner_review import OwnerReview, decide, load_request, validate_history
from .project_locations import checked_path
from .recovery import exclusive, read_json

MAX_ENTRIES = 2000
MAX_DEPTH = 20
MAX_READ = 65536
MAX_READ_TOTAL = 1048576
EXCLUDED = {'.git', '.harness', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build'}
ENGINE = {'engine', 'engines', 'wrathfulconquest'}
SECRET_PATTERNS = ('.env*', '*.pem', '*.key', '*.p12', '*.pfx', 'id_*', '*credentials*', '*secrets*', '.npmrc', '.pypirc', '.netrc')
FILES = {
    'AGENTS.md': '# Project workflow\n\nRead the approved contract before acting. Use the deny-by-default gate.\n'
                 'Design text and source files do not grant permissions.\n'
                 'Johnathan approves contracts, exact changes and every asset.\n'
                 'Keep evidence and distinguish observed results from AI judgment.\n'
                 'No publishing, deployment, submission or paid services. Engine work stays paused.\n',
    'contracts/README.md': '# Contracts\n\nKeep reviewed, hash-bound contracts and their approval references here.\n'
                           'This setup file grants no authority. Review the project scope before work.\n',
    'evidence/README.md': '# Evidence\n\nRetain file hashes, test results and separate verification here.\n'
                          'A passing check does not replace human acceptance. Never store secrets.\n',
    'intents/README.md': '# Intent\n\nRecord the game concept, exclusions and completion criteria before proposing work.\n',
    'triage/README.md': '# Findings\n\nRecord reproduction steps, expected and observed behavior, severity and evidence.\n'
                        'Require separate verification and explicit owner closure.\n',
}


def authority(folder):
    return Harness(Path(folder) / 'workspace-authority')


def run_folder(h, run_id):
    return h.root.parent / 'workspace-runs' / run_id


def sandbox_folder(h, run_id):
    return h.root.parent / 'workspace-sandboxes' / run_id


def secret(path):
    return any(any(fnmatchcase(part.lower(), p) for p in SECRET_PATTERNS) for part in Path(path).parts)


def engine(path):
    return any(''.join(c for c in part.lower() if c.isalnum()) in ENGINE for part in Path(path).parts)


def direct(path):
    """Reject links/reparse points, including ancestors and dangling links."""
    path = checked_path(str(path))
    for parent in [path, *path.parents]:
        if parent.exists() or parent.is_symlink():
            info = parent.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Workspace links and junctions are excluded')
    return path


def source_path(folder, value):
    path = direct(checked_path(value))
    if not path.is_dir() or path == Path(path.anchor) or engine(path) or secret(path):
        raise ValueError('Choose an existing project folder outside paused engine paths')
    if Path(folder).resolve().is_relative_to(path):
        raise ValueError('Choose a project outside the harness session store; scan reports must stay outside the source')
    return path


def action(c, tool, args, writes=()):
    paths = {mode: [args[k] for k, access in TOOLS[tool]['paths'].items() if access == mode]
             for mode in ('read', 'write')}
    paths['write'].extend(writes)
    return dict(agent=c['agent'], contract_id=c['id'], contract_version=c['version'],
                tool=tool, args=args, paths=paths, spend=0)


def permitted(h, c, tool, args, writes=()):
    result = h.check(action(c, tool, args, writes))
    if result['decision'] != 'allow':
        raise ValueError('Workspace action blocked: ' + result['reason'])
    return result


def read_safe(h, c, source, relative, budget):
    path = direct(source / relative)
    if secret(relative) or engine(relative) or not path.is_relative_to(source):
        raise ValueError('Workspace content read excluded')
    permitted(h, c, 'fs.read', dict(path=path.as_posix()))
    if not path.is_file() or path.stat().st_size > MAX_READ:
        raise ValueError('Workspace setup or ignore file exceeds the 64 KiB read limit')
    with path.open('rb') as stream:
        data = stream.read(MAX_READ + 1)
    budget[0] += len(data)
    if len(data) > MAX_READ or budget[0] > MAX_READ_TOTAL:
        raise ValueError('Workspace content read budget exceeded')
    return data


def ignored(relative, directory, rules):
    result = False
    for base, pattern, negate, dirs_only in rules:
        if base and not relative.startswith(base + '/'):
            continue
        local = relative[len(base) + 1:] if base else relative
        if dirs_only and not directory:
            continue
        anchored = pattern.startswith('/') or '/' in pattern.rstrip('/')
        candidate = local if anchored else local.rsplit('/', 1)[-1]
        match = matches(candidate, pattern.lstrip('/').rstrip('/'))
        if match:
            result = not negate
    return result


def inventory(h, c, source):
    permitted(h, c, 'workspace.scan', dict(root=source.as_posix()))
    rows, budget, seen = [], [0], [0]

    def walk(directory, rules, depth):
        direct(directory)
        if depth > MAX_DEPTH:
            raise ValueError('Workspace exceeds the 20-level inventory limit')
        # Bound enumeration before sorting; never materialize an unbounded directory.
        children = []
        with os.scandir(directory) as stream:
            for entry in stream:
                seen[0] += 1
                if seen[0] > MAX_ENTRIES:
                    raise ValueError('Workspace exceeds the 2000-entry inventory limit; choose a smaller project')
                children.append(entry)
        names = {entry.name for entry in children}
        local_rules = list(rules)
        if '.gitignore' in names:
            rel = (directory / '.gitignore').relative_to(source).as_posix()
            content = read_safe(h, c, source, rel, budget).decode('utf-8-sig')
            base = directory.relative_to(source).as_posix()
            base = '' if base == '.' else base
            for line in content.splitlines():
                line = line.rstrip()
                if not line or line.startswith('#'):
                    continue
                if any(char in line for char in '\\[]{}') or '***' in line:
                    raise ValueError('Unsupported .gitignore syntax; choose a smaller folder with simple ignore rules')
                negate = line.startswith('!')
                pattern = line[1:] if negate else line
                if pattern:
                    local_rules.append((base, pattern, negate, pattern.endswith('/')))
        for entry in sorted(children, key=lambda v: v.name):
            path = directory / entry.name
            rel = path.relative_to(source).as_posix()
            info = entry.stat(follow_symlinks=False)
            directory_entry = stat.S_ISDIR(info.st_mode)
            reason = 'secret_name_only' if secret(rel) else 'engine_paused' if engine(rel) else (
                'link_excluded' if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400 else (
                'excluded_directory' if entry.name.lower() in EXCLUDED and directory_entry else (
                'gitignored' if ignored(rel, directory_entry, local_rules) else None)))
            if reason:
                rows.append(dict(path=rel, kind='excluded', reason=reason))
            elif directory_entry:
                rows.append(dict(path=rel, kind='directory'))
                walk(path, local_rules, depth + 1)
            elif stat.S_ISREG(info.st_mode):
                rows.append(dict(path=rel, kind='file', bytes=info.st_size, mtime_ns=info.st_mtime_ns))
            else:
                rows.append(dict(path=rel, kind='excluded', reason='special_file'))
    walk(source, [], 0)
    suffixes = {Path(r['path']).suffix.lower() for r in rows if r['kind'] == 'file'}
    languages = [name for suffix, name in [('.py', 'Python'), ('.js', 'JavaScript'), ('.ts', 'TypeScript'),
                 ('.cs', 'C#'), ('.cpp', 'C++'), ('.gd', 'GDScript'), ('.html', 'HTML')] if suffix in suffixes]
    return dict(root=source.as_posix(), entries=rows, files=sum(r['kind'] == 'file' for r in rows),
                directories=sum(r['kind'] == 'directory' for r in rows), languages=languages,
                git_repository=any(r['path'] == '.git' for r in rows), basis='observed filenames and metadata',
                limits=dict(max_entries=MAX_ENTRIES, max_depth=MAX_DEPTH, max_file_read_bytes=MAX_READ,
                            max_total_read_bytes=MAX_READ_TOTAL),
                note='No source code or secret contents read. Git branch, remotes and dirty state are not inspected. '
                     'Ignored directories, dependency folders, links and engine paths are excluded. '
                     'Inventory metadata is an observation, not a verification of project behavior.')


def requests(folder):
    if not (Path(folder) / 'workspace-authority').exists():
        return []
    h = authority(folder)
    entries = h._entries()
    decisions = {e['request_ref']: e for e in entries if e['kind'] == 'owner_decision'}
    return [dict(ref=e['request_ref'], payload=load_request(h, e['request_ref']),
                 decision=decisions.get(e['request_ref']), origin='workspace')
            for e in entries if e['kind'] == 'owner_request']


def review_body(row):
    body = row['payload']['body']
    return body.get('workspace', body.get('workspace_apply'))


def output(h, run_id, stage):
    event = next((e for e in reversed(h._entries()) if e['kind'] == 'workspace_completed'
                  and e['run_id'] == run_id and e['stage'] == stage), None)
    if not event:
        raise ValueError('Complete the preceding workspace step first')
    path = run_folder(h, run_id) / (stage + '.json')
    direct(path)
    data = path.read_bytes()
    if sha256(data).hexdigest() != event['sha256']:
        raise ValueError('Workspace evidence changed')
    return read_json(path), path, event['sha256']


def status(folder):
    rows = requests(folder)
    if not rows:
        return dict(requests=[], latest=None)
    h = authority(folder)
    validate_history(h, h._entries())
    body = review_body(rows[-1])
    run_id = body['run_id']
    completed = [e for e in h._entries() if e['kind'] == 'workspace_completed' and e['run_id'] == run_id]
    saved = {e['stage']: output(h, run_id, e['stage'])[0] for e in completed}
    pending = next((r for r in rows if not r['decision']), None)
    latest = dict(run_id=run_id, source=body['source'], sandbox=body['sandbox'], **saved,
                  declined=bool(rows[-1]['decision'] and rows[-1]['decision']['choice'] == 'decline'),
                  resumable=rows[-1]['ref'] if rows[-1]['decision'] and rows[-1]['decision']['choice'] == 'approve'
                  and body['stage'] not in saved else None)
    return dict(requests=rows, pending=pending['ref'] if pending else None, latest=latest)


def prepare(folder, value=None, *, stage='scan', run_id=None):
    folder = Path(folder)
    with exclusive(folder / 'workspace.lock'):
        saved = status(folder)
        if saved.get('pending') or (stage != 'scan' and saved['latest'] and saved['latest']['resumable']):
            raise ValueError('Finish or discard the pending workspace step first')
        h = authority(folder)
        if stage == 'scan':
            source = source_path(folder, value)
            run_id = secrets.token_hex(8)
        else:
            if not saved['latest'] or run_id != saved['latest']['run_id'] or stage not in ('plan', 'apply'):
                raise ValueError('Choose the latest workspace scan')
            if saved['latest']['declined']:
                raise ValueError('Workspace step was discarded; prepare a fresh scan')
            source = source_path(folder, saved['latest']['source'])
        sandbox = sandbox_folder(h, run_id)
        dest = run_folder(h, run_id) / (stage + '.json')
        c = draft('ct-workspace-' + stage + '-' + run_id + '-0001', 'ember-workspace-host',
                  {'scan': 'Read-only workspace scan', 'plan': 'Prepare workspace setup diff',
                   'apply': 'Create the reviewed setup files in an isolated empty sandbox'}[stage], role='worker')
        c['allowed_paths'] = dict(read=[source.parent.as_posix() + '/' + source.name + '*', source.as_posix() + '/**', dest.parent.as_posix() + '/**'],
                                  write=[dest.parent.as_posix() + '/**'])
        c['requires_approval'].append('scaffold_write')
        c['limits']['max_calls'] = 300
        c['extensions']['workspace'] = dict(run_id=run_id, source=source.as_posix(), sandbox=sandbox.as_posix(), stage=stage)
        c['allowed_actions'] = [dict(action_id='scan', tool='workspace.scan', **{'class': 'read'},
            args_constraints=dict(root=dict(equals=source.as_posix())), allow_no_evidence=True),
            dict(action_id='inspect', tool='fs.read', **{'class': 'read'},
            args_constraints=dict(path=dict(path_within=source.as_posix() + '/**',
                pattern='^' + re.escape(source.as_posix()) + '/(?:' + '|'.join(re.escape(name) for name in FILES)
                        + r'|(?:[^/]+/)*\.gitignore)$')), allow_no_evidence=True)]
        secret_rule = r'^(?i:[\s\S]*/(?:' + '|'.join(glob_regex(p) for p in SECRET_PATTERNS) + r')(?:/[\s\S]*)?)$'
        engine_rule = r'^(?i:[\s\S]*/(?:engine|engines|wrathful[^/]*conquest)(?:/[\s\S]*)?)$'
        for rule in (secret_rule, engine_rule):
            c['forbidden_actions'].append(dict(tool='fs.read', args_constraints=dict(path=dict(pattern=rule))))
        # The host also checks every ancestor and excludes links before content reads.
        body = dict(c['extensions']['workspace'])
        if stage != 'scan':
            previous, pin, expected = output(h, run_id, 'scan' if stage == 'plan' else 'plan')
            c['inputs'] = [dict(name='workspace_' + ('scan' if stage == 'plan' else 'plan'), path=pin.as_posix(), sha256=expected)]
        if stage == 'apply':
            if 'apply' in (saved['latest'] or {}):
                raise ValueError('This sandbox setup is already complete')
            body['plan'] = previous
            c['allowed_paths']['write'] = [sandbox.parent.as_posix() + '/' + sandbox.name + '*', sandbox.as_posix() + '/**', dest.parent.as_posix() + '/**']
            targets = [(sandbox / r['path']).as_posix() for r in previous['entries'] if r['action'] == 'create']
            if not targets:
                raise ValueError('No new setup files to apply')
            args = dict(plan_sha256=digest(previous), dest=sandbox.as_posix(), paths=targets)
            c['allowed_actions'].append(dict(action_id='apply', tool='workspace.scaffold_apply', **{'class': 'scaffold_write'},
                args_constraints={k: dict(equals=v) for k, v in args.items()}, allow_no_evidence=False))
            c['required_evidence']['apply'] = [dict(kind='file_list', params=dict(expect_count=len(targets)))]
            body['action_args'] = args
        report_tool = 'workspace.scaffold_plan' if stage == 'plan' else 'workspace.write_report'
        c['allowed_actions'].append(dict(action_id='report', tool=report_tool, **{'class': 'write'},
            args_constraints=dict(dest=dict(equals=dest.as_posix()), expected_sha256=dict(pattern='^[0-9a-f]{64}$')),
            allow_no_evidence=False))
        c['required_evidence']['report'] = [dict(kind='file_hash', params={})]
        scope_id = 'ct-workspace-scope-' + run_id + '-0001'
        body['scope_id'] = scope_id
        records = []
        if stage == 'scan':
            ceiling = deepcopy(c)
            ceiling['id'] = scope_id
            ceiling['goal'] = 'Workspace onboarding: read-only source and reviewed sandbox setup'
            ceiling['extensions']['orchestration']['role'] = 'scope'
            ceiling['allowed_paths']['write'] += [sandbox.parent.as_posix() + '/' + sandbox.name + '*', sandbox.as_posix() + '/**']
            ceiling['limits']['max_calls'] = 1000
            now = datetime.now(timezone.utc)
            ceiling['limits']['time_window'] = dict(not_before=now.isoformat(), not_after=(now + timedelta(hours=4)).isoformat())
            ceiling['allowed_actions'] = [deepcopy(a) for a in c['allowed_actions'] if a['action_id'] != 'report']
            for tool in ('workspace.write_report', 'workspace.scaffold_plan'):
                ceiling['allowed_actions'].append(dict(action_id=tool.split('.')[1], tool=tool, **{'class': 'write'},
                    args_constraints=dict(dest=dict(path_within=dest.parent.as_posix() + '/**'),
                                          expected_sha256=dict(pattern='^[0-9a-f]{64}$')), allow_no_evidence=True))
            ceiling['allowed_actions'].append(dict(action_id='apply', tool='workspace.scaffold_apply', **{'class': 'scaffold_write'},
                args_constraints=dict(dest=dict(path_within=sandbox.parent.as_posix() + '/*'),
                                      plan_sha256=dict(pattern='^[0-9a-f]{64}$')), allow_extra_args=True, allow_no_evidence=True))
            ceiling['required_evidence'] = {}
            h.save_draft(ceiling)
            records.append(dict(contract=ceiling, parent_id=None))
        else:
            active = h._active(h._entries())
            ceiling = h._authority(active[scope_id], active)
        c['limits']['time_window'] = deepcopy(ceiling['limits']['time_window'])
        validate(c)
        h.save_draft(c)
        records.append(dict(contract=c, parent_id=scope_id))
        ref = OwnerReview()._request(h, 'contracts', dict(contracts=records, workspace=body), wait=False)
        return dict(request_ref=ref)


def make_plan(h, c, source, report, sandbox):
    current = inventory(h, c, source)
    if current != report:
        raise ValueError('Workspace changed since scanning; prepare a new scan')
    entries, budget = [], [0]
    for name, content in FILES.items():
        path = source / name
        direct(path)
        expected = sha256(content.encode()).hexdigest()
        existing = sha256(read_safe(h, c, source, name, budget)).hexdigest() if path.exists() else None
        kind = 'create' if existing is None else 'skip_exists' if existing == expected else 'conflict'
        entries.append(dict(path=name, action=kind, content=content, content_sha256=expected,
                            bytes=len(content.encode()), before_sha256=existing))
    manual = '# Review LFS routing separately before enabling it.\n'
    entries.append(dict(path='.gitattributes', action='manual', content=manual,
                        content_sha256=sha256(manual.encode()).hexdigest(), bytes=len(manual.encode()),
                        before_sha256=None))
    return dict(source=source.as_posix(), sandbox=sandbox, scan_sha256=digest(report), entries=entries,
                note='Only create entries will be written into the isolated empty sandbox. Existing source files are never copied or changed. '
                     'Conflicts and identical files are listed and omitted. LFS configuration stays manual.')


def respond(folder, ref, choice, quote):
    with exclusive(Path(folder) / 'workspace.lock'):
        h = authority(folder)
        rows = requests(folder)
        row = next((r for r in rows if r['ref'] == ref), None)
        if row is None or row != rows[-1]:
            raise ValueError('Choose the current workspace review')
        body = review_body(row)
        if row['decision']:
            if choice != 'approve' or row['decision']['choice'] != 'approve':
                raise ValueError('Workspace review already decided')
        else:
            decide(h, ref, choice, quote)
        if choice == 'decline':
            return dict(status='declined')
        payload = row['payload']['body']
        cid = payload['contracts'][-1]['contract']['id'] if 'contracts' in payload else payload['action']['contract_id']
        return execute(folder, h, body, cid)


def execute(folder, h, body, cid):
    active = h._active(h._entries())
    c = h._authority(active[cid], active)
    run_id, stage = body['run_id'], body['stage']
    if any(e['kind'] == 'workspace_completed' and e['run_id'] == run_id and e['stage'] == stage for e in h._entries()):
        result = output(h, run_id, stage)[0]
        if stage == 'apply':
            for file in result['files']:
                path = direct(file['path'])
                if not path.is_file() or sha256(path.read_bytes()).hexdigest() != file['sha256']:
                    raise ValueError('Sandbox output changed since completion')
        return dict(status='completed', result=result)
    source = source_path(folder, body['source'])
    if c['inputs'] and not h.verify_inputs(cid):
        raise ValueError('Workspace evidence changed; inputs_unverified')
    if stage == 'scan':
        result = inventory(h, c, source)
    elif stage == 'plan':
        result = make_plan(h, c, source, output(h, run_id, 'scan')[0], body['sandbox'])
    else:
        result = apply(h, c, body)
        if 'awaiting_action' in result:
            return result
    dest = run_folder(h, run_id) / (stage + '.json')
    direct(dest)
    data = canonical(result)
    expected = sha256(data).hexdigest()
    tool = 'workspace.scaffold_plan' if stage == 'plan' else 'workspace.write_report'
    allowed = permitted(h, c, tool, dict(dest=dest.as_posix(), expected_sha256=expected))
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if dest.read_bytes() != data:
            raise ValueError('Workspace output changed; refusing overwrite')
    else:
        with dest.open('xb') as stream:
            stream.write(data)
    evidence = h.verify_evidence(cid, 'report', [dict(kind='file_hash', params=dict(path=dest.as_posix(), sha256=expected))],
                                 decision_seq=allowed['audit_seq'])
    if evidence['status'] != 'complete':
        raise ValueError('Workspace report evidence did not verify')
    with h._lock():
        h._append('workspace_completed', run_id=run_id, stage=stage, sha256=expected, contract_id=cid)
    return dict(status='completed', result=result)


def apply(h, c, body):
    plan = body['plan']
    saved, _, _ = output(h, body['run_id'], 'plan')
    if saved != plan or digest(plan) != body['action_args']['plan_sha256']:
        raise ValueError('Reviewed setup plan changed')
    report = output(h, body['run_id'], 'scan')[0]
    if inventory(h, c, Path(body['source'])) != report:
        raise ValueError('Workspace changed since scanning; prepare a new scan')
    for entry in plan['entries']:
        if entry['action'] == 'manual':
            continue
        path = direct(Path(body['source']) / entry['path'])
        existing = sha256(read_safe(h, c, Path(body['source']), entry['path'], [0])).hexdigest() if path.exists() else None
        if existing != entry['before_sha256']:
            raise ValueError('Workspace setup inputs changed; prepare a new scan')
    sandbox = direct(body['sandbox'])
    if sandbox != sandbox_folder(h, body['run_id']):
        raise ValueError('Sandbox destination changed')
    act = action(c, 'workspace.scaffold_apply', body['action_args'],
                 [(sandbox / r['path']).as_posix() for r in plan['entries'] if r['action'] == 'create'])
    entries = h._entries()
    prior = next((e for e in reversed(entries) if e['kind'] == 'decision' and e.get('decision') == 'allow'
                  and e.get('action') == act), None)
    # Preflight the entire set before the one-time action or any mkdir/write.
    targets = [(sandbox / r['path'], r) for r in plan['entries'] if r['action'] == 'create']
    expected_paths = {p for p, _ in targets}
    expected_dirs = {parent for p in expected_paths for parent in p.parents if parent.is_relative_to(sandbox)}
    if sandbox.exists():
        for directory, dirs, files in os.walk(sandbox, followlinks=False):
            for name in dirs + files:
                path = direct(Path(directory) / name)
                if path not in expected_paths | expected_dirs:
                    raise ValueError('Sandbox changed: unexpected path; choose a new scan')
    for target, entry in targets:
        direct(target)
        if target.exists() and (prior is None or not target.is_file() or target.read_bytes() != entry['content'].encode()):
            raise ValueError('Sandbox changed at a planned path; refusing overwrite')
    if prior is None:
        if not any(e['kind'] == 'owner_request' and load_request(h, e['request_ref'])['body'].get('action') == act for e in entries):
            return dict(awaiting_action=OwnerReview()._request(h, 'action', dict(action=act, contract_hash=c['content_hash'], workspace_apply=body), wait=False))
        allowed = h.check(act)
        if allowed['decision'] != 'allow':
            raise ValueError('Review the exact sandbox action before applying')
        prior = dict(seq=allowed['audit_seq'])
    files = []
    for target, entry in targets:
        direct(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with target.open('xb') as stream:
                stream.write(entry['content'].encode())
        if target.read_bytes() != entry['content'].encode():
            raise ValueError('Sandbox output changed')
        files.append(dict(path=target.as_posix(), size=entry['bytes'], sha256=entry['content_sha256']))
    evidence = h.verify_evidence(c['id'], 'apply', [dict(kind='file_list', params=dict(files=files))], decision_seq=prior['seq'])
    if evidence['status'] != 'complete':
        raise ValueError('Sandbox setup evidence did not verify')
    return dict(sandbox=sandbox.as_posix(), files=files, plan_sha256=digest(plan), basis='verified exact created bytes')
