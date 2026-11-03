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
IMPORT_PROFILE = 'flat-browser-v1'
MAX_IMPORT_TOTAL = 262144
GIT_HEAD_REF = r'refs/heads/(?![a-zA-Z0-9_./-]*\.\.)[a-zA-Z0-9][a-zA-Z0-9_./-]{0,240}'
ASSET_SUFFIXES = {'.png': 'image', '.jpg': 'image', '.jpeg': 'image', '.webp': 'image',
                  '.svg': 'image', '.gif': 'image', '.wav': 'audio', '.mp3': 'audio',
                  '.ogg': 'audio', '.glb': 'model', '.gltf': 'model', '.blend': 'model',
                  '.fbx': 'model', '.obj': 'model'}


def authority(folder):
    return Harness(Path(folder) / 'workspace-authority')


def run_folder(h, run_id):
    return h.root.parent / 'workspace-runs' / run_id


def sandbox_folder(h, run_id):
    return h.root.parent / 'workspace-sandboxes' / run_id


def import_folder(h, run_id):
    return h.root.parent / 'workspace-imports' / run_id


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
    if not path.is_file() or path.stat().st_size > MAX_READ or path.stat().st_nlink > 1:
        raise ValueError('Workspace content must be a direct single-link file within the 64 KiB read limit')
    with path.open('rb') as stream:
        data = stream.read(MAX_READ + 1)
    budget[0] += len(data)
    if len(data) > MAX_READ or budget[0] > MAX_READ_TOTAL:
        raise ValueError('Workspace content read budget exceeded')
    return data


def git_inventory(h, c, source, rows, budget):
    """Passive bounded metadata only: no Git executable, config, index or hooks."""
    entry = next((row for row in rows if row['path'] == '.git'), None)
    result = dict(present=entry is not None, branch=None, commit=None,
                  worktree_state='not_inspected', remotes='not_inspected',
                  basis='bounded passive HEAD and branch-reference observations')
    if entry is None:
        return dict(result, state='absent')
    if entry.get('reason') == 'link_excluded' or not (source / '.git').is_dir():
        return dict(result, state='unsupported_metadata',
                    note='Linked/external Git directories and worktree pointer files are not followed.')
    head = source / '.git/HEAD'
    direct(head)
    if not head.is_file():
        return dict(result, state='missing_head')
    raw = read_safe(h, c, source, '.git/HEAD', budget)
    result['head_sha256'] = sha256(raw).hexdigest()
    text = raw.decode('ascii', errors='replace').strip()
    if re.fullmatch('[0-9a-fA-F]{40}|[0-9a-fA-F]{64}', text):
        return dict(result, state='detached', commit=text.lower())
    if not re.fullmatch('ref: ' + GIT_HEAD_REF, text):
        return dict(result, state='unsupported_head')
    ref = text[5:]
    if any(part in ('', '.', '..') or part.startswith('.') for part in ref.split('/')) or '..' in ref or secret(ref):
        return dict(result, state='unsupported_head')
    result['branch'] = ref.removeprefix('refs/heads/')
    loose = source / '.git' / ref
    direct(loose)
    if loose.exists():
        raw = read_safe(h, c, source, '.git/' + ref, budget)
        result['reference_sha256'] = sha256(raw).hexdigest()
        commit = raw.decode('ascii', errors='replace').strip()
        return dict(result, state='branch' if re.fullmatch('[0-9a-fA-F]{40}|[0-9a-fA-F]{64}', commit) else 'unsupported_reference',
                    commit=commit.lower() if re.fullmatch('[0-9a-fA-F]{40}|[0-9a-fA-F]{64}', commit) else None)
    packed = source / '.git/packed-refs'
    direct(packed)
    if packed.exists():
        raw = read_safe(h, c, source, '.git/packed-refs', budget)
        result['packed_refs_sha256'] = sha256(raw).hexdigest()
        for line in raw.decode('ascii', errors='replace').splitlines():
            value, _, name = line.partition(' ')
            if name == ref and re.fullmatch('[0-9a-fA-F]{40}|[0-9a-fA-F]{64}', value):
                return dict(result, state='branch', commit=value.lower())
    return dict(result, state='unborn_or_missing_reference')


def project_inventory(rows):
    """Filename hints never establish validity, compatibility or asset acceptance."""
    from .chat_build import PATH_PATTERN
    files = [row for row in rows if row['kind'] == 'file']
    browser = [row['path'] for row in files if re.fullmatch(PATH_PATTERN, row['path'])]
    assets = [dict(path=row['path'], kind=ASSET_SUFFIXES[Path(row['path']).suffix.lower()], bytes=row['bytes'])
              for row in files if Path(row['path']).suffix.lower() in ASSET_SUFFIXES]
    return dict(browser_profile=IMPORT_PROFILE, browser_candidates=browser,
                has_root_index='index.html' in browser, assets=assets,
                paused_engine_paths=[row['path'] for row in rows if row.get('reason') == 'engine_paused'],
                engine_hints=[row['path'] for row in files if Path(row['path']).suffix.lower() in ('.uproject', '.unity', '.godot')],
                basis='observed names, suffixes and sizes only; import validation and individual asset acceptance remain separate')


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
    git = git_inventory(h, c, source, rows, budget)
    return dict(root=source.as_posix(), entries=rows, files=sum(r['kind'] == 'file' for r in rows),
                directories=sum(r['kind'] == 'directory' for r in rows), languages=languages,
                git_repository=any(r['path'] == '.git' for r in rows), basis='observed filenames and metadata',
                git=git, project=project_inventory(rows),
                limits=dict(max_entries=MAX_ENTRIES, max_depth=MAX_DEPTH, max_file_read_bytes=MAX_READ,
                            max_total_read_bytes=MAX_READ_TOTAL),
                note='No source code, Git config, hooks or secret contents read. Passive Git HEAD/reference metadata is bounded; remotes and dirty state are not inspected. '
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
                  import_sandbox=body.get('import_sandbox', import_folder(h, run_id).as_posix()),
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
            if not saved['latest'] or run_id != saved['latest']['run_id'] or stage not in ('plan', 'apply', 'import_plan', 'import_apply'):
                raise ValueError('Choose the latest workspace scan')
            if saved['latest']['declined']:
                raise ValueError('Workspace step was discarded; prepare a fresh scan')
            source = source_path(folder, saved['latest']['source'])
        sandbox = sandbox_folder(h, run_id)
        imported = import_folder(h, run_id)
        dest = run_folder(h, run_id) / (stage + '.json')
        c = draft('ct-workspace-' + stage.replace('_', '-') + '-' + run_id + '-0001', 'ember-workspace-host',
                  {'scan': 'Read-only workspace scan', 'plan': 'Prepare workspace setup diff',
                   'apply': 'Create the reviewed setup files in an isolated empty sandbox',
                   'import_plan': 'Read and validate bounded browser source for exact import review',
                   'import_apply': 'Copy exact reviewed browser source into a separate isolated sandbox'}[stage], role='worker')
        c['allowed_paths'] = dict(read=[source.parent.as_posix() + '/' + source.name + '*', source.as_posix() + '/**', dest.parent.as_posix() + '/**'],
                                  write=[dest.parent.as_posix() + '/**'])
        c['requires_approval'].append('scaffold_write')
        c['limits']['max_calls'] = 300
        c['extensions']['workspace'] = dict(run_id=run_id, source=source.as_posix(), sandbox=sandbox.as_posix(),
                                             import_sandbox=imported.as_posix(), stage=stage)
        c['allowed_actions'] = [dict(action_id='scan', tool='workspace.scan', **{'class': 'read'},
            args_constraints=dict(root=dict(equals=source.as_posix())), allow_no_evidence=True),
            dict(action_id='inspect', tool='fs.read', **{'class': 'read'},
            args_constraints=dict(path=dict(path_within=source.as_posix() + '/**',
                pattern='^' + re.escape(source.as_posix()) + '/(?:' + '|'.join(re.escape(name) for name in FILES)
                        + r'|(?:[^/]+/)*\.gitignore|\.git/(?:HEAD|packed-refs|' + GIT_HEAD_REF + r'))$')), allow_no_evidence=True)]
        source_read = dict(action_id='import_read', tool='fs.read', **{'class': 'read'},
            args_constraints=dict(path=dict(path_within=source.as_posix() + '/**',
                pattern='^' + re.escape(source.as_posix()) + r'/[a-z][a-z0-9_-]{0,63}\.(?:html|css|js)$')),
            allow_no_evidence=True)
        if stage in ('import_plan', 'import_apply'):
            c['allowed_actions'].append(deepcopy(source_read))
        secret_rule = r'^(?i:[\s\S]*/(?:' + '|'.join(glob_regex(p) for p in SECRET_PATTERNS) + r')(?:/[\s\S]*)?)$'
        engine_rule = r'^(?i:[\s\S]*/(?:engine|engines|wrathful[^/]*conquest)(?:/[\s\S]*)?)$'
        for rule in (secret_rule, engine_rule):
            c['forbidden_actions'].append(dict(tool='fs.read', args_constraints=dict(path=dict(pattern=rule))))
        # The host also checks every ancestor and excludes links before content reads.
        body = dict(c['extensions']['workspace'])
        if stage != 'scan':
            preceding = {'plan': 'scan', 'apply': 'plan', 'import_plan': 'scan', 'import_apply': 'import_plan'}[stage]
            previous, pin, expected = output(h, run_id, preceding)
            c['inputs'] = [dict(name='workspace_' + preceding, path=pin.as_posix(), sha256=expected)]
        if stage in ('apply', 'import_apply'):
            if stage in (saved['latest'] or {}):
                raise ValueError('This sandbox setup is already complete')
            body['plan'] = previous
            target_folder = imported if stage == 'import_apply' else sandbox
            c['allowed_paths']['write'] = [target_folder.parent.as_posix() + '/' + target_folder.name + '*', target_folder.as_posix() + '/**', dest.parent.as_posix() + '/**']
            targets = [(target_folder / r['path']).as_posix() for r in previous['entries'] if r['action'] == 'create']
            if not targets:
                raise ValueError('No new setup files to apply')
            if stage == 'import_apply':
                c['inputs'] += [dict(name='source_' + row['path'].replace('.', '_'),
                    path=(source / row['path']).as_posix(), sha256=row['content_sha256']) for row in previous['entries']]
            args = dict(plan_sha256=digest(previous), dest=target_folder.as_posix(), paths=targets)
            c['allowed_actions'].append(dict(action_id='apply', tool='workspace.scaffold_apply', **{'class': 'scaffold_write'},
                args_constraints={k: dict(equals=v) for k, v in args.items()}, allow_no_evidence=False))
            c['required_evidence']['apply'] = [dict(kind='file_list', params=dict(expect_count=len(targets)))]
            body['action_args'] = args
        report_tool = 'workspace.scaffold_plan' if stage in ('plan', 'import_plan') else 'workspace.write_report'
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
            ceiling['goal'] = 'Workspace onboarding: inventory, reviewed setup and bounded browser import to isolated sandboxes'
            ceiling['extensions']['orchestration']['role'] = 'scope'
            ceiling['allowed_paths']['write'] += [sandbox.parent.as_posix() + '/' + sandbox.name + '*', sandbox.as_posix() + '/**',
                                                 imported.parent.as_posix() + '/' + imported.name + '*', imported.as_posix() + '/**']
            ceiling['allowed_paths']['read'] += [Path(__file__).with_name(name).resolve().as_posix() + '*'
                                                 for name in ('workspace.py', 'chat_build.py')]
            ceiling['limits']['max_calls'] = 1000
            now = datetime.now(timezone.utc)
            ceiling['limits']['time_window'] = dict(not_before=now.isoformat(), not_after=(now + timedelta(hours=4)).isoformat())
            ceiling['allowed_actions'] = [deepcopy(a) for a in c['allowed_actions'] if a['action_id'] != 'report']
            ceiling['allowed_actions'].append(deepcopy(source_read))
            for tool in ('workspace.write_report', 'workspace.scaffold_plan'):
                ceiling['allowed_actions'].append(dict(action_id=tool.split('.')[1], tool=tool, **{'class': 'write'},
                    args_constraints=dict(dest=dict(path_within=dest.parent.as_posix() + '/**'),
                                          expected_sha256=dict(pattern='^[0-9a-f]{64}$')), allow_no_evidence=True))
            ceiling['allowed_actions'].append(dict(action_id='apply', tool='workspace.scaffold_apply', **{'class': 'scaffold_write'},
                args_constraints=dict(dest=dict(one_of=[sandbox.as_posix(), imported.as_posix()]),
                                      plan_sha256=dict(pattern='^[0-9a-f]{64}$')), allow_extra_args=True, allow_no_evidence=True))
            ceiling['required_evidence'] = {}
            h.save_draft(ceiling)
            records.append(dict(contract=ceiling, parent_id=None))
        else:
            active = h._active(h._entries())
            ceiling = h._authority(active[scope_id], active)
            if stage in ('import_plan', 'import_apply') and not any(a['action_id'] == 'import_read' for a in ceiling['allowed_actions']):
                raise ValueError('Prepare and approve a fresh workspace scan before reviewing source import permissions')
        if stage in ('import_plan', 'import_apply'):
            for name in ('workspace.py', 'chat_build.py'):
                module = Path(__file__).with_name(name).resolve()
                c['allowed_paths']['read'].append(module.as_posix() + '*')
                c['inputs'].append(dict(name='host_' + name.replace('.', '_'), path=module.as_posix(),
                                        sha256=sha256(module.read_bytes()).hexdigest()))
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


def make_import_plan(h, c, source, report, sandbox):
    from . import chat_build
    if inventory(h, c, source) != report:
        raise ValueError('Workspace changed since scanning; prepare a new scan')
    names = [row['path'] for row in report['entries'] if row['kind'] == 'file'
             and re.fullmatch(chat_build.PATH_PATTERN, row['path'])]
    if not names or 'index.html' not in names or len(names) > chat_build.MAX_FILES:
        raise ValueError('Browser import needs a root index.html and at most eight flat lowercase HTML/CSS/JavaScript files')
    files, budget = {}, [0]
    for name in names:
        raw = read_safe(h, c, source, name, budget)
        if budget[0] > MAX_IMPORT_TOTAL:
            raise ValueError('Browser import exceeds the 256 KiB total source limit')
        if b'\0' in raw:
            raise ValueError('Browser import requires UTF-8 text files without binary NUL bytes')
        files[name] = raw.decode('utf-8')
    chat_build.validate_files(files)
    destination = direct(sandbox)
    conflicts = ['destination_exists'] if destination.exists() else []
    entries = [dict(path=name, action='conflict' if conflicts else 'create', content=content,
                    content_sha256=sha256(content.encode('utf-8')).hexdigest(),
                    before_sha256=None, bytes=len(content.encode('utf-8'))) for name, content in sorted(files.items())]
    return dict(profile=IMPORT_PROFILE, source=source.as_posix(), sandbox=destination.as_posix(),
                scan_sha256=digest(report), entries=entries,
                manifest={row['path']: row['content_sha256'] for row in entries},
                destination_expected_absent=True, destination_conflicts=conflicts,
                omitted=[dict(path=row['path'], reason=row.get('reason', 'outside_flat_browser_profile'))
                         for row in report['entries'] if row['path'] not in names],
                limits=dict(max_files=chat_build.MAX_FILES, max_file_bytes=MAX_READ,
                            max_total_source_bytes=MAX_IMPORT_TOTAL),
                note='Validated source structure only; no source is executed. Exact bytes are copied only to the separate import sandbox '
                     'after contract and action approval. This does not change the current game, approve assets or establish gameplay quality. '
                     'Nested sources, standalone asset files, dependency installation and engine imports are unsupported.')


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
        if stage == 'import_apply':
            imported_files(folder, run_id)
        elif stage == 'apply':
            for file in result['files']:
                path = direct(file['path'])
                if not path.is_file() or sha256(path.read_bytes()).hexdigest() != file['sha256']:
                    raise ValueError('Sandbox output changed since completion')
        return dict(status='completed', result=result)
    source = source_path(folder, body['source'])
    if stage == 'import_apply':
        for row in body['plan']['entries']:
            path = direct(source / row['path'])
            if not path.is_file() or path.stat().st_nlink > 1 or path.stat().st_size > MAX_READ:
                raise ValueError('Reviewed import source changed or is not a bounded direct file')
    if c['inputs'] and not h.verify_inputs(cid):
        raise ValueError('Workspace evidence changed; inputs_unverified')
    if stage == 'scan':
        result = inventory(h, c, source)
    elif stage == 'plan':
        result = make_plan(h, c, source, output(h, run_id, 'scan')[0], body['sandbox'])
    elif stage == 'import_plan':
        result = make_import_plan(h, c, source, output(h, run_id, 'scan')[0], body['import_sandbox'])
    else:
        result = apply(h, c, body)
        if 'awaiting_action' in result:
            return result
    dest = run_folder(h, run_id) / (stage + '.json')
    direct(dest)
    data = canonical(result)
    expected = sha256(data).hexdigest()
    tool = 'workspace.scaffold_plan' if stage in ('plan', 'import_plan') else 'workspace.write_report'
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
    importing = body['stage'] == 'import_apply'
    saved, _, _ = output(h, body['run_id'], 'import_plan' if importing else 'plan')
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
        if existing != entry['content_sha256' if importing else 'before_sha256']:
            raise ValueError('Workspace setup inputs changed; prepare a new scan')
    sandbox = direct(body['import_sandbox'] if importing else body['sandbox'])
    if sandbox != (import_folder if importing else sandbox_folder)(h, body['run_id']):
        raise ValueError('Sandbox destination changed')
    act = action(c, 'workspace.scaffold_apply', body['action_args'],
                 [(sandbox / r['path']).as_posix() for r in plan['entries'] if r['action'] == 'create'])
    entries = h._entries()
    prior = next((e for e in reversed(entries) if e['kind'] == 'decision' and e.get('decision') == 'allow'
                  and e.get('action') == act), None)
    if importing and prior is None and sandbox.exists():
        raise ValueError('Sandbox changed since import planning; refusing an existing destination')
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
    return dict(sandbox=sandbox.as_posix(), files=files, plan_sha256=digest(plan), basis='verified exact created bytes',
                **(dict(profile=IMPORT_PROFILE, manifest=plan['manifest'], source_snapshot=True) if importing else {}))


def imported_files(folder, run_id):
    """Return only a completed exact copy; adoption is a separate scoped build."""
    from . import chat_build
    if not isinstance(run_id, str) or not re.fullmatch('[a-f0-9]{16}', run_id):
        raise ValueError('Choose a completed workspace import')
    h = authority(folder)
    validate_history(h, h._entries())
    plan = output(h, run_id, 'import_plan')[0]
    result = output(h, run_id, 'import_apply')[0]
    sandbox = direct(import_folder(h, run_id))
    if (result.get('profile') != IMPORT_PROFILE or result.get('manifest') != plan['manifest']
            or result['sandbox'] != sandbox.as_posix() or plan['sandbox'] != sandbox.as_posix()
            or result['plan_sha256'] != digest(plan) or plan['destination_conflicts']):
        raise ValueError('Reviewed import evidence changed')
    expected = {row['path']: row for row in plan['entries']}
    if not sandbox.is_dir():
        raise ValueError('Imported sandbox is missing')
    with os.scandir(sandbox) as stream:
        actual = set()
        for entry in stream:
            actual.add(entry.name)
            if entry.name not in expected or len(actual) > len(expected):
                raise ValueError('Imported sandbox changed: unexpected path')
    if actual != set(expected):
        raise ValueError('Imported sandbox changed: missing file')
    files = {}
    for name, row in expected.items():
        path = direct(sandbox / name)
        if not path.is_file() or path.stat().st_nlink > 1 or path.stat().st_size != row['bytes']:
            raise ValueError('Imported sandbox file changed')
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != row['content_sha256']:
            raise ValueError('Imported sandbox bytes changed')
        files[name] = raw.decode('utf-8')
    expected_receipts = [dict(path=(sandbox / name).as_posix(), size=row['bytes'], sha256=row['content_sha256'])
                         for name, row in expected.items()]
    if result['files'] != expected_receipts:
        raise ValueError('Imported sandbox receipt changed')
    chat_build.validate_files(files)
    return files
