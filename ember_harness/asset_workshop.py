"""Prepare an exported prop for the existing owner-reviewed session workflow."""
from pathlib import Path
from datetime import datetime, timezone
import json

from . import asset_pipeline, chat_build, gameplay, project_brief
from .recovery import atomic_json, exclusive

TEMPLATES = Path(__file__).with_name('asset_lab')


def plan(spec=None):
    def step(action, **kw): return dict(action=action, **kw)
    name = asset_pipeline.describe(spec)['display_name'] if spec is not None else 'Delivery chest'
    return dict(title=name + ' interaction and collision', scenarios=[
        dict(name='Cannot deliver from afar', viewport='desktop', steps=[
            step('press', key='Space'), step('text', selector='#status', value='Too far to reach'),
            step('text', selector='#deliveries', value='0')]),
        dict(name='Keyboard open and close', viewport='desktop', steps=[
            step('click', selector='#approach'), step('text', selector='#status', value='Ready to open'),
            step('press', key='Space'), step('text', selector='#lid-state', value='Open'),
            step('text', selector='#deliveries', value='1'), step('press', key='Space'),
            step('text', selector='#lid-state', value='Closed')]),
        dict(name='Touch delivery and reset', viewport='mobile', steps=[
            step('tap', selector='#approach'), step('tap', selector='#interact'),
            step('text', selector='#lid-state', value='Open'), step('text', selector='#deliveries', value='1'),
            step('tap', selector='#reset'), step('text', selector='#lid-state', value='Closed'),
            step('text', selector='#deliveries', value='0')]),
        dict(name='Approach respects collision', viewport='desktop', steps=[
            step('click', selector='#approach'), step('text', selector='#collision-state', value='Blocked')]),
    ])


def files(source, engine):
    source, engine = Path(source), Path(engine)
    spec = json.loads((source / 'asset-spec.json').read_text(encoding='utf-8'))
    descriptor = asset_pipeline.describe(spec)
    raw = (source / (descriptor['id'] + '.glb')).read_bytes()
    return assemble(asset_pipeline.package(raw, spec), engine.read_text(encoding='utf-8'))


def assemble(package, engine):
    result = {name: (TEMPLATES / name).read_text(encoding='utf-8') for name in ('index.html', 'style.css', 'app.js')}
    result.update({'engine.js': engine, 'asset.js': package})
    chat_build.validate_files(result)
    return result


def prepare(root, source, engine, *, session_id=None):
    from .local_ui import App
    from .asset_library import register, load, provenance
    asset_ref=register(root,source)
    record,_,_=load(root,asset_ref)
    prepared=assemble(record['package'],Path(engine).read_text(encoding='utf-8'))
    _, spec, _ = asset_pipeline.unpack(prepared['asset.js'])
    descriptor = asset_pipeline.describe(spec)
    name = descriptor['display_name']
    app = App(root)
    if session_id:
        app.resume(session_id)
    else:
        app.start(name + ' · Blender asset workshop', chat_only=True)
    folder = app.sessions_dir / app.session['id']
    with exclusive(folder / 'chat.lock'), exclusive(folder / 'build.lock'):
        current = chat_build.context(app.root, folder)
        if set(current['manifest']) - set(prepared):
            raise ValueError('Use a fresh asset workshop session; unrelated files would be removed')
        ref = chat_build.propose_build(app.root, folder, 'asset-' + chat_build.digest(prepared)[:24],
            'Review an original Blender prop in a playable offline Three.js scene',
            dict(title=name + ' · field test', summary='Try the asset, inspect its measurements and accept the exact package when satisfied.',
                 files=[dict(path=k, content=v) for k,v in prepared.items()]), expected_before=current['sha256'],
                 asset_source=provenance(root,asset_ref))
    seed_guidance(folder, spec)
    return dict(session_id=app.session['id'], request_ref=ref, status='awaiting_owner',
                basis='No project files written and no owner acceptance invented. Open this saved session to try the proposal.')


def seed_guidance(folder, spec):
    if spec.get('profile') == 'sprite-atlas-v1':
        from .asset_2d import plan as sprite_plan
        saved = gameplay.load(folder)
        # Only seed workshop selectors in the actual workshop, never in a custom game.
        pending = chat_build.list_requests(folder)
        is_workshop = False
        if pending:
            child = pending[-1]['payload']['body']['contracts'][-1]['contract']
            is_workshop = any(a['tool'] == 'fs.write' and
                a['args_constraints']['path'].get('equals', '').endswith('/index.html') and
                'id="sprite-workshop"' in a['args_constraints']['content'].get('equals', '')
                for a in child['allowed_actions'])
        if is_workshop and saved['revision'] == 0:
            gameplay.save(folder, sprite_plan(spec), 0)
        return
    name=asset_pipeline.describe(spec)['display_name']
    saved = gameplay.load(folder)
    if saved['revision'] == 0: gameplay.save(folder, plan(spec), 0)
    brief = project_brief.load(folder)
    if brief['revision'] == 0:
        project_brief.save(folder, dict(goal='Approach '+name+', open and close it, then reset.',
            controls='WASD/arrows; Space to open/close; R to reset; touch buttons; drag to orbit.',
            visual_direction=spec['art_direction'],
            constraints='Preserve GLB source identity, collision proxy, hinge, socket, offline operation and gameplay selectors.'), 0, purpose='asset_preview')


def review_updated_export(root, folder, asset_ref, current_ref):
    """Re-read the approved asset's recorded export, preserving the current scene."""
    from . import asset_library, project_versions, session_chat
    folder = Path(folder)
    with exclusive(folder / 'chat.lock'), exclusive(folder / 'build.lock'):
        state = chat_build.status(root, folder)
        if state['resumable'] or not state['completed'] or state['completed'][-1]['request_ref'] != current_ref:
            raise ValueError('Choose the latest completed build before reviewing an asset update')
        saved = project_versions.snapshot(root, folder, current_ref)
        current = chat_build.context(root, folder)
        if current['manifest'] != saved['manifest']:
            raise ValueError('Project changed since the approved build; review those changes first')
        record, spec, _ = asset_library.load(root, asset_ref)
        from . import sprite_project
        sprite_plan=sprite_project.unpack_plan(saved['files'][sprite_project.PLAN_FILE]) if sprite_project.PLAN_FILE in saved['files'] else None
        is_bound=bool(sprite_plan and any(e['asset_ref']==asset_ref for e in sprite_plan['entities']))
        library = asset_library.context(root, folder, project_files=saved['files'])
        if not is_bound and (saved['files'].get('asset.js') != record['package'] or library['current_ref'] != asset_ref):
            raise ValueError('Choose the asset used by the latest approved scene')

        def ready(ref, updated_ref):
            messages = session_chat.transcript(folder)
            message_id = 'asset-update-' + ref
            if not any(m['id'] == message_id for m in messages):
                messages.append(dict(id=message_id, role='assistant', provider='local asset review',
                    text='The updated '+record['display_name']+' export is ready for review. Try the proposal and run the saved gameplay checks before accepting the asset.',
                    proposal_ref=ref, asset_ref=updated_ref, asset_intent='use',
                    created_at=datetime.now(timezone.utc).isoformat()))
                atomic_json(folder / 'chat.json', messages)
            return dict(status='awaiting_review', request_ref=ref, asset_ref=updated_ref,
                        message='Updated export ready for review. Project files have not changed.')

        pending = next((r for r in state['requests'] if not r['decision']), None)
        if pending:
            source = pending['payload']['body']['build'].get('asset_source', {})
            if source.get('update_from') == asset_ref:
                return ready(pending['ref'], source['ref'])
            raise ValueError('Approve or decline the pending build before reviewing an asset update')
        # Use only recorded source paths. Never execute Blender or accept a supplied path.
        paths = {role: Path(item['path']) for role, item in record['sources'].items()}
        if any(path.resolve() != path for path in paths.values()):
            raise ValueError('Recorded asset source path changed; register the new source explicitly')
        source = paths['specification'].parent
        extension = '.png' if spec.get('profile') == 'sprite-atlas-v1' else '.glb'
        if paths['specification'] != source / 'asset-spec.json' or paths['export'] != source / (spec['id'] + extension):
            raise ValueError('Recorded asset source locations do not match')
        updated_ref = asset_library.register(root, source, refresh=True)
        updated, updated_spec, _ = asset_library.load(root, updated_ref)
        if updated_spec['id'] != spec['id']:
            raise ValueError('The updated export must keep the approved asset identity')
        if updated['package'] == record['package']:
            return dict(status='unchanged', asset_ref=asset_ref,
                        message='The exported asset is unchanged. Source edits need a fresh export before review.')
        if is_bound:
            assets=sprite_project.unpack_assets(saved['files'][sprite_project.ASSETS_FILE])
            for entity in sprite_plan['entities']:
                if entity['asset_ref']==asset_ref:
                    sprite_project.validate_entity_asset(entity,updated_spec);entity['asset_ref']=updated_ref
            assets.pop(asset_ref)
            assets[updated_ref]=json.loads(updated['package'][len(sprite_project.asset_2d.PREFIX):-len(sprite_project.asset_2d.SUFFIX)])
            files={**saved['files'],sprite_project.ASSETS_FILE:sprite_project.pack_assets(assets),sprite_project.PLAN_FILE:sprite_project.pack_plan(sprite_plan)}
            if saved['files'].get('asset.js')==record['package']:files['asset.js']=updated['package']
        else:
            files = {**saved['files'], 'asset.js': updated['package']}
        provenance = asset_library.provenance(root, updated_ref)
        provenance['update_from'] = asset_ref
        turn = 'asset-update-' + chat_build.digest(dict(current=current_ref, asset=updated_ref, attempt=len(state['requests'])))[:32]
        ref = chat_build.propose_build(root, folder, turn,
            'Review a revised export of the approved asset in the existing scene',
            dict(title=record['display_name'] + ' · updated export',
                 summary='Replace the recorded asset with this validated export. Keep the scene, runtime and saved gameplay plan. Review and accept the exact revised asset.',
                 files=[dict(path=k, content=v) for k, v in files.items()]),
            expected_before=current['sha256'], asset_source=provenance)
        return ready(ref, updated_ref)
