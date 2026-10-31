"""Exact browser-prototype proposals, human review, and gated local application."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from difflib import unified_diff
from hashlib import sha256
from html.parser import HTMLParser
from base64 import b64encode
import os
from pathlib import Path
import re

from jsonschema import Draft202012Validator

from .core import Harness, digest, timestamp
from .owner_review import OwnerReview, decide, load_request, validate_history
from .recovery import exclusive
from .scope import propose

MAX_FILES = 8
PATH_PATTERN = r'^[a-z][a-z0-9_-]{0,63}\.(html|css|js)$'

BUILD_SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['title', 'summary', 'files'],
    'properties': {
        'title': {'type': 'string', 'minLength': 1, 'maxLength': 160},
        'summary': {'type': 'string', 'minLength': 1, 'maxLength': 2000},
        'files': {'type': 'array', 'minItems': 1, 'maxItems': MAX_FILES, 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['path', 'content'],
            'properties': {'path': {'type': 'string', 'pattern': PATH_PATTERN},
                           'content': {'type': 'string', 'minLength': 1, 'maxLength': 65536}}}},
    },
}
CHAT_SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['message', 'build'],
    'properties': {'message': {'type': 'string', 'minLength': 1, 'maxLength': 8000},
                   'build': {'anyOf': [BUILD_SCHEMA, {'type': 'null'}]}},
}


def harness(folder):
    return Harness(Path(folder) / 'build-authority')


def project(root, folder):
    session_id = Path(folder).name
    if not re.fullmatch('[0-9a-f]{24}', session_id):
        raise ValueError('A saved session is required for building')
    destination = Path(root).resolve() / '.harness/projects' / session_id
    if destination.resolve() != destination or destination.is_symlink():
        raise ValueError('Project path changed or escaped the session')
    return destination


def file_hash(path):
    if path.is_symlink():
        raise ValueError('Build target cannot be a symbolic link')
    return sha256(path.read_bytes()).hexdigest() if path.exists() else None


class HTMLCheck(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.html = self.body = False

    def handle_starttag(self, tag, attrs):
        self.html |= tag == 'html'
        self.body |= tag == 'body'


def validate_html(content):
    if len(content.encode('utf-8')) > 65536:
        raise ValueError('Browser prototype exceeds the file size limit')
    parser = HTMLCheck()
    parser.feed(content)
    parser.close()
    if not parser.html or not parser.body:
        raise ValueError('A complete HTML document with html and body elements is required')


def context(root, folder):
    destination = project(root, folder)
    files = {}
    if destination.exists():
        for target in sorted(destination.iterdir()):
            if not re.fullmatch(PATH_PATTERN, target.name) or not target.is_file():
                raise ValueError('Project contains an unsupported file or directory; inspection required')
            file_hash(target)
            files[target.name] = target.read_bytes().decode('utf-8')
    validate_files(files, empty=True)
    manifest = {name: sha256(content.encode('utf-8')).hexdigest() for name, content in files.items()}
    return dict(workspace_kind='browser project', file='index.html',
                sha256=manifest_hash(manifest), content=files.get('index.html'),
                files=[dict(path=name, content=content) for name, content in files.items()], manifest=manifest)


def manifest_hash(manifest):
    # Preserve the existing single-file context and cached-turn representation.
    if set(manifest) <= {'index.html'}:
        return manifest.get('index.html')
    return digest(manifest)


def validate_files(files, *, empty=False):
    if empty and not files:
        return
    if not 1 <= len(files) <= MAX_FILES or 'index.html' not in files:
        raise ValueError('A browser project requires index.html and at most eight files')
    if any(not re.fullmatch(PATH_PATTERN, name) for name in files):
        raise ValueError('Use flat lowercase HTML, CSS and JavaScript file names')
    sizes = [len(content.encode('utf-8')) for content in files.values()]
    if any(size > 65536 for size in sizes) or sum(sizes) > 262144:
        raise ValueError('Browser project exceeds the file or total size limit')
    for name, content in files.items():
        if name.endswith('.html'):
            validate_html(content)
            ResourcePreview(files).feed(content)


class ResourcePreview(HTMLParser):
    """Embed reviewed local resources without exposing a project HTTP file server."""
    def __init__(self, files):
        super().__init__(convert_charrefs=False)
        self.files, self.output = files, []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'base':
            raise ValueError('Browser projects cannot change the base URL')
        resource = values.get('src') if tag == 'script' else values.get('href') if tag == 'link' and 'stylesheet' in (values.get('rel') or '').split() else None
        if tag == 'script' and values.get('type') == 'module':
            raise ValueError('Use classic JavaScript scripts; module imports are not supported yet')
        original = self.get_starttag_text()
        if resource is not None:
            name = resource.removeprefix('./')
            extension = '.js' if tag == 'script' else '.css'
            if name not in self.files or not name.endswith(extension):
                raise ValueError('Script and stylesheet references must name an included local file')
            mime = 'text/javascript' if tag == 'script' else 'text/css'
            url = 'data:' + mime + ';base64,' + b64encode(self.files[name].encode('utf-8')).decode('ascii')
            # Rebuild attributes so unusual quoting cannot affect replacement.
            from html import escape
            attrs = [(key, url if key == ('src' if tag == 'script' else 'href') else value) for key, value in attrs]
            original = '<' + tag + ''.join(' ' + key + ('="' + escape(value, quote=True) + '"' if value is not None else '') for key, value in attrs) + '>'
        self.output.append(original)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        self.output.append('</' + tag + '>')

    def handle_data(self, data):
        self.output.append(data)

    def handle_entityref(self, name):
        self.output.append('&' + name + ';')

    def handle_charref(self, name):
        self.output.append('&#' + name + ';')

    def handle_comment(self, data):
        self.output.append('<!--' + data + '-->')

    def handle_decl(self, decl):
        self.output.append('<!' + decl + '>')


def propose_build(root, folder, turn_id, intent, build, *, expected_before=None, restore_from=None):
    Draft202012Validator(BUILD_SCHEMA).validate(build)
    files = {item['path']: item['content'] for item in build['files']}
    if len(files) != len(build['files']):
        raise ValueError('Duplicate file paths in browser project')
    validate_files(files)
    h = harness(folder)
    destination = project(root, folder)
    target = destination / 'index.html'
    existing = list_requests(folder)
    previous = next((r for r in existing if r['payload']['body']['build']['turn_id'] == turn_id), None)
    if previous:
        saved = previous['payload']['body']['build']
        proposed = {name: sha256(value.encode('utf-8')).hexdigest() for name, value in files.items()}
        if saved.get('manifest', {'index.html': saved['after_sha256']}) != proposed or saved.get('restore_from') != restore_from:
            raise ValueError('The saved turn already has a different build proposal')
        return previous['ref']
    if any(not r['decision'] for r in existing):
        raise ValueError('Approve or decline the pending build before proposing another change')
    if status(root, folder)['resumable']:
        raise ValueError('Resume the approved build before proposing another change')
    current = context(root, folder)
    if current['sha256'] != expected_before:
        raise ValueError('Project changed while Muse was preparing the build; ask for a fresh proposal')
    old_files = {item['path']: item['content'] for item in current['files']}
    if set(old_files) - set(files):
        raise ValueError('Include every existing project file; file deletion is not supported')
    manifest = {name: sha256(value.encode('utf-8')).hexdigest() for name, value in files.items()}
    rows = [dict(name=name, path=(destination / name).as_posix(),
                 before_sha256=current['manifest'].get(name), after_sha256=manifest[name])
            for name in sorted(files) if files[name] != old_files.get(name)]
    if not rows:
        raise ValueError('The proposed build is identical to the current project')
    before, after = current['manifest'].get('index.html'), manifest['index.html']
    suffix = digest(dict(turn=turn_id, build=build))[:12]
    scope = propose('ct-chat-scope-' + suffix + '-0001', 'muse-build-planner', intent, destination)
    scope['allowed_paths'] = dict(read=[destination.as_posix() + '/**'], write=[destination.as_posix() + '/**'])
    scope['goal'] = 'Build a local browser prototype: ' + build['title']
    now = datetime.now(timezone.utc)
    scope['limits'] = dict(spend_usd=0, max_calls=MAX_FILES + 2,
                           time_window=dict(not_before=now.isoformat(), not_after=(now + timedelta(hours=24)).isoformat()))
    scope['approval_mode'] = 'approve_all'
    scope['allowed_actions'], scope['required_evidence'] = [], {}
    for index, row in enumerate(rows):
        row['action_id'] = 'write' if len(rows) == 1 else 'write-' + str(index + 1)
        scope['allowed_actions'].append(dict(action_id=row['action_id'], tool='fs.write', **{'class': 'write'},
            args_constraints=dict(path={'equals': row['path']}, content={'equals': files[row['name']]})))
        scope['required_evidence'][row['action_id']] = [dict(kind='file_hash', params=dict(path=row['path'], sha256=row['after_sha256']))]
    scope['inputs'] = []
    for name, before_text in old_files.items():
        snapshot = h.root / 'build-inputs' / suffix / name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(before_text.encode('utf-8'))
        pattern = snapshot.parent.as_posix() + '/**'
        if pattern not in scope['allowed_paths']['read']:
            scope['allowed_paths']['read'].append(pattern)
        scope['inputs'].append(dict(name='before_' + name.replace('.', '_'), path=snapshot.as_posix(), sha256=current['manifest'][name]))
    scope['extensions']['chat_build'] = dict(turn_id=turn_id, before_sha256=before, after_sha256=after)
    child = deepcopy(scope)
    child.update(id='ct-chat-build-' + suffix + '-0001', agent='ember-build-worker')
    child['extensions']['orchestration']['role'] = 'coding'
    child['limits']['max_calls'] = len(rows)
    for contract in (scope, child):
        h.save_draft(contract)
    diff = ''.join(''.join(unified_diff(old_files.get(row['name'], '').splitlines(keepends=True), files[row['name']].splitlines(keepends=True),
                                fromfile='current/' + row['name'], tofile='proposed/' + row['name'])) + '\n' for row in rows)
    body = dict(contracts=[dict(contract=scope, parent_id=None), dict(contract=child, parent_id=scope['id'])],
                build=dict(turn_id=turn_id, title=build['title'], summary=build['summary'],
                           path=target.as_posix(), before_sha256=before, after_sha256=after, diff=diff,
                           files=rows, manifest=manifest, before_manifest=current['manifest'],
                           checks=['HTML parsed and local script/stylesheet references checked', str(len(files)) + ' files in this session project; ' + str(len(rows)) + ' changed',
                                   'No server commands, packages, deployment or engine edits']))
    if restore_from is not None:
        body['build']['restore_from'] = restore_from
        body['build']['checks'].append('Historical approved bytes and evidence verified; restoration requires this new approval')
    return OwnerReview()._request(h, 'contracts', body, wait=False)


def list_requests(folder):
    if not (Path(folder) / 'build-authority').exists():
        return []
    h = harness(folder)
    entries = h._entries()
    decisions = {e['request_ref']: e for e in entries if e['kind'] == 'owner_decision'}
    return [dict(ref=e['request_ref'], payload=load_request(h, e['request_ref']),
                 decision=decisions.get(e['request_ref']), origin='chat_build')
            for e in entries if e['kind'] == 'owner_request']


def _target(root, folder, payload):
    target = project(root, folder) / 'index.html'
    if target.as_posix() != payload['body']['build']['path'] or target.resolve() != target:
        raise ValueError('Reviewed project path changed')
    return target


def respond(root, folder, ref, choice, quote):
    with exclusive(Path(folder) / 'build.lock'):
        h = harness(folder)
        payload = load_request(h, ref)
        _target(root, folder, payload)
        build = payload['body']['build']
        before = build.get('before_manifest', {'index.html': build['before_sha256']})
        if choice != 'decline' and any(file_hash(project(root, folder) / name) != value for name, value in
                                     {**dict.fromkeys(build.get('manifest', {})), **before}.items()):
            raise ValueError('Project changed since this proposal; ask Muse for a fresh proposal')
        if choice != 'decline':
            check_project_names(project(root, folder), before)
        result = decide(h, ref, choice, quote)
        if choice == 'approve':
            return {**result, 'build': apply(root, folder, ref)}
        return result


def apply(root, folder, ref):
    """Called under build.lock; completion is reconciled from exact bytes and audit."""
    h = harness(folder)
    payload = load_request(h, ref)
    entries = h._entries()
    validate_history(h, entries)
    decision = next((e for e in entries if e['kind'] == 'owner_decision' and e['request_ref'] == ref), None)
    if not decision or decision['choice'] != 'approve':
        raise ValueError('Explicit owner approval is required before building')
    build = payload['body']['build']
    _target(root, folder, payload)
    child_id = payload['body']['contracts'][1]['contract']['id']
    active = h._active(entries)
    contract = h._authority(active[child_id], active)
    if 'files' not in build:
        # Legacy saved single-file packets use the same per-file application path.
        payload = deepcopy(payload)
        build = payload['body']['build']
        build['files'] = [dict(name='index.html', path=build['path'], action_id='write',
                               before_sha256=build['before_sha256'], after_sha256=build['after_sha256'])]
        build['manifest'] = {'index.html': build['after_sha256']}
    return apply_project(root, folder, ref, h, payload, entries, contract)


def check_project_names(destination, manifest):
    if destination.exists() and set(p.name for p in destination.iterdir()) - set(manifest):
        raise ValueError('Project changed: unexpected files require inspection')


def apply_project(root, folder, ref, h, payload, entries, contract):
    build = payload['body']['build']
    destination = project(root, folder)
    check_project_names(destination, build['manifest'])
    done = any(e['kind'] == 'chat_build_completed' and e['request_ref'] == ref for e in entries)
    actions = {a['action_id']: a for a in contract['allowed_actions']}
    planned = []
    for row in build['files']:
        target = destination / row['name']
        if target.resolve() != target or target.as_posix() != row['path']:
            raise ValueError('Reviewed project path changed')
        content = actions[row['action_id']]['args_constraints']['content']['equals']
        action = dict(agent=contract['agent'], contract_id=contract['id'], contract_version=1, tool='fs.write',
                      args=dict(path=target.as_posix(), content=content), paths=dict(read=[], write=[target.as_posix()]), spend=0)
        prior = next((e for e in entries if e['kind'] == 'decision' and e.get('decision') == 'allow' and e.get('action') == action), None)
        current = file_hash(target)
        if current != row['before_sha256'] and not (current == row['after_sha256'] and prior):
            raise ValueError('Project changed or build outcome is uncertain; inspection required')
        if done and current != row['after_sha256']:
            raise ValueError('Built file changed after verification')
        planned.append((row, target, content, action, prior))
    changed = {r['name'] for r in build['files']}
    for name, expected in build['manifest'].items():
        if name not in changed and file_hash(destination / name) != expected:
            raise ValueError('Unchanged project file changed; inspection required')
    if done:
        return dict(status='completed', path=build['path'], sha256=build['after_sha256'], manifest=build['manifest'])
    # Validate the entire resulting project before any side effect.
    contents = {name: (destination / name).read_bytes().decode('utf-8') for name in build['manifest'] if name not in changed}
    contents.update({row['name']: content for row, _, content, _, _ in planned})
    validate_files(contents)
    for row, target, content, action, prior in planned:
        current = file_hash(target)
        if current != row['after_sha256']:
            window = contract['limits']['time_window']
            if not timestamp(window['not_before']) <= h.clock() <= timestamp(window['not_after']):
                raise ValueError('Build approval expired; ask Muse for a fresh proposal')
            if not h.verify_inputs(contract['id']):
                raise ValueError('Approved input files changed')
            if prior is None:
                permitted = h.check(action)
                if permitted['decision'] != 'allow':
                    raise ValueError('Build denied: ' + permitted['reason'])
                prior = dict(seq=permitted['audit_seq'])
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = Path(folder) / 'build-output.tmp'
            with temp.open('wb') as stream:
                stream.write(content.encode('utf-8'))
                stream.flush()
                os.fsync(stream.fileno())
            if file_hash(target) != row['before_sha256'] or target.resolve() != target:
                raise ValueError('Project changed during build; no overwrite performed')
            os.replace(temp, target)
        evidence = h.verify_evidence(contract['id'], row['action_id'], [dict(kind='file_hash',
            params=dict(path=target.as_posix(), sha256=row['after_sha256']))], decision_seq=prior['seq'])
        if evidence['status'] != 'complete':
            raise ValueError('Build evidence did not verify')
    check_project_names(destination, build['manifest'])
    if any(file_hash(destination / name) != expected for name, expected in build['manifest'].items()):
        raise ValueError('Project changed before completion; inspection required')
    with h._lock():
        h._append('chat_build_completed', request_ref=ref, contract_id=contract['id'],
                  path=build['path'], sha256=build['after_sha256'], manifest=build['manifest'])
    return dict(status='completed', path=build['path'], sha256=build['after_sha256'], manifest=build['manifest'])


def resume(root, folder, ref):
    with exclusive(Path(folder) / 'build.lock'):
        return apply(root, folder, ref)


def status(root, folder):
    requests = list_requests(folder)
    if not requests:
        return dict(requests=[], completed=[], resumable=[], audit=[], project=str(project(root, folder)))
    h = harness(folder)
    entries = h._entries()
    completed = [e for e in entries if e['kind'] == 'chat_build_completed']
    done_refs = {e['request_ref'] for e in completed}
    resumable = [r['ref'] for r in requests if r['decision'] and r['decision']['choice'] == 'approve' and r['ref'] not in done_refs]
    return dict(requests=requests, completed=completed, resumable=resumable, audit=entries[-100:],
                project=str(project(root, folder)))


def preview(root, folder):
    state = status(root, folder)
    if state['resumable']:
        raise ValueError('Resume the approved build before previewing the project')
    if not state['completed']:
        raise ValueError('Approve and complete a build before previewing')
    last = state['completed'][-1]
    target = project(root, folder) / 'index.html'
    manifest = last.get('manifest', {'index.html': last['sha256']})
    check_project_names(target.parent, manifest)
    if any(file_hash(target.parent / name) != expected for name, expected in manifest.items()):
        raise ValueError('Project changed since the verified build')
    files = {name: (target.parent / name).read_bytes().decode('utf-8') for name in manifest}
    validate_files(files)
    if len(files) == 1:
        return files['index.html']
    parser = ResourcePreview(files)
    parser.feed(files['index.html'])
    parser.close()
    return ''.join(parser.output)


def verify(root, folder):
    preview(root, folder)  # Validates original file sizes before embedding resources.
    h = harness(folder)
    entries = h._entries()
    validate_history(h, entries)
    last = [e for e in entries if e['kind'] == 'chat_build_completed'][-1]
    payload = load_request(h, last['request_ref'])
    for row in payload['body']['build'].get('files', [dict(action_id='write')]):
        if h.step_status(last['contract_id'], row['action_id'])['status'] != 'complete':
            raise ValueError('Current build evidence did not verify')
    return dict(passed=True, path=last['path'], sha256=last['sha256'], audit=h.audit_verify(),
                manifest=last.get('manifest', {'index.html': last['sha256']}),
                checks=['Approved bytes match every project file', 'HTML and local references checked', 'Owner receipts and evidence verified'],
                limit='Behavior and JavaScript need review in the prototype preview')
