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
import tempfile

from jsonschema import Draft202012Validator

from .core import Harness, digest, timestamp, SCHEMA
from .owner_review import OwnerReview, decide, load_request, validate_history
from .recovery import exclusive
from .scope import propose, BRIEF_SCHEMA
from .project_brief import UPDATE_SCHEMA
from .asset_2d import GENERATION_SCHEMA
from . import sprite_project

MAX_FILES = 8
MAX_IMAGE_REQUESTS = 8
PATH_PATTERN = r'^[a-z][a-z0-9_-]{0,63}\.(html|css|js)$'
LARGE_FILES = {'engine.js': 1048576, 'asset.js': 524288, 'sprite-assets.js': 4*1024*1024, 'sprite-plan.js':131072}
PROTECTED_FILES = ('asset.js', 'engine.js', 'sprite-player.js','sprite-assets.js','sprite-plan.js','ember-audio.js')
AUTO_PROJECT_SCOPE = object()

BUILD_SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['title', 'summary', 'files'],
    'properties': {
        'title': {'type': 'string', 'minLength': 1, 'maxLength': 160},
        'summary': {'type': 'string', 'minLength': 1, 'maxLength': 2000},
        'files': {'type': 'array', 'minItems': 1, 'maxItems': MAX_FILES, 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['path', 'content'],
            'properties': {'path': {'type': 'string', 'pattern': PATH_PATTERN},
                           'content': {'type': 'string', 'minLength': 1, 'maxLength': 1048576}}}},
    },
}
PROPOSAL_SCHEMA = deepcopy(BUILD_SCHEMA)
PROPOSAL_SCHEMA.update(required=['title', 'summary'], anyOf=[{'required': ['files']}, {'required': ['edits']}])
PROPOSAL_SCHEMA['properties']['edits'] = {
    'type': 'array', 'minItems': 1, 'maxItems': 64, 'items': {
        'type': 'object', 'additionalProperties': False, 'required': ['path', 'before', 'after'],
        'properties': {'path': {'type': 'string', 'pattern': PATH_PATTERN},
                       'before': {'type': 'string', 'minLength': 1, 'maxLength': 65536},
                       'after': {'type': 'string', 'maxLength': 65536}}}}
REVISION_INSTRUCTION = (
    'Improve the supplied existing game in place. Make the smallest coherent change needed for the request. '
    'Preserve unrelated systems, controls, visuals, file organization and gameplay targets. '
    'Do not rebuild, simplify away features, restyle or replace working systems unless the user requests it '
    'or it is necessary to implement the requested change; explain any necessary broader change in summary. '
    'For revisions return build {title,summary,edits:[{path,before,after}]}, with exact source text in before '
    'that occurs once in the supplied file. All edits match the supplied source, not the result of another edit; '
    'edits must not overlap. The host retains every untouched byte and file. '
    'To add new files with edits, include files:[{path,content}] containing only new files. '
    'Do not edit engine.js, asset.js, sprite-player.js, sprite-assets.js, sprite-plan.js or ember-audio.js; the host retains these. '
    'Use complete files only for a first build or when a requested or necessary rewrite needs them. '
    'Existing files omitted from a full-file reply are retained unchanged; file deletion is not supported. '
)
GAME_UI_INSTRUCTION = (
    'For new or requested game UI, design the interface as part of the playable game view. '
    'Before coding, choose the essential player information, its anchors within the game viewport, '
    'and a small visual vocabulary drawn from the approved game art: palette, type, shapes, borders and icon treatment. '
    'Describe those placement and style choices briefly in the build summary. '
    'Use a shared game-stage wrapper for the renderer and DOM HUD/menu layers; anchor overlays to that wrapper, '
    'not to the surrounding browser page. Keep HUD, pause, help and result states inside this stage. '
    'Do not sandwich the game between a page header/scoreboard and a footer of instructions or controls, '
    'or wrap gameplay in dashboard cards, unless the approved design explicitly calls for that layout. '
    'Keep the playfield dominant and its action area clear: show only essential live information, '
    'use contextual prompts and tuck secondary instructions into an in-game help/pause view. '
    'Match the game world rather than importing the Ember workspace theme or a generic web-app style. '
    'Use local available fonts and original CSS/SVG treatments; no remote UI kits or new artwork calls. '
    'Adapt anchors, scale and touch controls to the actual game viewport and safe areas on mobile; '
    'keep touch targets at least 44 CSS pixels and text legible without shrinking the entire desktop layout. '
    'Reserve non-overlapping space for HUD counters and controls at narrow widths: use compact named icon buttons '
    'or a menu rather than squeezing full desktop button labels over the counters. '
    'Bound help/settings panels to the stage with border-box sizing, a maximum height and internal scrolling; '
    'keep the close control reachable even when the panel content exceeds a short landscape stage. '
    'Give help/settings/pause openers an accessible name and aria-controls pointing to the unique panel ID '
    'so the browser reviewer can capture the open state as well as gameplay. '
    'Keep decorative overlays from intercepting gameplay input; interactive controls need semantic buttons, '
    'visible keyboard focus, accessible names and clear pressed/disabled states where applicable. '
    'When required by the requested mechanic, make start, pause, success, failure and restart states coherent '
    'with the same visual language. Preserve existing controls, selectors and gameplay checks. '
    'This guidance applies within the selected task: preserve unrelated existing UI and honor explicit approved layouts. '
)
GAME_UI_REVIEW_INSTRUCTION = (
    'Inspect game UI integration in the actual desktop and mobile captures. Check whether HUD, controls and '
    'menus belong to the game viewport rather than detached page sections above or below the renderer; '
    'whether their palette, typography, shapes and borders fit the approved game art; and whether they '
    'leave the action readable and reachable. A tidy surrounding web page is not evidence of an integrated game UI. '
    'Use source to check stage-relative anchoring, input interception and responsive behavior. '
    'Report the offending element, viewport and concrete repair when there is a mismatch. '
    'Overlapping or truncated counters, controls hiding other UI, and clipped or unclosable help/settings '
    'panels fail UI integration even when they are inside the stage. Mark the affected criterion not_met, '
    'rather than met with a crowding caveat. Inspect open panels when evidence is supplied; do not assume '
    'that DOM visibility proves the full panel or its close control fits in the stage. '
    'Respect explicit approved layouts and task scope; do not demand a redesign of unrelated existing UI. '
    'Only claim interaction/menu states that the supplied evidence actually shows; flag required missing evidence. '
)
CHAT_SCHEMA = {
    '$defs': deepcopy(SCHEMA['$defs']),
    'type': 'object', 'additionalProperties': False, 'required': ['message', 'build'],
    'properties': {'message': {'type': 'string', 'minLength': 1, 'maxLength': 8000},
                   'image_request': {'anyOf': [GENERATION_SCHEMA, {'type': 'null'}]},
                   'image_requests': {'anyOf': [{'type': 'array', 'minItems': 1,
                       'maxItems': MAX_IMAGE_REQUESTS, 'items': GENERATION_SCHEMA}, {'type': 'null'}]},
                   'sprite_project': {'anyOf':[sprite_project.RESPONSE_SCHEMA,{'type':'null'}]},
                   'brief_updates': {'anyOf': [UPDATE_SCHEMA, {'type': 'null'}]},
                   'plan': {'anyOf': [{'type': 'null'}, {
                       'type': 'object', 'additionalProperties': False, 'required': ['scope', 'art_direction'],
                       'properties': {'scope': {**BRIEF_SCHEMA, 'required': list(BRIEF_SCHEMA['properties'])},
                                      'art_direction': SCHEMA['properties']['art_direction']}}]},
                   'asset': {'anyOf': [{'type': 'null'}, {'type': 'object', 'additionalProperties': False,
                       'required': ['ref', 'intent'], 'properties': {
                           'ref': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
                           'intent': {'enum': ['discuss', 'use']}}}]},
                   'build': {'anyOf': [PROPOSAL_SCHEMA, {'type': 'null'}]}},
}

# The fixed runner validates exact action fields and its total time budget in gameplay.validate.
CHECK_STEP_SCHEMA = dict(type='object',additionalProperties=False,required=['action'],properties=dict(
    action=dict(type='string',minLength=1,maxLength=24),selector=dict(type='string',maxLength=160),
    key=dict(type='string',maxLength=16),ms=dict(type='integer',minimum=1,maximum=2000),
    value=dict(anyOf=[dict(type='string',maxLength=200),dict(type='number')])))
CHECKS_SCHEMA = dict(type='object',additionalProperties=False,required=['title','scenarios'],properties=dict(
    title=dict(type='string',minLength=1,maxLength=120),
    scenarios=dict(type='array',minItems=1,maxItems=4,items=dict(type='object',additionalProperties=False,
        required=['name','viewport','steps'],properties=dict(name=dict(type='string',minLength=1,maxLength=120),
            viewport=dict(enum=['desktop','mobile']),steps=dict(type='array',minItems=1,maxItems=16,items=CHECK_STEP_SCHEMA))))))
CHAT_SCHEMA['properties']['gameplay_checks'] = dict(anyOf=[CHECKS_SCHEMA,dict(type='null')])


def harness(folder):
    return Harness(Path(folder) / 'build-authority')


def project(root, folder):
    from .project_locations import destination
    return destination(root, folder)


def file_hash(path):
    if path.is_symlink():
        raise ValueError('Build target cannot be a symbolic link')
    return sha256(path.read_bytes()).hexdigest() if path.exists() else None


class HTMLCheck(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.html = self.body = False
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        self.html |= tag == 'html'
        self.body |= tag == 'body'
        if tag == 'script':
            self.scripts.extend(value for key, value in attrs if key == 'src' and value is not None)


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
    result = dict(workspace_kind='browser project', directory=str(destination), file='index.html',
                sha256=manifest_hash(manifest), content=files.get('index.html'),
                files=[dict(path=name, content=content) for name, content in files.items()], manifest=manifest)
    from .mechanic_workflow import binding
    mechanics = binding(files)
    if mechanics is not None:
        result['mechanics'] = mechanics
    return result


def manifest_hash(manifest):
    # Preserve the existing single-file context and cached-turn representation.
    if set(manifest) <= {'index.html'}:
        return manifest.get('index.html')
    return digest(manifest)


def materialize_build(build, base):
    """Resolve exact edits in memory; approvals still bind the complete resulting files."""
    Draft202012Validator(PROPOSAL_SCHEMA).validate(build)
    if 'edits' not in build:
        result = deepcopy(build)
        names = [item['path'] for item in result['files']]
        if len(set(names)) != len(names):
            raise ValueError('Duplicate file paths in browser project')
        # Recover an unambiguous transport mix-up: a complete page that loads
        # game.js was returned under game.js, with its JS under index.html.
        entry = next((item for item in result['files'] if item['path'] == 'index.html'), None)
        if entry and not entry['content'].lstrip().startswith('<'):
            pages = []
            for item in result['files']:
                if not item['path'].endswith('.js') or not re.match(r'\s*(?:<!doctype\s+html|<html\b)', item['content'], re.I):
                    continue
                page = HTMLCheck(); page.feed(item['content']); page.close()
                if page.html and page.body and item['path'] in page.scripts:
                    pages.append(item)
            if len(pages) == 1:
                entry['content'], pages[0]['content'] = pages[0]['content'], entry['content']
        # A file list describes replacements/additions, never implicit deletion.
        result['files'].extend(dict(path=name, content=content) for name, content in base.items() if name not in names)
        return result
    if not base:
        raise ValueError('Targeted edits require an existing project')
    files = dict(base)
    additions = build.get('files', [])
    names = [item['path'] for item in additions]
    if len(set(names)) != len(names) or set(names) & set(base):
        raise ValueError('With targeted edits, files may only add unique new file paths')
    spans = {}
    for edit in build['edits']:
        name, before, after = edit['path'], edit['before'], edit['after']
        if name in PROTECTED_FILES:
            raise ValueError('Targeted edits must preserve prepared assets and runtime')
        if name not in base:
            raise ValueError('Targeted edit names a missing existing file: ' + name)
        source = base[name]
        start = source.find(before)
        # Check overlapping occurrences too; str.count alone misses these.
        if start < 0 or source.find(before, start + 1) >= 0:
            raise ValueError('Targeted edit must match exactly once in ' + name)
        end = start + len(before)
        matches = spans.setdefault(name, [])
        if any(start < prior_end and prior_start < end for prior_start, prior_end, _ in matches):
            raise ValueError('Targeted edits overlap in ' + name)
        matches.append((start, end, after))
    for name, matches in spans.items():
        for start, end, after in sorted(matches, reverse=True):
            files[name] = files[name][:start] + after + files[name][end:]
    files.update({item['path']: item['content'] for item in additions})
    return dict(title=build['title'], summary=build['summary'],
                files=[dict(path=name, content=content) for name, content in sorted(files.items())])


def validate_files(files, *, empty=False):
    if empty and not files:
        return
    if not 1 <= len(files) <= MAX_FILES or 'index.html' not in files:
        raise ValueError('A browser project requires index.html and at most eight files')
    if any(not re.fullmatch(PATH_PATTERN, name) for name in files):
        raise ValueError('Use flat lowercase HTML, CSS and JavaScript file names')
    sizes = [len(content.encode('utf-8')) for content in files.values()]
    if any(size > LARGE_FILES.get(name, 65536) for name, size in zip(files, sizes)) or sum(
            size for name, size in zip(files, sizes) if name not in LARGE_FILES) > 262144:
        raise ValueError('Browser project exceeds the file or total size limit')
    if 'asset.js' in files:
        from .asset_pipeline import unpack
        unpack(files['asset.js'])
    sprite_project.validate_files(files)
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


def propose_build(root, folder, turn_id, intent, build, *, expected_before=None, restore_from=None, asset_source=None, project_scope=AUTO_PROJECT_SCOPE):
    Draft202012Validator(BUILD_SCHEMA).validate(build)
    files = {item['path']: item['content'] for item in build['files']}
    if len(files) != len(build['files']):
        raise ValueError('Duplicate file paths in browser project')
    validate_files(files)
    h = harness(folder)
    from . import project_plan
    plan = project_plan.context(root, folder)
    if project_scope is AUTO_PROJECT_SCOPE:
        project_scope = plan['binding'] if plan else None
    parent_scope = project_plan.check_binding(root, folder, project_scope)
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
    sprite_project.validate_files(files,old_files)
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
    asset_actions = []
    if 'asset.js' in files and parent_scope is None:
        from .asset_pipeline import unpack
        _, asset_spec, _ = unpack(files['asset.js'])
        scope['art_direction']['style'] = asset_spec['art_direction']
    elif sprite_project.ASSETS_FILE in files and parent_scope is None:
        scope['art_direction']['style']=sprite_project.asset_rows(files)[0]['spec']['art_direction']
    if sprite_project.ASSETS_FILE in files and parent_scope is None:
        planned_assets=sprite_project.asset_rows(files)
        scope['extensions']['scope']['asset_budget']={'sprite_atlases':len(planned_assets)}
        if 'asset.js' in files and manifest['asset.js'] not in {a['package_sha256'] for a in planned_assets}:
            scope['extensions']['scope']['asset_budget']['retained_asset']=1
    changed_assets=[]
    if any(row['name']=='asset.js' for row in rows):
        changed_assets.append(dict(path='asset.js',package_sha256=manifest['asset.js']))
    prior_hashes={a['package_sha256'] for a in sprite_project.asset_rows(old_files)}
    if 'asset.js' in old_files: prior_hashes.add(sha256(old_files['asset.js'].encode()).hexdigest())
    seen={a['package_sha256'] for a in changed_assets}
    for asset in sprite_project.asset_rows(files):
        if asset['package_sha256'] not in prior_hashes|seen:
            changed_assets.append(asset);seen.add(asset['package_sha256'])
    for index,asset in enumerate(changed_assets):
        scope['allowed_actions'].append(dict(action_id='accept-asset' if len(changed_assets)==1 else 'accept-asset-'+str(index+1),
            tool='asset.accept',**{'class':'asset_acceptance'},args_constraints=dict(
                path={'equals':(destination/asset['path']).as_posix()},sha256={'equals':asset['package_sha256']}),allow_no_evidence=True))
    scope['limits']['max_calls']=max(scope['limits']['max_calls'],len(rows)+len(changed_assets))
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
    child['limits']['max_calls'] = len(rows) + len(changed_assets)
    if parent_scope is not None:
        from .core import subset
        child['art_direction'] = deepcopy(parent_scope['art_direction'])
        child['limits']['time_window'] = deepcopy(parent_scope['limits']['time_window'])
        child['allowed_paths']['read'] = deepcopy(parent_scope['allowed_paths']['read'])
        child['extensions']['scope'] = deepcopy(parent_scope['extensions']['scope'])
        child['extensions']['lineage'].update(scope_id=parent_scope['id'], scope_version=parent_scope['version'])
        child['extensions']['project_task'] = deepcopy(project_scope)
        if not subset(child, parent_scope):
            raise ValueError('Build exceeds the approved project scope')
    for asset in changed_assets:
        asset_actions.append(dict(agent=child['agent'], contract_id=child['id'], contract_version=1,
            tool='asset.accept', args=dict(path=(destination / asset['path']).as_posix(), sha256=asset['package_sha256']),
            paths=dict(read=[(destination / asset['path']).as_posix()], write=[]), spend=0))
    for contract in ((child,) if parent_scope else (scope, child)):
        h.save_draft(contract)
    diff = ''.join(''.join(unified_diff(old_files.get(row['name'], '').splitlines(keepends=True), files[row['name']].splitlines(keepends=True),
                                fromfile='current/' + row['name'], tofile='proposed/' + row['name'])) + '\n' for row in rows)
    body = dict(contracts=[dict(contract=scope, parent_id=None), dict(contract=child, parent_id=scope['id'])],
                build=dict(turn_id=turn_id, title=build['title'], summary=build['summary'],
                           path=target.as_posix(), before_sha256=before, after_sha256=after, diff=diff,
                           files=rows, manifest=manifest, before_manifest=current['manifest'],
                           checks=['HTML parsed and local script/stylesheet references checked', str(len(files)) + ' files in this session project; ' + str(len(rows)) + ' changed',
                                   'No server commands, packages, deployment or engine edits']))
    if parent_scope is not None:
        body['contracts'] = [dict(contract=child, parent_id=parent_scope['id'])]
        body['build']['project_scope'] = deepcopy(project_scope)
        body['build']['checks'].append('Exact child contract is a subset of the existing approved project scope; task acceptance remains separate')
    if restore_from is not None:
        body['build']['restore_from'] = restore_from
        body['build']['checks'].append('Historical approved bytes and evidence verified; restoration requires this new approval')
    if asset_actions:
        body['asset_actions'] = asset_actions
    if asset_actions and 'asset.js' in files:
        from .asset_pipeline import unpack
        _, spec, report = unpack(files['asset.js'])
        body['build']['asset'] = dict(spec=spec, report=report, package_sha256=manifest['asset.js'])
        body['build']['checks'].append('Acceptance includes this exact asset package; technical checks do not judge visual quality')
    if sprite_project.ASSETS_FILE in files:
        body['build']['sprite_assets']=sprite_project.asset_rows(files)
        body['build']['sprite_plan']=sprite_project.unpack_plan(files[sprite_project.PLAN_FILE])
        body['build']['checks'].append('Entity roles, required clips, state graphs and exact draw replacements checked; '+str(len(asset_actions))+' changed assets require individual acceptance receipts')
    if asset_source is not None:
        body['build']['asset_source']=deepcopy(asset_source)
    from .mechanic_workflow import binding as mechanic_binding
    mechanics = mechanic_binding(files)
    if mechanics is not None:
        body['build']['mechanics'] = mechanics
        body['build']['checks'].append('Versioned reference mechanics and exact settings retained; fixed-step checks and human feel remain separate')
    return OwnerReview()._request(h, 'contracts', body, wait=False)


def list_requests(folder):
    if not (Path(folder) / 'build-authority').exists():
        return []
    h = harness(folder)
    entries = h._entries()
    decisions = {e['request_ref']: e for e in entries if e['kind'] == 'owner_decision'}
    return [dict(ref=e['request_ref'], payload=load_request(h, e['request_ref']),
                 decision=decisions.get(e['request_ref']), origin='chat_build')
            for e in entries if e['kind'] == 'owner_request' and 'build' in load_request(h, e['request_ref'])['body']]


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
        if choice != 'decline' and build.get('project_scope'):
            from .project_plan import check_binding
            check_binding(root, folder, build['project_scope'])
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
    if build.get('project_scope'):
        from .project_plan import check_binding
        check_binding(root, folder, build['project_scope'])
    child_id = payload['body']['contracts'][-1]['contract']['id']
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
            # Stage on the destination volume so a chosen folder can be on another drive.
            temp = None
            try:
                with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.ember-output-', suffix='.tmp', delete=False) as stream:
                    temp = Path(stream.name)
                    stream.write(content.encode('utf-8'))
                    stream.flush()
                    os.fsync(stream.fileno())
                if file_hash(target) != row['before_sha256'] or target.resolve() != target:
                    raise ValueError('Project changed during build; no overwrite performed')
                os.replace(temp, target)
            finally:
                if temp is not None:
                    temp.unlink(missing_ok=True)
        evidence = h.verify_evidence(contract['id'], row['action_id'], [dict(kind='file_hash',
            params=dict(path=target.as_posix(), sha256=row['after_sha256']))], decision_seq=prior['seq'])
        if evidence['status'] != 'complete':
            raise ValueError('Build evidence did not verify')
    check_project_names(destination, build['manifest'])
    if any(file_hash(destination / name) != expected for name, expected in build['manifest'].items()):
        raise ValueError('Project changed before completion; inspection required')
    for action in payload['body'].get('asset_actions', []):
        prior = next((e for e in h._entries() if e['kind'] == 'decision' and e.get('decision') == 'allow' and e.get('action') == action), None)
        if prior is None:
            accepted = h.check(action)
            if accepted['decision'] != 'allow':
                raise ValueError('Explicit owner asset acceptance required before completing this build')
    if sprite_project.PLAN_FILE in contents:
        sprite_project.sync_applied(folder,sprite_project.unpack_plan(contents[sprite_project.PLAN_FILE]),ref)
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


def proposal_snapshot(root, folder, ref, *, allow_declined=False):
    """Read reviewed bytes under the caller's build.lock; never apply them."""
    h = harness(folder)
    entries = h._entries()
    validate_history(h, entries)
    payload = load_request(h, ref)
    _target(root, folder, payload)
    decision = next((e for e in entries if e['kind'] == 'owner_decision' and e['request_ref'] == ref), None)
    if decision and not (allow_declined and decision['choice'] == 'decline'):
        raise ValueError('Choose a pending proposal to preview')
    build = payload['body']['build']
    current = context(root, folder)
    before = build.get('before_manifest', {'index.html': build['before_sha256']} if build['before_sha256'] else {})
    if current['manifest'] != before:
        raise ValueError('Project changed since this proposal; request fresh changes before previewing')
    before_files = {row['path']: row['content'] for row in current['files']}
    files = dict(before_files)
    child = payload['body']['contracts'][-1]['contract']
    actions = {a['action_id']: a for a in child['allowed_actions']}
    rows = build.get('files', [dict(name='index.html', path=build['path'], action_id='write', after_sha256=build['after_sha256'])])
    for row in rows:
        action = actions[row['action_id']]
        content = action['args_constraints']['content']['equals']
        expected_path = (project(root, folder) / row['name']).as_posix()
        if (not re.fullmatch(PATH_PATTERN, row['name']) or row['path'] != expected_path or
                action['tool'] != 'fs.write' or action['args_constraints']['path']['equals'] != expected_path or
                sha256(content.encode('utf-8')).hexdigest() != row['after_sha256']):
            raise ValueError('Proposed bytes do not match the reviewed files')
        files[row['name']] = content
    manifest = {name: sha256(content.encode('utf-8')).hexdigest() for name, content in files.items()}
    if manifest != build.get('manifest', {'index.html': build['after_sha256']}):
        raise ValueError('Proposed project manifest does not match the reviewed files')
    validate_files(files)
    return dict(files=files, before_files=before_files, manifest=manifest, before_manifest=before,
                request_ref=ref, title=build['title'])


def proposal_preview(root, folder, ref):
    """Render exact pending bytes without deciding, applying or recording evidence."""
    with exclusive(Path(folder) / 'build.lock'):
        saved = proposal_snapshot(root, folder, ref)
        files = saved['files']
        parser = ResourcePreview(files)
        parser.feed(files['index.html'])
        parser.close()
        return dict(html=''.join(parser.output), request_ref=ref, manifest=saved['manifest'],
                    basis='Unapproved proposal preview; current game and approval history unchanged')


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
    from . import project_versions
    h = harness(folder)
    entries = h._entries()
    last = [e for e in entries if e['kind'] == 'chat_build_completed'][-1]
    # Inspection is historical proof, not a new use of a retired write contract.
    # The existing version reader checks the owner receipt, original gate decisions
    # and immutable file evidence. New work still needs today's active scope.
    saved = project_versions.snapshot(root, folder, last['request_ref'])
    if context(root, folder)['manifest'] != saved['manifest']:
        raise ValueError('Project changed during build verification')
    return dict(passed=True, path=last['path'], sha256=last['sha256'], audit=h.audit_verify(),
                manifest=last.get('manifest', {'index.html': last['sha256']}),
                checks=['Approved bytes match every project file', 'HTML and local references checked', 'Owner receipts and evidence verified'],
                limit='Behavior and JavaScript need review in the prototype preview')
