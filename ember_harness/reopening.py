"""Closed -> reopened -> fresh intake, with immutable closure and attempt history."""
from copy import deepcopy
from pathlib import Path

from .attempts import status
from .intake import records, seal, check_evidence


def transition(entries, root, bug_id, expected_hash, expected_state_hash, reason, seq):
    bug = records(entries, root).get(bug_id)
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('recurrence reason required')
    if not bug or bug['state'] != 'closed' or bug.get('duplicate_of'):
        raise ValueError('only the canonical closed bug can be reopened')
    current = status(entries, bug_id)
    if bug['record_hash'] != expected_hash or current['state_hash'] != expected_state_hash:
        raise ValueError('stale closed bug or attempt state; review current hashes')
    if current['status'] != 'closed':
        raise ValueError('current successful closed attempt required')
    closure_seq = current['attempts'][-1]['outcome_seq']
    closure = entries[closure_seq - 1]
    if closure.get('status') != 'closed' or closure.get('bug_id') != bug_id or closure_seq != bug['status_basis']:
        raise ValueError('current matching closure required')
    result = deepcopy(bug)
    result.update(state='reopened', owner='QA', reopen_count=bug.get('reopen_count', 0) + 1,
                  last_reopened_seq=seq, last_closure_seq=closure_seq)
    return result, closure


def reopen(intake, bug_id, *, contract_id, expected_hash, expected_state_hash, reason):
    bug = intake.get(bug_id)
    intake._reviewer(contract_id, [bug])
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError('recurrence reason required')
    _, gate = intake._gate(contract_id, 'triage.reopen',
                          {'path': (intake.root / 'bugs' / (bug_id + '.json')).as_posix(), 'reason': reason})
    with intake.h._lock():
        entries = intake.h._entries()
        bug, closure = transition(entries, intake.root.as_posix(), bug_id, expected_hash, expected_state_hash, reason, len(entries) + 1)
        c = intake._reviewer(contract_id, [bug])
        if c['agent'] == closure.get('author'):
            raise ValueError('reopening QA reviewer must differ from fix author')
        check_evidence(bug, intake.root)
        decision = entries[gate['audit_seq'] - 1]
        if decision['contract_version'] != c['version']:
            raise ValueError('QA contract changed before reopening')
        result = intake._commit(contract_id, decision, 'reopen', [bug], bug_id=bug_id, status='reopened',
            expected_hash=expected_hash, expected_state_hash=expected_state_hash, closure_seq=closure['seq'],
            reason=reason, reviewer_note={'reviewer': c['agent'], 'role': 'QA', 'note': reason, 'label': 'self_reported'})
        return {**result, 'attempts': status(intake.h._entries(), bug_id)}


def validate_history(harness, entries):
    for index, event in enumerate(entries):
        if event.get('operation') != 'reopen':
            continue
        if event['kind'] != 'state_transition' or event.get('detail', {}).get('scope') != 'bug_intake' or event.get('status') != 'reopened':
            raise ValueError('invalid reopening transition')
        bug, closure = transition(entries[:index], event['intake_root'], event['bug_id'], event['expected_hash'], event['expected_state_hash'], event['reason'], event['seq'])
        if event['records'] != [seal(bug, event['seq'])] or event['closure_seq'] != closure['seq']:
            raise ValueError('reopening differs from closed source record')
        active = harness._active(entries[:index])
        approval = active.get(event['contract_id'])
        if not approval:
            raise ValueError('active QA authority required for reopening')
        c = harness._authority(approval, active)
        if (c['version'] != event['contract_version'] or c['extensions']['orchestration']['role'] != 'verifier' or
                c['extensions'].get('triage', {}).get('review_role') != 'QA' or c['agent'] in (bug['created_by'], closure.get('author'))):
            raise ValueError('distinct approved QA reviewer required for reopening')
        decision = entries[event['decision_seq'] - 1]
        args = {'path': (Path(event['intake_root']) / 'bugs' / (event['bug_id'] + '.json')).as_posix(), 'reason': event['reason']}
        note = {'reviewer': c['agent'], 'role': 'QA', 'note': event['reason'], 'label': 'self_reported'}
        if (decision['seq'] >= event['seq'] or decision.get('decision') != 'allow' or decision.get('contract_id') != c['id'] or
                decision.get('contract_version') != c['version'] or decision.get('action', {}).get('tool') != 'triage.reopen' or
                decision['action']['args'] != args or event.get('reviewer_note') != note):
            raise ValueError('reopening lacks matching QA gate or recurrence note')
