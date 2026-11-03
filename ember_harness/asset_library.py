"""Workspace asset locations and immutable, verified snapshots for conversation."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re

from . import asset_pipeline
from .core import canonical, digest
from .recovery import atomic_json, exclusive, read_json

MAX_RECORD = 600_000
MAX_ASSETS = 32
SOURCE_ROOTS=('.harness/asset-source','.harness/asset-lab-source','assets','art','models')
_summaries = {}
_sources = {}
_source_states = {}


def home(root):
    path = Path(root).resolve() / '.harness/asset-library'
    if path.resolve() != path:
        raise ValueError('Asset library path changed')
    return path


def limited(path, maximum):
    with Path(path).open('rb') as stream: raw = stream.read(maximum + 1)
    if len(raw) > maximum: raise ValueError('Asset file exceeds its size limit')
    return raw


def fingerprint(path):
    result = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): result.update(chunk)
    return result.hexdigest()


def register(root, source, *, refresh=False):
    """Explicit callers may register a source directory; discovery stays in workspace roots."""
    source = Path(source).resolve()
    spec_path = source / 'asset-spec.json'
    spec_bytes = limited(spec_path, 65536)
    spec = json.loads(spec_bytes)
    descriptor = asset_pipeline.describe(spec)
    is_2d = spec.get('profile') == 'sprite-atlas-v1'
    glb_path = source / (descriptor['id'] + ('.png' if is_2d else '.glb'))
    blend = source / (descriptor['id'] + '.blend')
    request_path = source / 'generation-request.json'
    generated = is_2d and spec['production']['method'] == 'generated'
    request_bytes = None
    if generated:
        from .asset_2d import generation_request
        request_bytes = limited(request_path, 32768)
        if canonical(json.loads(request_bytes)) != canonical(generation_request(spec)):
            raise ValueError('Generated asset must retain its exact image-tool request')
    signature = tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ctime_ns) for p in (spec_path, glb_path, blend, request_path) if p.is_file())
    cached = _sources.get(str(source))
    if not refresh and cached and cached[0] == signature and (home(root) / (cached[1] + '.json')).is_file():
        return cached[1]
    raw = limited(glb_path, asset_pipeline.MAX_GLB)
    package = asset_pipeline.package(raw, spec)
    sources = dict(specification=dict(path=str(spec_path), sha256=sha256(spec_bytes).hexdigest()),
                   export=dict(path=str(glb_path), sha256=sha256(raw).hexdigest()))
    if blend.is_file():
        # Native source is tracked as provenance; its contents never enter model context.
        sources['blender'] = dict(path=str(blend), sha256=fingerprint(blend))
    if request_bytes is not None:
        sources['generation'] = dict(path=str(request_path), sha256=sha256(request_bytes).hexdigest())
    record = dict(version=1, asset_id=descriptor['id'], display_name=descriptor['display_name'],
                  sources=sources, package=package, source_mtime_ns=glb_path.stat().st_mtime_ns)
    ref = digest(record)
    folder = home(root); folder.mkdir(parents=True, exist_ok=True)
    path = folder / (ref + '.json')
    with exclusive(folder / 'library.lock'):
        if path.exists():
            if read_json(path) != record: raise ValueError('Asset record changed')
        else:
            atomic_json(path, record)
    _sources[str(source)] = (signature, ref)
    return ref


def load(root, ref):
    if not isinstance(ref, str) or not re.fullmatch('[0-9a-f]{64}', ref):
        raise ValueError('A known asset reference is required')
    path = home(root) / (ref + '.json')
    if path.resolve() != path: raise ValueError('Asset record path changed')
    try: record = json.loads(limited(path, MAX_RECORD))
    except OSError as error: raise ValueError('The recorded asset is unavailable') from error
    if digest(record) != ref or record.get('version') != 1:
        raise ValueError('Asset record changed')
    raw, spec, report = asset_pipeline.unpack(record['package'])
    if (record['asset_id'] != spec['id'] or record['sources']['export']['sha256'] != report['sha256'] or
            record['display_name'] != asset_pipeline.describe(spec)['display_name']):
        raise ValueError('Asset source identity changed')
    return record, spec, report


def discover(root):
    """Find known production outputs, without searching arbitrary folders or test workspaces."""
    root = Path(root).resolve(); candidates = []
    for relative in SOURCE_ROOTS:
        base = root / relative
        if base.is_dir() and base.resolve() == base:
            candidates.extend(base.rglob('asset-spec.json'))
    checks = root / '.harness/asset-checks'
    if checks.is_dir() and checks.resolve() == checks:
        for path in checks.glob('*/refined/asset-spec.json'):
            try:
                report = read_json(path.parent.parent / 'report.json')
                if report.get('passed'): candidates.append(path)
            except (OSError, ValueError): pass
    # Old rehearsal runs remain on disk; only the most recent bounded set is inspected.
    def modified(path):
        try: return path.stat().st_mtime_ns
        except OSError: return 0
    candidates = sorted(candidates, key=modified, reverse=True)[:64]
    registered = []
    for path in candidates:
        if not path.resolve().is_relative_to(root): continue
        try: registered.append(register(root, path.parent))
        except (OSError, ValueError, KeyError, TypeError, IndexError): continue
    return registered


def summary(root, ref):
    if not isinstance(ref,str) or not re.fullmatch('[0-9a-f]{64}',ref):
        raise ValueError('A known asset reference is required')
    path = home(root) / (ref + '.json')
    if path.resolve()!=path: raise ValueError('Asset record path changed')
    stat = path.stat(); signature = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    cached = _summaries.get(str(path))
    if cached and cached[0] == signature:
        record, spec, report = deepcopy(cached[1])
    else:
        record = json.loads(limited(path, MAX_RECORD))
        if digest(record) != ref or record.get('version') != 1:
            raise ValueError('Asset record changed')
        package = record['package']
        if not package.startswith(asset_pipeline.PREFIX) or not package.endswith(asset_pipeline.SUFFIX):
            raise ValueError('Invalid recorded asset package')
        metadata = json.loads(package[len(asset_pipeline.PREFIX):-len(asset_pipeline.SUFFIX)])
        spec, report = metadata['spec'], metadata['report']
        _summaries[str(path)] = (signature, deepcopy((record, spec, report)))
    sources = {}
    for role,item in record['sources'].items():
        source=Path(item['path'])
        try:
            info=source.stat(); stamp=(info.st_size,info.st_mtime_ns,info.st_ctime_ns)
            cached_source=_source_states.get(str(source))
            if not cached_source or cached_source[0]!=stamp:
                cached_source=(stamp,fingerprint(source));_source_states[str(source)]=cached_source
            state='recorded' if cached_source[1]==item['sha256'] else 'changed'
        except OSError: state='missing'
        sources[role]={**item,'exists':state!='missing','status':state}
    measurements = (dict(dimensions_px=report['dimensions_px'], frames=len(report['frames']))
                    if spec.get('profile') == 'sprite-atlas-v1' else
                    dict(dimensions_m=report['dimensions_m'], triangles=report['triangles'], materials=report['materials']))
    return dict(ref=ref, id=record['asset_id'], display_name=record['display_name'], sources=sources,
                package_sha256=sha256(record['package'].encode('utf-8')).hexdigest(),
                source_mtime_ns=record.get('source_mtime_ns',stat.st_mtime_ns),
                sha256=report['sha256'], profile=report['profile'], **measurements, specification=spec,
                basis='Immutable asset snapshot with recorded source locations; not human acceptance')


def context(root, folder, messages=(), *, refresh=False, project_files=None):
    if refresh: discover(root)
    folder = Path(folder)
    # The most recent host-validated reference is durable even after old prose leaves the prompt.
    focus = next((m['asset_ref'] for m in reversed(messages) if m.get('asset_ref')), None)
    current_hash = None
    if project_files and 'asset.js' in project_files:
        current_hash = sha256(project_files['asset.js'].encode('utf-8')).hexdigest()
    candidates = sorted(home(root).glob('*.json'), key=lambda p:p.stat().st_mtime_ns, reverse=True)[:128]
    from . import chat_build
    pending_hash = None
    current_source = pending_source = None
    requests=chat_build.list_requests(folder)
    entries=chat_build.harness(folder)._entries() if requests else []
    accepted={e['action']['args']['sha256'] for e in entries if e['kind']=='decision' and e.get('decision')=='allow'
        and e.get('action',{}).get('tool')=='asset.accept'}
    if requests:
        completed=[e for e in entries if e['kind']=='chat_build_completed']
        if project_files is None and completed:
            package_hash=completed[-1].get('manifest',{}).get('asset.js')
            for request in reversed(requests):
                asset=request['payload']['body'].get('build',{}).get('asset')
                if asset and asset['package_sha256']==package_hash:
                    current_hash=asset['package_sha256'];break
        completed_refs={e['request_ref'] for e in completed}
        for request in reversed(requests):
            build=request['payload']['body']['build']
            if request['ref'] in completed_refs and build.get('manifest',{}).get('asset.js')==current_hash and build.get('asset_source'):
                current_source=build['asset_source']['ref'];break
    for request in reversed(requests):
        if not request['decision']:
            asset = request['payload']['body'].get('build', {}).get('asset')
            if asset: pending_hash = asset['package_sha256']
            pending_source=request['payload']['body']['build'].get('asset_source',{}).get('ref')
            break
    valid = []
    for path in candidates:
        try: row = summary(root, path.stem)
        except (OSError, ValueError, KeyError, TypeError): continue
        valid.append(row)
    for preferred in (focus,current_source,pending_source):
        if preferred and all(row['ref'] != preferred for row in valid):
            try: valid.append(summary(root, preferred))
            except (OSError,ValueError,KeyError,TypeError): pass
    rows, ids, current, remembered, pending = [], set(), None, None, None
    for row in sorted(valid,key=lambda v:v['source_mtime_ns'],reverse=True):
        if row['ref'] == focus: remembered = row
        if row['package_sha256'] == current_hash and (current is None or row['ref']==current_source): current = row
        if row['package_sha256'] == pending_hash and (pending is None or row['ref']==pending_source): pending = row
        if row['id'] not in ids and len(rows) < MAX_ASSETS:
            rows.append(row); ids.add(row['id'])
    for row in (remembered, current, pending):
        if row and all(v['ref'] != row['ref'] for v in rows): rows.append(row)
    if project_files and 'sprite-plan.js' in project_files:
        from .sprite_project import unpack_plan
        for entity in unpack_plan(project_files['sprite-plan.js'])['entities']:
            if entity['asset_ref'] and all(v['ref']!=entity['asset_ref'] for v in rows):
                rows.append(summary(root,entity['asset_ref']))
    for row in rows:
        row['accepted_in_session']=row['package_sha256'] in accepted
        row['acceptance_basis']='Exact package asset.accept decision in this session' if row['accepted_in_session'] else 'No acceptance receipt for these package bytes in this session'
    return dict(assets=rows, focus_ref=focus if remembered else (pending or current or {}).get('ref'),
                current_ref=current['ref'] if current else None, pending_ref=pending['ref'] if pending else None,
                note='References select existing snapshots only. Source locations and discussion never approve changes.')


def provenance(root, ref):
    record,_,report=load(root,ref)
    return dict(ref=ref,id=record['asset_id'],sources=record['sources'],sha256=report['sha256'],
                basis='Recorded source locations; this proposal uses the immutable asset snapshot')


def select(root, snapshot, ref):
    if not snapshot or not any(row['ref'] == ref for row in snapshot['assets']):
        raise ValueError('Choose an asset supplied in this conversation context')
    return load(root, ref)


def runtime(root, basis):
    if basis.get('engine.js'): return basis['engine.js']
    path = Path(root).resolve() / '.harness/asset-tools/engine.js'
    if path.resolve() != path: raise ValueError('Prepared 3D runtime path changed')
    try: return limited(path, 1048576).decode('utf-8').replace('\r\n','\n').replace('\r','\n')
    except OSError as error:
        raise ValueError('Prepare the offline 3D runtime before using an asset; see docs/ASSET_PIPELINE.md') from error


def build_from_reference(root, snapshot, ref, build, basis):
    """A model selects a frozen reference, never a file path or invented binary content."""
    record, spec, _ = select(root, snapshot, ref)
    if 'sprite-plan.js' in basis:
        raise ValueError('Use the sprite entity plan to choose which entity receives this artwork')
    if build and any(item['path'] in ('sprite-assets.js','sprite-plan.js') for item in build['files']):
        raise ValueError('Use the sprite entity plan to prepare multi-atlas files')
    is_2d = spec.get('profile') == 'sprite-atlas-v1'
    if build is None and basis.get('asset.js'):
        prior_2d = asset_pipeline.unpack(basis['asset.js'])[1].get('profile') == 'sprite-atlas-v1'
        if prior_2d != is_2d:
            raise ValueError('Propose scene code when changing between 2D and 3D assets')
    engine = None if is_2d else runtime(root, basis)
    from . import asset_workshop, chat_build
    if build is None:
        if basis and 'asset.js' not in basis:
            raise ValueError('Propose scene code to integrate this asset into the existing game')
        if is_2d:
            from . import asset_2d
            files = {**basis, 'asset.js': record['package']} if basis else asset_2d.assemble(record['package'])
        else:
            files = {**basis, 'asset.js': record['package'], 'engine.js': engine} if basis else asset_workshop.assemble(record['package'], engine)
        name = record['display_name']
        result = dict(title=name + ' · asset proposal', summary='Use the recorded '+name+' export in this scene.', files=[])
    else:
        result = deepcopy(build)
        files = {item['path']: item['content'] for item in result['files']}
        if len(files) != len(result['files']): raise ValueError('Duplicate proposed file paths')
        if 'asset.js' in files and files['asset.js'] != record['package']:
            raise ValueError('Use the recorded asset bytes rather than reconstructing asset.js')
        if not is_2d and 'engine.js' in files and files['engine.js'] != engine:
            raise ValueError('Keep the prepared 3D runtime unchanged')
        files['asset.js'] = record['package']
        if not is_2d: files['engine.js'] = engine
    if is_2d:
        from . import asset_2d
        if spec['kind'] in ('tile', 'tileset'):
            # Asset selection is reviewed with its runtime upgrade; ordinary revisions retain it.
            if 'sprite-player.js' in files and files['sprite-player.js'] not in (basis.get('sprite-player.js'), asset_2d.player_source()):
                raise ValueError('Keep the prepared sprite player unchanged')
            files.pop('sprite-player.js', None)
            files = asset_2d.attach_player(files, {})
        else:
            files = asset_2d.attach_player(files, basis)
    chat_build.validate_files(files)
    result['files'] = [dict(path=name, content=content) for name,content in files.items()]
    return result


def prompt_project(project):
    """Keep source readable without asking the model to copy mesh bytes and vendor code."""
    if project is None: return None
    result = deepcopy(project)
    for item in result.get('files', []):
        if item['path'] in ('asset.js', 'engine.js', 'sprite-player.js','sprite-assets.js','sprite-plan.js','ember-audio.js'):
            content = item.pop('content'); raw = content.encode('utf-8')
            item.update(sha256=sha256(raw).hexdigest(), bytes=len(raw), retained_by_host=True)
            if item['path'] == 'asset.js':
                _,spec,report=asset_pipeline.unpack(content)
                item['asset']=dict(specification=spec,report=report)
            if item['path']=='sprite-plan.js':
                from .sprite_project import unpack_plan
                item['sprite_plan']=unpack_plan(content)
            if item['path']=='sprite-assets.js':
                from .sprite_project import asset_rows
                item['sprite_assets']=asset_rows({'sprite-assets.js':content})
    return result


def prompt_files(files):
    view=prompt_project(dict(files=[dict(path=k,content=v) for k,v in files.items()]))['files']
    return dict(files={row['path']:row['content'] for row in view if 'content' in row},
        prepared_files=[row for row in view if 'content' not in row])


def preserve_files(build, basis):
    result = deepcopy(build)
    files = {item['path']: item['content'] for item in result['files']}
    if len(files) != len(result['files']): raise ValueError('Duplicate proposed file paths')
    if any(name in files and name not in basis for name in ('sprite-assets.js','sprite-plan.js')):
        raise ValueError('Use the sprite entity plan to prepare atlas and state-definition files')
    for name in ('asset.js', 'engine.js', 'sprite-player.js','sprite-assets.js','sprite-plan.js','ember-audio.js'):
        if name in basis:
            if name in files and files[name] != basis[name]:
                raise ValueError('Select a known asset reference to replace the prepared asset or runtime')
            files[name] = basis[name]
    if 'sprite-player.js' in basis:
        from .asset_2d import attach_player
        files = attach_player(files, basis)
    from .game_audio import attach
    files = attach(files, basis)
    result['files'] = [dict(path=name, content=content) for name,content in files.items()]
    return result
