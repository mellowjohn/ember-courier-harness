"""A read-only handoff of the current approved game and its bounded evidence."""
from hashlib import sha256
import io
import json
from pathlib import Path
import zipfile

from . import chat_build, findings, gameplay, playtests, polish_runtime, project_plan, project_versions, task_run
from .contract_lock import verify as contract_lock
from .core import digest
from .recovery import exclusive, read_json

LIMIT = ('This is a snapshot of local host records, not an independent attestation or a declaration of project completion. '
         'Owner decisions can be fixture responses in rehearsals. AI judgments and fixed browser assertions do not establish '
         'artistic quality, complete gameplay correctness or human acceptance. Historical acceptance and closure do not transfer to later builds.')


def current_checks(folder, saved, game):
    rows = []
    for event in gameplay.reports(folder):
        if event['request_ref'] != game['request_ref'] or event['plan_sha256'] != saved['sha256']:
            continue
        area = folder / 'gameplay-runs' / event['report_id']
        source, capture = area / 'input.json', area / 'output/report.json'
        if capture.as_posix() != event['report_path'] or polish_runtime.file_digest(capture) != event['report_sha256']:
            raise ValueError('Gameplay handoff evidence changed')
        observed = polish_runtime.verified_report(source, capture.parent)
        data = read_json(source)
        parser = chat_build.ResourcePreview(game['files'])
        parser.feed(game['files']['index.html']); parser.close()
        if (data['html'] != ''.join(parser.output) or data['gameplay_plan'] != saved['plan'] or
                data['gameplay_plan_sha256'] != saved['sha256'] or event['manifest'] != game['manifest'] or
                event['plan_revision'] != saved['revision'] or event['plan'] != saved['plan'] or
                observed['gameplay'] != event['gameplay'] or event['outcome'] != observed['gameplay']['outcome']):
            raise ValueError('Gameplay handoff binding changed')
        rows.append(dict(report_id=event['report_id'], outcome=event['outcome'],
            scenarios=observed['gameplay']['scenarios'], basis=event['basis'], capture_sha256=event['report_sha256']))
    return rows


def report(root, folder, ref):
    """Caller holds the session chat, gameplay and build locks."""
    h = chat_build.harness(folder)
    entries = h._entries()
    chat_build.preview(root, folder)
    current = chat_build.context(root, folder)
    state = chat_build.status(root, folder)
    if state['completed'][-1]['request_ref'] != ref:
        raise ValueError('The current build changed; download its handoff again')
    game = project_versions.snapshot(root, folder, ref)
    if current['manifest'] != game['manifest']:
        raise ValueError('The approved game changed')
    checked = contract_lock(h.root)
    if not checked['ok']:
        raise ValueError('Project evidence needs inspection: ' + '; '.join(checked['errors']))
    plan = project_plan.status(root, folder)
    saved = gameplay.load(folder)
    checks = current_checks(folder, saved, game)
    runs = []
    for row in task_run.history(root, folder):
        if row['status'] == 'inspection_required':
            raise ValueError('Retained task evidence needs inspection before handoff')
        work, _, packet, task = task_run.load(folder, row['id'])
        runs.append(dict(id=row['id'], kind=task.get('kind', 'coding'), goal=row['goal'], status=row['status'],
            plan_ref=task['project_plan']['binding']['ref'], proposal_ref=row['proposal_ref'],
            applied_to_current_build=row['proposal_ref'] == ref,
            author=packet['body']['contracts'][0]['contract']['agent'],
            reviewer=packet['body']['contracts'][1]['contract']['agent'],
            selected_direction=row.get('selected_direction'),
            attempts=[dict(index=r['index'], qualified=r['qualified'], manifest=r['manifest'],
                matches_current_files=r['manifest'] == game['manifest'],
                browser_outcome=r['observations']['gameplay']['outcome'], ai_judgment=r['verdict']) for r in row['reports']]))
    bugs = []
    for row in findings.history(root, folder):
        bug, closure = row['bug'], row['closure']
        bugs.append(dict(id=bug['id'], summary=bug['title'], severity=bug['severity'], state=bug['state'],
            reported_build=bug.get('build_id'), attempts_started=row['attempts']['attempts_started'],
            closed_build=closure['build'] if closure else None,
            closure_applies_to_current_build=bool(closure and bug['state'] == 'closed' and closure['build'] == ref)))
    tasks = [dict(id=t['id'], title=t['title'], state=t['state'], build_ref=t['build_ref'],
        accepted=bool(t['acceptance']), acceptance_applies_to_current_build=bool(t['acceptance'] and t['build_ref'] == ref))
        for t in plan['tasks']]
    asset = None
    if 'asset.js' in game['files']:
        from .asset_pipeline import unpack, describe
        _, spec, measured = unpack(game['files']['asset.js'])
        asset = dict(id=spec['id'], name=describe(spec)['display_name'], specification=spec, measured=measured,
            package_sha256=game['manifest']['asset.js'], acceptance='Individual acceptance verified in saved build history')
    approved = plan['approved']
    binding = next(r['payload']['body']['build'].get('project_scope')
        for r in state['requests'] if r['ref'] == ref)
    plan_history = [dict(ref=r['ref'], version=r['payload']['body']['contracts'][0]['contract']['version'],
        decision=r['decision']['choice'] if r['decision'] else 'pending',
        widening_acknowledged=r['widening_acknowledged']) for r in project_plan.requests(folder)]
    result = dict(format_version=1, build=dict({k:v for k,v in game.items() if k != 'files'},
        project_scope=binding, matches_current_plan=bool(binding and approved and binding['ref'] == approved['ref'])),
        project_plan=dict(managed=plan['managed'], active=plan['active'], reason=plan['reason'],
            approved=approved, history=plan_history, tasks=tasks,
            acceptance_history=[{k:e[k] for k in ('plan_ref', 'task_id', 'request_ref', 'manifest')}
                for e in entries if e['kind'] == 'project_task_accepted']), asset=asset, task_runs=runs, findings=bugs,
        gameplay=dict(saved_plan=saved, current_build_checks=checks, limit=gameplay.LIMIT),
        playtests=[dict(report_id=e['report_id'], outcome=e['outcome'], note=e['note'],
            basis='Host-recorded human observation; not independent verification') for e in playtests.reports(folder)
            if e['request_ref'] == ref and e['manifest'] == game['manifest']],
        pending_build_reviews=sum(not r['decision'] for r in state['requests']),
        evidence=dict(audit_entries=len(entries), audit_snapshot_sha256=digest(entries),
            contract_lock='passed', checks=checked['checks']), limit=LIMIT)
    if 'sprite-plan.js' in game['files']:
        from .sprite_project import unpack_plan,asset_rows
        result['sprite_project']=dict(plan=unpack_plan(game['files']['sprite-plan.js']),assets=asset_rows(game['files']))
    # Task workers append without holding the project lock. Never combine two audit snapshots.
    if h._entries() != entries or gameplay.load(folder) != saved:
        raise ValueError('Project evidence changed during handoff; try again when the worker is idle')
    return result


def markdown(data):
    game = data['build']
    plan = data['project_plan']
    current = data['gameplay']['current_build_checks']
    lines = ['# Ember project handoff', '', f"Approved game: version {game['number']}", '',
        f"Build reference: `{game['request_ref']}`", '', data['limit'], '',
        '## Scope and outcomes', '',
        f"Project plan: {'active' if plan['active'] else 'inactive' if plan['managed'] else 'not configured'}.",
        'Build bound to the current approved plan: ' + ('yes' if game['matches_current_plan'] else 'no') + '.',
        f"Tasks accepted on this exact build: {sum(t['acceptance_applies_to_current_build'] for t in plan['tasks'])} / {len(plan['tasks'])}.",
        f"Pending build reviews: {data['pending_build_reviews']}.", '',
        '## Asset and verification', '',
        'Accepted asset: ' + (data['asset']['id'] if data['asset'] else 'none in this build') + '.',
        'Reviewed game bytes, owner receipts, audit and contract-lock: passed.',
        f"Saved gameplay reports for this exact build and current plan: {len(current)}.",
        'Latest gameplay outcome: ' + (current[-1]['outcome'] if current else 'not checked') + '.',
        f"Recorded playtests for this build: {len(data['playtests'])}.",
        f"Findings: {len(data['findings'])}; closures bound to this exact build: "
            f"{sum(b['closure_applies_to_current_build'] for b in data['findings'])}.", '',
        'See project-report.json for the complete approved design, version-bound task outcomes, findings, '
        'separate AI judgments and fixed browser observations. Missing checks and unaccepted outcomes remain outstanding.', '',
        '## Play the game', '',
        'Extract game.zip and open index.html in a browser. Play the keyboard and touch flows and compare '
        'them with the saved completion criteria. Keep the report with that exact game version.', '',
        'The package contains the approved browser game and report. Editable Blender sources and raw captures '
        'remain in the local workspace. Private conversation, owner quotes and host paths are omitted.', '']
    return '\n'.join(lines)


def export(root, folder, ref):
    folder = Path(folder)
    with exclusive(folder / 'chat.lock'), exclusive(folder / 'gameplay.lock'):
        game_zip, _ = project_versions.export(root, folder, ref)
        with exclusive(folder / 'build.lock'):
            data = report(root, folder, ref)
            data['game_zip_sha256'] = sha256(game_zip).hexdigest()
            files = {'game.zip': game_zip, 'PROJECT_HANDOFF.md': markdown(data).encode('utf-8'),
                'project-report.json': json.dumps(data, indent=2, ensure_ascii=False).encode('utf-8')}
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w') as archive:
                for name, content in sorted(files.items()):
                    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, content)
            return output.getvalue(), 'ember-project-v' + str(data['build']['number']) + '-handoff.zip'
