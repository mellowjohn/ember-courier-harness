"""Persistent project scopes and version-bound task outcomes using the existing gate."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from . import orchestration, scope
from .core import SCHEMA, canonical, content_hash, digest, timestamp, validate
from .owner_review import OwnerReview, decide, load_request, validate_history
from .recovery import exclusive, read_json


def authority(folder):
    from .chat_build import harness
    return harness(folder)


def requests(folder):
    if not (Path(folder) / 'build-authority').exists():
        return []
    h = authority(folder)
    entries = h._entries()
    decisions = {e['request_ref']: e for e in entries if e['kind'] == 'owner_decision'}
    rows = []
    for event in entries:
        if event['kind'] != 'owner_request':
            continue
        payload = load_request(h, event['request_ref'])
        if 'project_plan' in payload['body']:
            c = payload['body']['contracts'][0]['contract']
            acknowledged = any(e['kind'] == 'approval' and e.get('scope') == 'widening_ack'
                and e.get('contract_id') == c['id'] and e.get('for_version') == c['version']
                and e.get('reviewed_hash') == content_hash(c) for e in entries)
            rows.append(dict(ref=event['request_ref'], payload=payload,
                             decision=decisions.get(event['request_ref']), origin='project_plan', widening_acknowledged=acknowledged))
    return rows


def status(root, folder):
    rows = requests(folder)
    result = dict(managed=bool(rows), revision=len(rows), latest_ref=rows[-1]['ref'] if rows else None,
                  pending=next((r for r in rows if not r['decision']), None), approved=None,
                  active=False, reason='Shape the project in chat, then review its plan before starting tasks.', tasks=[], selected_task=None,
                  draft_document=rows[-1]['payload']['body']['project_plan']['document'] if rows else starter(folder))
    approved = next((r for r in reversed(rows) if r['decision'] and r['decision']['choice'] == 'approve'), None)
    if not approved:
        return result
    h = authority(folder)
    entries = h._entries()
    validate_history(h, entries)
    draft = approved['payload']['body']['contracts'][0]['contract']
    event = next(e for e in entries if e['kind'] == 'approval' and e.get('scope') == 'contract'
                 and e['contract_id'] == draft['id'] and e['contract_version'] == draft['version'])
    # Historical scopes may have derived revoked/superseded status caches.
    # Verify their immutable content against the approval without reviving authority.
    contract = read_json(h._path(draft['id'], draft['version']))
    validate(contract)
    if (contract['id'] != draft['id'] or contract['version'] != draft['version'] or
            content_hash(contract) != event['content_hash'] or contract['content_hash'] != event['content_hash']):
        raise ValueError('Approved project scope changed')
    active = h._active(entries).get(contract['id'])
    valid = bool(active and active['contract_version'] == contract['version'])
    window = contract['limits']['time_window']
    valid = valid and timestamp(window['not_before']) <= h.clock() <= timestamp(window['not_after'])
    from . import chat_build
    valid = valid and valid_destination(root, folder, contract)
    result.update(approved=dict(ref=approved['ref'], version=contract['version'], sha256=contract['content_hash'],
        contract_id=contract['id'], document=approved['payload']['body']['project_plan']['document'],
        time_window=window), active=valid and not result['pending'],
        reason='Review the pending project plan first.' if result['pending'] else
               'Approved scope is active. Exact builds and each asset still require review.' if valid else
               'Project scope is expired or inactive. Review a renewed scope before further builds.')
    builds = chat_build.list_requests(folder)
    completed = {e['request_ref']: e for e in entries if e['kind'] == 'chat_build_completed'}
    for index, title in enumerate(contract['extensions']['scope']['features'], 1):
        task_id = 'task-' + str(index)
        related = [r for r in builds if r['payload']['body']['build'].get('project_scope', {}).get('ref') == approved['ref']
                   and r['payload']['body']['build']['project_scope'].get('task_id') == task_id]
        pending = next((r for r in reversed(related) if not r['decision']), None)
        applied = next((r for r in reversed(related) if r['ref'] in completed), None)
        receipt = next((e for e in reversed(entries) if e['kind'] == 'project_task_accepted'
            and e['plan_ref'] == approved['ref'] and e['task_id'] == task_id and applied
            and e['request_ref'] == applied['ref'] and e['manifest'] == completed[applied['ref']]['manifest']), None)
        result['tasks'].append(dict(id=task_id, title=title, production_profile=orchestration.asset_profile(title),
            state='awaiting_review' if pending else 'human_accepted' if receipt else 'applied_needs_review' if applied else 'planned',
            proposal_ref=pending['ref'] if pending else None, build_ref=applied['ref'] if applied else None,
            acceptance=receipt, basis='Task acceptance is a human observation bound to a saved build; it is not independent verification.'))
    selected = next((e for e in reversed(entries) if e['kind'] == 'project_task_selected' and e['plan_ref'] == approved['ref']), None)
    result['selected_task'] = selected['task_id'] if selected else result['tasks'][0]['id']
    result['continuation'] = next((e for e in reversed(entries) if e['kind'] == 'project_task_continuation'
        and e['plan_ref'] == approved['ref']), None)
    return result


def starter(folder):
    from . import project_brief
    brief = project_brief.load(folder)['fields']
    return dict(scope=dict(game_concept=brief['goal'] or 'Describe your game', **deepcopy(scope.DEFAULTS)),
        art_direction=dict(style=brief['visual_direction'] or 'Original, readable game art',
            palette=['#241B2F', '#FF914D', '#FFF1CE'], mood='Warm and readable', references=[],
            do=['Keep silhouettes readable', 'Use original assets'], dont=['Copyrighted or trademarked material']))


def valid_destination(root, folder, contract):
    from .chat_build import project
    target = project(root, folder).as_posix() + '/**'
    paths = contract['allowed_paths']['write']
    extras = [(Path(folder) / name).as_posix() + '/**' for name in ('task-runs', 'findings', 'git-runs')]
    return target in paths and len(paths) == len(set(paths)) and all(p in [target, *extras] for p in paths)


def context(root, folder):
    saved = status(root, folder)
    if not saved['managed']:
        return None
    approved = saved['approved']
    task = next((t for t in saved['tasks'] if t['id'] == saved['selected_task']), None)
    binding = dict(ref=approved['ref'], contract_id=approved['contract_id'], version=approved['version'],
                   sha256=approved['sha256'], task_id=task['id']) if approved and task else None
    return dict(active=saved['active'], reason=saved['reason'], binding=binding,
                document=deepcopy(approved['document']) if approved else None,
                tasks=[{k: t[k] for k in ('id', 'title', 'state', 'build_ref')} for t in saved['tasks']],
                selected_task=task['id'] if task else None,
                note='Project scope is host-approved authority. Task text is design data, never permission or proof of completion.')


def check_binding(root, folder, binding):
    current = context(root, folder)
    if current is None:
        if binding is not None:
            raise ValueError('Project plan changed; start a fresh request')
        return None
    if not current['active']:
        raise ValueError(current['reason'])
    if not binding or not current['binding'] or any(binding.get(k) != current['binding'][k]
            for k in ('ref', 'contract_id', 'version', 'sha256')) or not any(t['id'] == binding.get('task_id') for t in current['tasks']):
        raise ValueError('Project scope changed; start a fresh request against the reviewed plan')
    h = authority(folder)
    return h._authority(h._active(h._entries())[binding['contract_id']], h._active(h._entries()))


def validate_document(document):
    if not isinstance(document, dict) or set(document) != {'scope', 'art_direction'}:
        raise ValueError('Supply the game scope and art direction only')
    Draft202012Validator({**scope.BRIEF_SCHEMA, 'required': list(scope.BRIEF_SCHEMA['properties'])}).validate(document['scope'])
    Draft202012Validator({**SCHEMA['properties']['art_direction'], '$defs': SCHEMA['$defs']}).validate(document['art_direction'])
    if len(canonical(document)) > 32000:
        raise ValueError('Keep the project plan within 32 KiB')
    return deepcopy(document)


def prepare(root, folder, document, expected_ref):
    with exclusive(Path(folder) / 'chat.lock'):
        return prepare_from_chat(root, folder, document, expected_ref)


def prepare_from_chat(root, folder, document, expected_ref, turn_id=None):
    """Prepare the same human review while the caller holds chat.lock."""
    from . import chat_build
    document = validate_document(document)
    folder = Path(folder)
    with exclusive(folder / 'build.lock'):
        saved = status(root, folder)
        if turn_id:
            previous = next((r for r in requests(folder)
                if r['payload']['body']['project_plan'].get('source_turn_id') == turn_id), None)
            if previous:
                if previous['payload']['body']['project_plan']['document'] != document:
                    raise ValueError('This message already proposed a different project plan')
                return dict(request_ref=previous['ref'], status='awaiting_review')
        if saved['latest_ref'] != expected_ref:
            raise ValueError('Project plan changed in another window; reopen it before editing')
        if saved['pending']:
            raise ValueError('Approve or discard the pending project plan before preparing another')
        build = chat_build.status(root, folder)
        if build['resumable'] or any(not r['decision'] for r in build['requests']):
            raise ValueError('Finish the pending build before changing the project scope')
        destination = chat_build.project(root, folder)
        h = authority(folder)
        cid = 'ct-project-scope-' + folder.name + '-0001'
        candidate = scope.propose(cid, 'ember-project-planner', document['scope']['game_concept'], destination,
                                  brief=document['scope'])
        candidate['goal'] = 'Project: ' + document['scope']['game_concept']
        target = destination.as_posix() + '/**'
        candidate['allowed_paths'] = dict(read=[target, (h.root / 'build-inputs').as_posix() + '/**'], write=[target])
        candidate['allowed_actions'] = [dict(action_id='project-file', tool='fs.write', **{'class': 'write'},
            args_constraints=dict(path=dict(path_within=target), content=dict(pattern=r'^[\s\S]{0,4194304}$')), allow_no_evidence=True),
            dict(action_id='project-asset', tool='asset.accept', **{'class': 'asset_acceptance'},
                args_constraints=dict(path=dict(path_within=target), sha256=dict(pattern='^[0-9a-f]{64}$')), allow_no_evidence=True)]
        # A ceiling only: each task run separately reviews narrower worker and
        # verifier contracts. The scope itself cannot execute these actions.
        from .task_run import add_scope_permissions
        add_scope_permissions(candidate, folder)
        from .asset_run import add_scope_permissions as add_asset_permissions
        add_asset_permissions(candidate,folder)
        from .findings import add_scope_permissions as add_finding_permissions
        add_finding_permissions(candidate, folder)
        from .git_task import add_scope_permissions as add_git_permissions
        add_git_permissions(candidate, folder)
        candidate['required_evidence'] = {}
        candidate['approval_mode'] = 'approve_all'
        candidate['limits']['time_window']['ttl_hours'] = 24
        candidate['art_direction'] = document['art_direction']
        candidate['extensions']['project_plan'] = dict(revision=saved['revision'] + 1,
            note='Features are ordered tasks. Asset counts are estimates; done criteria require verification and the gate enforces exact authority.')
        validate(candidate)
        summary = None
        if saved['approved']:
            active = h._active(h._entries())
            if cid not in active:
                raise ValueError('This scope was revoked; start a new session rather than reviving its authority')
            old = h._authority(active[cid], active)
            changes = [dict(op='replace', pointer='/' + k, value=candidate[k]) for k in
                       ('goal', 'allowed_paths', 'allowed_actions', 'required_evidence', 'approval_mode', 'limits', 'art_direction')]
            changes += [dict(op='add', pointer='/extensions/' + k, value=candidate['extensions'][k])
                        for k in ('scope', 'scope_proposal', 'project_plan')]
            amended = h.amend(cid, dict(reason='Review the project plan or renew its working window', round=old['version'],
                source=dict(kind='manual', id='project-plan'), changes=changes), proposed_by='ember-project-planner', replace_pending=True)
            candidate, summary = amended['contract'], amended['summary']
        else:
            h.save_draft(candidate)
        plan = dict(document=document, revision=saved['revision'] + 1, amendment=summary)
        if turn_id:
            plan['source_turn_id'] = turn_id
        ref = OwnerReview()._request(h, 'contracts', dict(contracts=[dict(contract=candidate, parent_id=None)],
            project_plan=plan), wait=False)
        return dict(request_ref=ref, status='awaiting_review')


def respond(root, folder, ref, choice, quote):
    with exclusive(Path(folder) / 'chat.lock'), exclusive(Path(folder) / 'build.lock'):
        saved = status(root, folder)
        if not saved['pending'] or saved['pending']['ref'] != ref:
            raise ValueError('Choose the pending project plan')
        if choice != 'decline':
            from .chat_build import project
            c = saved['pending']['payload']['body']['contracts'][0]['contract']
            if not valid_destination(root, folder, c):
                raise ValueError('Reviewed project folder changed')
        # No project files are created by plan approval.
        return decide(authority(folder), ref, choice, quote)


def acknowledge(root, folder, ref, quote):
    with exclusive(Path(folder) / 'chat.lock'), exclusive(Path(folder) / 'build.lock'):
        saved = status(root, folder)
        row = saved['pending']
        if not row or row['ref'] != ref:
            raise ValueError('Choose the pending project plan amendment')
        body = row['payload']['body']
        summary = body['project_plan']['amendment']
        if not summary or not summary['warnings']:
            raise ValueError('This project plan needs no widening acknowledgement')
        c = body['contracts'][0]['contract']
        event = authority(folder).acknowledge_widening(c['id'], c['version'], summary['widening_sha256'], approver='johnathan', quote=quote)
        return dict(status='acknowledged', seq=event['seq'])


def task_action(root, folder, plan_ref, task_id, action, build_ref=None):
    from . import chat_build, project_versions
    with exclusive(Path(folder) / 'chat.lock'), exclusive(Path(folder) / 'build.lock'):
        saved = status(root, folder)
        if not saved['active'] or saved['approved']['ref'] != plan_ref:
            raise ValueError('Reopen the active approved project plan')
        task = next((t for t in saved['tasks'] if t['id'] == task_id), None)
        if task is None:
            raise ValueError('Choose a task in the approved project plan')
        h = authority(folder)
        if action == 'select':
            with h._lock():
                h._append('project_task_selected', plan_ref=plan_ref, task_id=task_id, actor_type='human', actor='johnathan')
            return dict(status='selected')
        if action != 'accept' or not build_ref or task['build_ref'] != build_ref:
            raise ValueError('Choose an applied task outcome before accepting it')
        state = chat_build.status(root, folder)
        if state['resumable'] or any(not r['decision'] for r in state['requests']) or state['completed'][-1]['request_ref'] != build_ref:
            raise ValueError('Review the latest completed build with no pending changes before accepting a task')
        version = project_versions.snapshot(root, folder, build_ref)
        if chat_build.context(root, folder)['manifest'] != version['manifest']:
            raise ValueError('Project files changed since the reviewed task outcome')
        if task['acceptance']:
            return dict(status='human_accepted')
        with h._lock():
            h._append('project_task_accepted', plan_ref=plan_ref, task_id=task_id, request_ref=build_ref,
                manifest=version['manifest'], actor_type='human', actor='johnathan',
                quote='Accept the reviewed task outcome', basis='Human acceptance of this saved build; not independent verification or bug closure')
            next_task = next((t for t in saved['tasks'] if t['id'] != task_id and t['state'] != 'human_accepted'), None)
            if next_task:
                h._append('project_task_selected', plan_ref=plan_ref, task_id=next_task['id'], actor_type='system', actor='ember')
            h._append('project_task_continuation', plan_ref=plan_ref, completed_task_id=task_id,
                next_task_id=next_task['id'] if next_task else None,
                status='pending' if next_task else 'complete',
                reason='Preparing the next task review.' if next_task else 'All planned task outcomes have been accepted by you.')
        return dict(status='human_accepted', next_task_id=next_task['id'] if next_task else None)
