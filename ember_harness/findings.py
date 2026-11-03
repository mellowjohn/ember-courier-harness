"""Browser findings use the existing intake, bug attempts, gate and owner inbox.

Browser checkpoints deliberately make no claim about clean Git checkouts. Human
reports and AI judgments are labeled separately from frozen Chromium assertions.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import secrets

from jsonschema import Draft202012Validator

from . import chat_build, gameplay, playtests, polish, polish_runtime, project_plan
from .attempts import Attempts, status as attempt_status
from .core import canonical, content_hash, digest, subset, validate
from .intake import FINDING_SCHEMA, Intake
from .owner_review import OwnerReview, decide, load_request
from .recovery import exclusive, read_json


def intake(folder):
    return Intake(chat_build.harness(folder), checked_path(Path(folder) / 'findings' / 'data'))


def checked_path(path):
    path = Path(path)
    if path.resolve() != path.absolute():
        raise ValueError('Finding workspace path changed')
    return path


def save_input(path, data):
    path = checked_path(path)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('Retained finding input changed')
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)


def add_scope_permissions(scope, folder):
    work = (Path(folder) / 'findings').as_posix() + '/**'
    scope['allowed_paths']['read'].append(work)
    scope['allowed_paths']['read'].append((chat_build.harness(folder).root / 'triage' / 'fix_contracts').as_posix() + '/**')
    scope['allowed_paths']['write'].append(work)
    scope['allowed_actions'] += actions(folder)


def actions(folder):
    work = Path(folder) / 'findings'
    inputs = (work / 'inputs').as_posix() + '/**'
    bugs = (work / 'data' / 'bugs').as_posix() + '/BUG-*.json'
    path = dict(path_within=bugs)
    note = dict(pattern=r'^[\s\S]{1,2000}$')
    specs = [
        ('inspect', 'triage.inspect', 'read', dict(path=dict(path_within=inputs))),
        ('ingest', 'triage.ingest', 'write', dict(source=dict(path_within=inputs), dest=path)),
        ('severity', 'triage.review_severity', 'write', dict(path=path, severity=dict(one_of=['S0', 'S1', 'S2', 'S3']),
                                                         demo_impact=dict(one_of=[True, False]), note=note)),
        ('duplicate', 'triage.confirm_duplicate', 'write', dict(path=path, target=path, note=note)),
        ('reopen', 'triage.reopen', 'write', dict(path=path, reason=note)),
        ('close', 'triage.close', 'bug_close', dict(bug_id=dict(pattern=r'^BUG-[0-9]+$'), severity=dict(one_of=['S0', 'S1', 'S2', 'S3'])))]
    return [dict(action_id='finding-' + key, tool=tool, **{'class': kind}, args_constraints=args, allow_no_evidence=True)
            for key, tool, kind, args in specs]


def requests(folder):
    if not (Path(folder) / 'build-authority').exists():
        return []
    h = chat_build.harness(folder)
    entries = h._entries()
    decisions = {e['request_ref']: e for e in entries if e['kind'] == 'owner_decision'}
    rows = []
    for event in entries:
        if event['kind'] == 'owner_request':
            packet = load_request(h, event['request_ref'])
            if 'finding_submission' in packet['body'] or 'finding_closure' in packet['body']:
                rows.append(dict(ref=event['request_ref'], payload=packet, decision=decisions.get(event['request_ref'])))
    return rows


def _current(root, folder, request_ref, manifest):
    verified = chat_build.verify(root, folder)
    latest = chat_build.status(root, folder)['completed'][-1]
    if latest['request_ref'] != request_ref or verified['manifest'] != manifest:
        raise ValueError('Finding build is stale; playtest the current approved build')


def describe(root, folder, report_id, request_ref, fields, *, bug_id=None, bug_hash=None):
    """Turn a tester's description into the existing reviewed finding workflow."""
    allowed = {'summary', 'area', 'symptom_tag', 'steps', 'expected', 'actual', 'frequency', 'impact', 'demo_impact'}
    if not isinstance(fields, dict) or set(fields) - allowed:
        raise ValueError('Supply finding details only; build identity and evidence come from the host')
    from .intake import tag
    details = dict(area='browser_game', frequency='once', impact='degraded')
    details.update(fields)
    if not details.get('symptom_tag') and isinstance(details.get('summary'), str):
        details['symptom_tag'] = tag(details['summary'])[:128]
    Draft202012Validator(FINDING_SCHEMA).validate(dict(details, source='playtest'))
    if (any(not isinstance(details.get(key), str) or not details[key].strip()
            for key in ('summary', 'expected', 'actual')) or not details.get('steps') or
            any(not step.strip() for step in details['steps'])):
        raise ValueError('Describe the bug, how to repeat it, what you expected and what happened')
    if not project_plan.context(root, folder):
        raise ValueError('Approve a project plan before submitting findings')
    playtests.record(root, Path(folder), report_id, request_ref, 'problem', details['summary'], [])
    return prepare(root, folder, report_id, details, bug_id=bug_id, bug_hash=bug_hash)


def prepare(root, folder, report_id, fields, *, bug_id=None, bug_hash=None):
    """Stage a human report, then review intake/QA authority under the project scope."""
    with exclusive(Path(folder) / 'chat.lock'), exclusive(Path(folder) / 'build.lock'):
        frozen = project_plan.context(root, folder)
        if not frozen:
            raise ValueError('Approve a project plan before submitting findings')
        parent = project_plan.check_binding(root, folder, frozen['binding'])
        allowed = {'summary', 'area', 'symptom_tag', 'steps', 'expected', 'actual', 'frequency', 'impact', 'demo_impact'}
        if not isinstance(fields, dict) or set(fields) - allowed:
            raise ValueError('Supply finding details only; build identity and evidence come from the host')
        report = next((e for e in playtests.reports(folder) if e['report_id'] == report_id and e['outcome'] == 'problem'), None)
        if not report:
            raise ValueError('Choose a recorded problem playtest from this session')
        _current(root, folder, report['request_ref'], report['manifest'])
        if bug_id:
            prior = intake(folder).get(bug_id)
            if prior['record_hash'] != bug_hash or prior['state'] in ('closed', 'duplicate'):
                raise ValueError('Review the current open finding before updating it')
            if Attempts(chat_build.harness(folder)).status(bug_id)['status'] == 'in_progress':
                raise ValueError('Stop or finish the active fix before changing its finding')
        evidence = canonical(report)
        evidence_hash = sha256(evidence).hexdigest()
        target = Path(folder) / 'findings' / 'inputs' / (evidence_hash + '.json')
        finding = dict(fields, source='playtest', build_id=report['request_ref'], build_family=Path(folder).name,
                       evidence=[dict(path=target.as_posix(), sha256=evidence_hash)])
        Draft202012Validator(FINDING_SCHEMA).validate(finding)
        if not finding['summary'].strip() or any(not s.strip() for s in finding.get('steps', [])):
            raise ValueError('Describe the finding')
        existing = next((r for r in requests(folder) if r['payload']['body'].get('finding_submission', {}).get('identity') ==
                         digest(dict(finding=finding, bug_id=bug_id, bug_hash=bug_hash))), None)
        if existing:
            return dict(request_ref=existing['ref'])
        save_input(target, evidence)
        source = target.parent / ('finding-' + digest(finding) + '.json')
        save_input(source, canonical(finding))
        contracts = []
        token = secrets.token_hex(12)
        for role, agent in [('triage', 'ember-finding-intake'), ('verifier', 'ember-finding-qa')]:
            c = deepcopy(parent)
            c.update(id='ct-finding-' + role + '-' + token + '-0001', version=1, agent=agent, status='draft',
                     approved_by=None, approved_at=None, content_hash=None, goal='Record and review local browser findings',
                     inputs=[dict(name='finding', path=source.as_posix(), sha256=polish_runtime.file_digest(source)),
                             dict(name='playtest', path=target.as_posix(), sha256=evidence_hash)])
            c['extensions']['orchestration'] = dict(role=role)
            c['extensions']['lineage'] = dict(supersedes=None, amendment_log=[], derived_from=None)
            c['extensions']['triage'] = dict(review_role='QA') if role == 'verifier' else {}
            c['allowed_paths'] = dict(read=[(Path(folder) / 'findings').as_posix() + '/**'],
                                     write=[(intake(folder).root).as_posix() + '/**'])
            tools = ('triage.inspect', 'triage.ingest') if role == 'triage' else ('triage.review_severity', 'triage.confirm_duplicate', 'triage.reopen')
            c['allowed_actions'] = [a for a in actions(folder) if a['tool'] in tools]
            c['required_evidence'] = {}
            validate(c)
            if not subset(c, parent):
                raise ValueError('Amend or renew the project plan to review finding permissions first')
            contracts.append(dict(contract=c, parent_id=parent['id']))
        h = chat_build.harness(folder)
        for item in contracts:
            h.save_draft(item['contract'])
        submission = dict(identity=digest(dict(finding=finding, bug_id=bug_id, bug_hash=bug_hash)),
                          finding=finding, source=source.as_posix(), project_plan=frozen['binding'],
                          manifest=report['manifest'], bug_id=bug_id, bug_hash=bug_hash)
        ref = OwnerReview()._request(h, 'contracts', dict(contracts=contracts, finding_submission=submission), wait=False)
        return dict(request_ref=ref)


def respond(root, folder, ref, choice, quote):
    with exclusive(Path(folder) / 'chat.lock'), exclusive(Path(folder) / 'build.lock'):
        h = chat_build.harness(folder)
        packet = next((r for r in requests(folder) if r['ref'] == ref), None)
        if not packet:
            raise ValueError('Choose a finding review from this session')
        body = packet['payload']['body']
        if packet['decision'] and (packet['decision']['choice'], packet['decision']['quote']) != (choice, quote):
            raise ValueError('Finding review already has a different owner decision')
        prior_closure = next((e for e in h._entries() if e.get('run_id') == body['finding_closure']['run_id']
                              and e.get('status') == 'closed'), None) if 'finding_closure' in body else None
        if packet['decision'] and choice == 'approve' and prior_closure:
            return dict(status='closed', status_basis=prior_closure['seq'])
        if choice != 'decline':
            if 'finding_submission' in body:
                sub = body['finding_submission']
                project_plan.check_binding(root, folder, sub['project_plan'])
                _current(root, folder, sub['finding']['build_id'], sub['manifest'])
            else:
                closure_proof(root, folder, body['finding_closure']['run_id'])
        if not packet['decision']:
            decide(h, ref, choice, quote)
        if choice == 'decline':
            return dict(status='declined')
        if 'finding_closure' in body:
            return close(root, folder, body['finding_closure']['run_id'])
        sub = body['finding_submission']
        existing = next((e for e in h._entries() if e.get('operation') in ('ingest', 'update') and
                         e.get('contract_id') == body['contracts'][0]['contract']['id']), None)
        if existing:
            return dict(bug_id=existing['records'][0]['id'])
        if read_json(sub['source']) != sub['finding']:
            raise ValueError('Reviewed finding changed')
        if not h.verify_inputs(body['contracts'][0]['contract']['id']):
            raise ValueError('Reviewed finding evidence changed')
        result = intake(folder).ingest(sub['source'], contract_id=body['contracts'][0]['contract']['id'],
                                      bug_id=sub['bug_id'], expected_hash=sub['bug_hash'])
        return dict(bug_id=result['bugs'][0]['id'])


def qa(root, folder, action, bug_id, bug_hash, note, **fields):
    with exclusive(Path(folder) / 'chat.lock'), exclusive(Path(folder) / 'build.lock'):
        frozen = project_plan.context(root, folder)
        if not frozen:
            raise ValueError('Approve a project plan before reviewing findings')
        project_plan.check_binding(root, folder, frozen['binding'] if frozen else None)
        service = next((r for r in reversed(requests(folder)) if r['decision'] and r['decision']['choice'] == 'approve'
                        and 'finding_submission' in r['payload']['body'] and
                        r['payload']['body']['finding_submission']['project_plan']['ref'] == frozen['binding']['ref']), None)
        if not service:
            raise ValueError('Review finding intake and QA permissions first')
        cid = service['payload']['body']['contracts'][1]['contract']['id']
        queue = intake(folder)
        if not queue.h.verify_inputs(cid):
            raise ValueError('Reviewed QA inputs changed')
        if attempt_status(queue.h._entries(), bug_id)['status'] == 'in_progress':
            raise ValueError('Stop or finish the active fix before changing its finding')
        if action == 'severity':
            return queue.review_severity(bug_id, contract_id=cid, expected_hash=bug_hash,
                                         severity=fields['severity'], demo_impact=fields['demo_impact'], note=note)
        if action == 'duplicate':
            return queue.confirm_duplicate(bug_id, fields['target_id'], contract_id=cid, bug_hash=bug_hash,
                                           target_hash=fields['target_hash'], note=note)
        if action == 'reopen':
            return queue.reopen(bug_id, contract_id=cid, expected_hash=bug_hash,
                                expected_state_hash=fields['state_hash'], reason=note)
        raise ValueError('Unknown finding review action')


def configure(root, folder, plan, bug_id, bug_hash, scenario):
    bug = intake(folder).get(bug_id)
    if bug['record_hash'] != bug_hash:
        raise ValueError('Finding changed; review its current details')
    if bug['state'] != 'triaged' or bug['severity_review_required'] or not bug['route']['code_fix_allowed']:
        raise ValueError('Finding is not ready for an in-scope code fix; review the canonical reproduction and route')
    if bug['build_id'] != chat_build.status(root, folder)['completed'][-1]['request_ref']:
        raise ValueError('Finding build is stale; update its reproduction on the current build')
    _current(root, folder, bug['build_id'], plan['base_manifest'])
    count = len(plan['gameplay_plan']['plan']['scenarios'])
    if type(scenario) is not int or not 0 <= scenario < count:
        raise ValueError('Choose the saved gameplay scenario that reproduces this finding')
    state = Attempts(chat_build.harness(folder)).status(bug_id)
    if state['status'] != 'ready':
        raise ValueError('Finding attempt is ' + state['status'] + '; review the existing run or owner escalation')
    plan.update(kind='finding', goal='Fix ' + bug_id + ': ' + bug['title'], rounds=1, credits=10,
                finding=dict(bug=bug, regression_scenario=scenario),
                notice='One scoped bug attempt, at most $10 shared promotional credits. Frozen baseline repro, separate candidate verification, exact build review and explicit closure remain separate.')


def configure_contracts(folder, work, plan, contracts):
    coder, verifier = [item['contract'] for item in contracts]
    verifier['approval_mode'] = 'each'
    snapshot = intake(folder).snapshot(plan['finding']['bug']['id'], coder['id'])
    coder['extensions']['triage'] = dict(bug_id=snapshot['id'])
    verifier['allowed_actions'].append(dict(action_id='close', tool='triage.close', **{'class': 'bug_close'},
        args_constraints=dict(bug_id=dict(equals=snapshot['id']), severity=dict(equals=plan['finding']['bug']['severity'])),
        allow_no_evidence=True))
    verifier['allowed_actions'][0]['args_constraints']['path']['one_of'] += [(work / 'captures' / '0' / 'input.json').as_posix()]
    for c in (coder, verifier):
        c['inputs'].append(dict(name='bug_snapshot', path=snapshot['path'], sha256=snapshot['sha256']))


def check_binding(folder, plan):
    if intake(folder).get(plan['finding']['bug']['id'])['record_hash'] != plan['finding']['bug']['record_hash']:
        raise ValueError('Finding changed since the fix was reviewed')


def regression_failed(plan, observed):
    gameplay.validate_result(plan['gameplay_plan']['plan'], observed.get('gameplay'))
    index = plan['finding']['regression_scenario']
    steps = plan['gameplay_plan']['plan']['scenarios'][index]['steps']
    actual = observed['gameplay']['scenarios'][index]['steps']
    return any(s['action'] in ('visible', 'hidden', 'text', 'contains', 'number_at_least') and a['status'] == 'failed'
               for s, a in zip(steps, actual))


def baseline(worker, files):
    worker.contract = worker.packet['body']['contracts'][1]['contract']
    observed = worker.browser(0, files)
    if not regression_failed(worker.plan, observed):
        raise polish.Stopped('Saved regression did not reproduce this finding; review its steps and expectations')


def verify_report(work, plan):
    source = work / 'captures' / '0' / 'input.json'
    observed = polish_runtime.verified_report(source, source.parent / 'output')
    if not regression_failed(plan, observed):
        raise ValueError('A failing frozen baseline assertion is required')
    return observed


class FixAttempts:
    """Adapt the existing approval-allocated bug ledger to the task executor."""
    def __init__(self, h, plan, contract):
        self.h, self.plan, self.contract = h, plan, contract

    def begin(self, run_id, index):
        state = Attempts(self.h).status(self.plan['finding']['bug']['id'])
        attempt = next((a for a in state['attempts'] if a['contract_id'] == self.contract['id']), None)
        if not attempt or attempt['status'] != 'running':
            raise ValueError('A running approved bug attempt is required')
        return attempt

    def finish(self, attempt, report, path):
        if report['qualified']:
            return
        with self.h._lock():
            if any(e['kind'] == 'state_transition' and e.get('detail', {}).get('scope') == 'browser_bug_attempt'
                   and e['contract_id'] == self.contract['id'] for e in self.h._entries()):
                return
            self.h._append('state_transition', detail=dict(scope='browser_bug_attempt'),
                bug_id=self.plan['finding']['bug']['id'], contract_id=self.contract['id'], contract_version=1,
                attempt_number=attempt['number'], attempt_status='failed', run_id=self.plan['id'],
                report_path=Path(path).as_posix(), report_sha256=polish_runtime.file_digest(path))

    def abandon(self, run_id, reason):
        with self.h._lock():
            state = Attempts(self.h).status(self.plan['finding']['bug']['id'])
            attempt = next((a for a in state['attempts'] if a['contract_id'] == self.contract['id'] and a['status'] == 'running'), None)
            if attempt:
                self.h._append('state_transition', detail=dict(scope='browser_bug_abandoned'),
                    bug_id=self.plan['finding']['bug']['id'], contract_id=self.contract['id'], contract_version=1,
                    attempt_number=attempt['number'], attempt_status='abandoned', run_id=run_id,
                    actor='ember-host', actor_type='host', reason=reason)


def validate_failure(h, event):
    from .task_run import completed_report, load
    folder = h.root.parent
    work, _, packet, plan = load(folder, event['run_id'])
    if (plan.get('kind') != 'finding' or packet['body']['contracts'][0]['contract']['id'] != event['contract_id'] or
            event['bug_id'] != plan['finding']['bug']['id'] or event['contract_version'] != 1 or event['attempt_status'] != 'failed'):
        raise ValueError('Failed browser attempt lacks its reviewed binding')
    report = completed_report(folder, plan['id'], 1)
    if not report or report['qualified'] or event['report_path'] != (work / 'reports' / '1.json').as_posix() or event['report_sha256'] != polish_runtime.file_digest(event['report_path']):
        raise ValueError('Failed browser attempt lacks its retained independent report')


def validate_abandonment(h, event):
    from .task_run import load
    _, _, packet, plan = load(h.root.parent, event['run_id'])
    if (plan.get('kind') != 'finding' or packet['body']['contracts'][0]['contract']['id'] != event['contract_id'] or
            plan['finding']['bug']['id'] != event['bug_id'] or event['contract_version'] != 1 or
            event['attempt_status'] != 'abandoned' or event['actor_type'] != 'host' or not event['reason'].strip()):
        raise ValueError('Abandoned browser attempt differs from its approved run')


def closure_proof(root, folder, run_id):
    from . import task_run
    work, h, packet, plan = task_run.load(folder, run_id)
    if plan.get('kind') != 'finding':
        raise ValueError('Choose a finding fix run')
    project_plan.check_binding(root, folder, plan['project_plan']['binding'])
    check_binding(folder, plan)
    report = task_run.completed_report(folder, run_id, 1)
    if not report or not report['qualified']:
        raise ValueError('A qualified independent fix report is required')
    if gameplay.load(folder) != plan['gameplay_plan']:
        raise ValueError('Gameplay plan changed since verification')
    entries = h._entries()
    promoted = next((e for e in entries if e['kind'] == 'task_run_promoted' and e['run_id'] == run_id), None)
    if not promoted:
        raise ValueError('Review and apply the exact fix before closure')
    if plan.get('git_repair'):
        from .git_automation import witness
        witness(folder, run_id, promoted['request_ref'])
    _current(root, folder, promoted['request_ref'], report['manifest'])
    active = h._active(entries)
    for item in packet['body']['contracts']:
        c = item['contract']
        if c['id'] not in active or content_hash(h._authority(active[c['id']], active)) != content_hash(c) or not h.verify_inputs(c['id']):
            raise ValueError('Fix or verifier authority is inactive or changed')
    coder, verifier = [item['contract'] for item in packet['body']['contracts']]
    if coder['agent'] == verifier['agent']:
        raise ValueError('Fix reviewer must differ from author')
    state = Attempts(h).status(plan['finding']['bug']['id'])
    if not any(a['contract_id'] == coder['id'] and a['status'] == 'running' for a in state['attempts']):
        raise ValueError('The approved fix attempt is no longer running')
    if (work / 'stop.json').exists():
        raise ValueError('The fix was stopped')
    return h, plan, coder, verifier, promoted, report


def prepare_close(root, folder, run_id):
    with exclusive(Path(folder) / 'chat.lock'), exclusive(Path(folder) / 'build.lock'):
        h, plan, coder, verifier, promoted, report = closure_proof(root, folder, run_id)
        git_context = {}
        if plan.get('git_repair'):
            from .git_automation import witness
            git_context['git_verification'] = witness(folder, run_id, promoted['request_ref'])
        action = dict(agent=verifier['agent'], contract_id=verifier['id'], contract_version=verifier['version'],
                      tool='triage.close', args=dict(bug_id=plan['finding']['bug']['id'], severity=plan['finding']['bug']['severity']),
                      paths=dict(read=[], write=[]), spend=0)
        ref = OwnerReview()._request(h, 'action', dict(action=action, contract_hash=content_hash(verifier),
            finding_closure=dict(run_id=run_id, bug=plan['finding']['bug'], build_ref=promoted['request_ref'],
                                 report=report, **git_context,
                                 notice='Explicit bug closure; task and asset acceptance remain separate.')), wait=False)
        return dict(request_ref=ref)


def close(root, folder, run_id):
    h, plan, coder, verifier, promoted, report = closure_proof(root, folder, run_id)
    git_context = {}
    if plan.get('git_repair'):
        from .git_automation import witness
        git_context['git_verification'] = witness(folder, run_id, promoted['request_ref'])
    if not any(r['decision'] and r['decision']['choice'] == 'approve' and
               r['payload']['body'].get('finding_closure', {}).get('run_id') == run_id for r in requests(folder)):
        raise ValueError('Explicit owner closure approval required')
    action = dict(agent=verifier['agent'], contract_id=verifier['id'], contract_version=1, tool='triage.close',
                  args=dict(bug_id=plan['finding']['bug']['id'], severity=plan['finding']['bug']['severity']),
                  paths=dict(read=[], write=[]), spend=0)
    decision = h.check(action)
    if decision['decision'] != 'allow':
        raise ValueError('Explicit owner closure approval required: ' + decision['reason'])
    with h._lock():
        entries = h._entries()
        if intake(folder).get(plan['finding']['bug']['id'])['record_hash'] != plan['finding']['bug']['record_hash']:
            raise ValueError('Finding changed before closure')
        active = h._active(entries)
        for c in (coder, verifier):
            if c['id'] not in active or content_hash(h._authority(active[c['id']], active)) != content_hash(c):
                raise ValueError('Fix authority changed before closure')
        if chat_build.context(root, folder)['manifest'] != report['manifest']:
            raise ValueError('Applied fix changed before closure')
        e = h._append('state_transition', bug_id=plan['finding']['bug']['id'], severity=plan['finding']['bug']['severity'],
            status='closed', build=promoted['request_ref'], fix_contract_id=coder['id'], fix_version=1,
            verifier_contract_id=verifier['id'], verifier_version=1, author=coder['agent'], reviewer=verifier['agent'],
            review_kind='browser_regression_and_separate_ai_judgment', run_id=run_id, decision_seq=decision['audit_seq'],
            checkpoints=dict(C0='captures/0', C1='reports/1.json', C2=promoted['request_ref'], C3='explicit_owner_closure'),
            **git_context)
    return dict(status='closed', status_basis=e['seq'])


def validate_history(h, entries):
    """Recheck historical browser closure witnesses without requiring today's build."""
    from . import task_run
    count = 0
    for index, event in enumerate(entries):
        if event.get('review_kind') != 'browser_regression_and_separate_ai_judgment':
            continue
        count += 1
        folder = h.root.parent
        work, _, packet, plan = task_run.load(folder, event['run_id'])
        coder, verifier = [item['contract'] for item in packet['body']['contracts']]
        bug = plan['finding']['bug']
        report = task_run.completed_report(folder, event['run_id'], 1)
        promoted = next((e for e in entries[:index] if e['kind'] == 'task_run_promoted' and e['run_id'] == plan['id']), None)
        applied = next((e for e in entries[:index] if e['kind'] == 'chat_build_completed' and e['request_ref'] == event['build']), None)
        decision = entries[event['decision_seq'] - 1]
        expected_action = dict(agent=verifier['agent'], contract_id=verifier['id'], contract_version=1, tool='triage.close',
            args=dict(bug_id=bug['id'], severity=bug['severity']), paths=dict(read=[], write=[]), spend=0)
        if plan.get('git_repair'):
            from .git_automation import witness
            # The outer pass is validating this closure. Its Git witness checks
            # contracts/commits/source/captures without recursing into C3 again.
            if not promoted or event.get('git_verification') != witness(folder, plan['id'], promoted['request_ref'], _checking_closure=True):
                raise ValueError('Historical finding closure lost its clean Git witness')
        if (event['status'] != 'closed' or event['bug_id'] != bug['id'] or event['severity'] != bug['severity'] or
                event['fix_contract_id'] != coder['id'] or event['verifier_contract_id'] != verifier['id'] or
                event['author'] != coder['agent'] or event['reviewer'] != verifier['agent'] or coder['agent'] == verifier['agent'] or
                not report or not report['qualified'] or not promoted or promoted['request_ref'] != event['build'] or
                not applied or applied['manifest'] != report['manifest'] or
                decision['seq'] >= event['seq'] or decision.get('decision') != 'allow' or decision.get('action') != expected_action):
            raise ValueError('Browser closure differs from its frozen fix and applied evidence')
        owner = next((r for r in requests(folder) if r['decision'] and r['decision']['seq'] < event['seq'] and
                      r['decision']['choice'] == 'approve' and r['payload']['body'].get('finding_closure', {}).get('run_id') == plan['id']), None)
        if not owner:
            raise ValueError('Browser closure lacks an explicit owner decision')
        approval = entries[decision['approval_ref'] - 1]
        if approval.get('scope') != 'action' or approval['seq'] not in owner['decision']['approval_seqs']:
            raise ValueError('Browser closure did not consume the exact owner action approval')
    return count


def history(root, folder):
    if not (Path(folder) / 'build-authority').exists():
        return []
    h = chat_build.harness(folder)
    entries = h._entries()
    rows = []
    for bug in intake(folder).list():
        attempts = Attempts(h).status(bug['id'])
        run = next((e for e in reversed(entries) if e['kind'] == 'approval' and (e.get('bug_attempt') or {}).get('bug_id') == bug['id']), None)
        run_id = None
        if run:
            c = h._load(run)
            run_id = c.get('extensions', {}).get('task_run', {}).get('id')
        rows.append(dict(bug=bug, attempts=attempts, run_id=run_id,
                         closure=next((e for e in reversed(entries) if e.get('status') == 'closed' and e.get('bug_id') == bug['id']), None)))
    return rows
