"""Hash-bound QA proposals and owner reconciliation of terminal duplicate histories."""
from pathlib import Path
import json
import re

from .core import canonical, digest
from .intake import records, merge_records, check_evidence
from .attempts import status


def plan_for(entries, root, bug_id, target_id, reviewer, note):
    bugs = records(entries, root)
    a, b = bugs[bug_id], bugs[target_id]
    if a['id'] == b['id'] or any(x['state'] in ('duplicate', 'closed', 'reopened') for x in (a, b)):
        raise ValueError('current open canonical bugs required')
    if not any(x['bug_id'] == b['id'] for x in a['duplicate_candidates']) and not any(x['bug_id'] == a['id'] for x in b['duplicate_candidates']):
        raise ValueError('no duplicate candidate to reconcile')
    ordered = sorted((a, b), key=lambda x: x['created_seq'])
    states = [status(entries, x['id']) for x in ordered]
    if any(st['status'] in ('in_progress', 'closed') for st in states):
        raise ValueError('finish or revoke running attempts before reconciliation; closed bugs require reopening')
    return {'intake_root': root, 'bugs': [x['id'] for x in ordered],
            'bug_hashes': [x['record_hash'] for x in ordered], 'states': states,
            'state_hashes': [x['state_hash'] for x in states],
            'attempts_started': sum(x['attempts_started'] for x in states),
            'canceled_retry_refs': [x['retry_approval_ref'] for x in states if x['retry_approval_ref']],
            'preserve_stop': any(x['status'] == 'stopped' for x in states),
            'reviewer': reviewer, 'note': note,
            'result_records': list(merge_records(*ordered))}


class Reconciliation:
    def __init__(self, intake):
        self.intake, self.h = intake, intake.h

    def _path(self, ref):
        if not isinstance(ref, str) or re.fullmatch('[0-9a-f]{64}', ref) is None:
            raise ValueError('reviewed reconciliation hash required')
        return self.h.root / 'triage/reconciliations' / (ref + '.json')

    def _current(self, plan):
        a, b = (self.intake.get(x) for x in plan['bugs'])
        c = self.intake._reviewer(plan['reviewer']['contract_id'], [a, b])
        if c['version'] != plan['reviewer']['version'] or c['agent'] != plan['reviewer']['agent']:
            raise ValueError('QA approval changed; propose again')
        for bug in (a, b):
            check_evidence(bug, self.intake.root)
        rebuilt = plan_for(self.h._entries(), self.intake.root.as_posix(), *plan['bugs'], plan['reviewer'], plan['note'])
        if rebuilt != plan:
            raise ValueError('stale reconciliation; review a new proposal')
        return c

    def propose(self, bug_id, target_id, *, contract_id, bug_hash, target_hash, note):
        if not isinstance(note, str) or not note.strip():
            raise ValueError('QA reviewer note required')
        a, b = self.intake.get(bug_id), self.intake.get(target_id)
        c = self.intake._reviewer(contract_id, [a, b])
        _, gate = self.intake._gate(contract_id, 'triage.confirm_duplicate', self._args([bug_id, target_id], note))
        with self.h._lock():
            a, b = self.intake.get(bug_id), self.intake.get(target_id)
            if [a['record_hash'], b['record_hash']] != [bug_hash, target_hash]:
                raise ValueError('stale bug hashes')
            reviewer = {'contract_id': contract_id, 'version': c['version'], 'agent': c['agent']}
            plan = plan_for(self.h._entries(), self.intake.root.as_posix(), bug_id, target_id, reviewer, note)
            self._current(plan)
            ref = digest(plan)
            path = self._path(ref)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and path.read_bytes() != canonical(plan):
                raise ValueError('immutable reconciliation plan was changed')
            path.write_bytes(canonical(plan))
            self.h._append('duplicate_reconciliation_proposed', plan=plan, plan_hash=ref, decision_seq=gate['audit_seq'])
            return {'plan_hash': ref, 'plan': plan, 'path': path.as_posix()}

    def _args(self, bugs, note):
        return {'path': (self.intake.root / 'bugs' / (bugs[0] + '.json')).as_posix(),
                'target': (self.intake.root / 'bugs' / (bugs[1] + '.json')).as_posix(), 'note': note}

    def approve(self, plan_hash, *, approver, quote):
        if approver != 'johnathan' or not isinstance(quote, str) or not quote.strip():
            raise ValueError("Johnathan's own recorded reconciliation approval required")
        plan = json.loads(self._path(plan_hash).read_text(encoding='utf-8'))
        if digest(plan) != plan_hash or plan['intake_root'] != self.intake.root.as_posix():
            raise ValueError('reconciliation plan hash or workspace mismatch')
        self._current(plan)
        cid = plan['reviewer']['contract_id']
        _, gate = self.intake._gate(cid, 'triage.confirm_duplicate', self._args(plan['bugs'], plan['note']))
        with self.h._lock():
            entries = self.h._entries()
            if not any(e.get('kind') == 'duplicate_reconciliation_proposed' and e.get('plan_hash') == plan_hash and e.get('plan') == plan for e in entries):
                raise ValueError('audited QA proposal required')
            if any(e.get('scope') == 'duplicate_reconciliation' and e.get('plan_hash') == plan_hash for e in entries):
                raise ValueError('reconciliation already consumed')
            self._current(plan)
            decision = entries[gate['audit_seq'] - 1]
            result = self.intake._commit(cid, decision, 'reconcile_duplicates', plan['result_records'], event_kind='approval',
                scope='duplicate_reconciliation', actor_type='human', actor=approver, quote=quote,
                plan_hash=plan_hash, reconciliation={'bugs': plan['bugs'], 'state_hashes': plan['state_hashes']},
                reviewer_note={'reviewer': plan['reviewer']['agent'], 'role': 'QA', 'note': plan['note'], 'label': 'self_reported'})
            return {**result, 'attempts': status(self.h._entries(), plan['bugs'][0])}


def validate_history(harness, entries):
    proposals = {}
    consumed = set()
    for index, event in enumerate(entries):
        if event['kind'] == 'duplicate_reconciliation_proposed':
            plan, ref = event['plan'], event['plan_hash']
            if digest(plan) != ref or re.fullmatch('[0-9a-f]{64}', ref) is None:
                raise ValueError('invalid reconciliation proposal hash')
            path = harness.root / 'triage/reconciliations' / (ref + '.json')
            if json.loads(path.read_text(encoding='utf-8')) != plan:
                raise ValueError('reconciliation proposal file differs from audit')
            decision = entries[event['decision_seq'] - 1]
            if decision.get('decision') != 'allow' or decision.get('action', {}).get('tool') != 'triage.confirm_duplicate' or decision['seq'] >= event['seq']:
                raise ValueError('QA reconciliation proposal lacks allowed decision')
            expected_paths = {(Path(plan['intake_root']) / 'bugs' / (b + '.json')).as_posix() for b in plan['bugs']}
            args = decision.get('action', {}).get('args', {})
            if {args.get('path'), args.get('target')} != expected_paths or args.get('note') != plan['note']:
                raise ValueError('QA proposal gate differs from reviewed bugs or note')
            prefix = entries[:index]
            reviewer = plan['reviewer']
            active = harness._active(prefix)
            approval = active.get(reviewer['contract_id'])
            if not approval:
                raise ValueError('active QA contract required for reconciliation')
            c = harness._authority(approval, active)
            bugs = records(prefix, plan['intake_root'])
            if (c['version'] != reviewer['version'] or c['agent'] != reviewer['agent'] or
                c['extensions']['orchestration']['role'] != 'verifier' or c['extensions'].get('triage', {}).get('review_role') != 'QA' or
                any(bugs[b]['created_by'] == c['agent'] for b in plan['bugs']) or not plan['note'].strip() or
                decision.get('contract_id') != c['id']):
                raise ValueError('invalid reconciliation QA identity')
            if plan_for(prefix, plan['intake_root'], *plan['bugs'], reviewer, plan['note']) != plan:
                raise ValueError('proposal differs from historical bug and attempt state')
            proposals[ref] = plan
        elif event.get('scope') == 'duplicate_reconciliation':
            ref = event['plan_hash']
            plan = proposals.get(ref)
            if not plan or ref in consumed or event.get('actor') != 'johnathan' or event.get('actor_type') != 'human' or not event.get('quote', '').strip():
                raise ValueError('invalid or reused owner reconciliation approval')
            if plan_for(entries[:index], plan['intake_root'], *plan['bugs'], plan['reviewer'], plan['note']) != plan:
                raise ValueError('owner approved stale reconciliation')
            if event['reconciliation'] != {'bugs': plan['bugs'], 'state_hashes': plan['state_hashes']}:
                raise ValueError('reconciliation ledger differs from reviewed plan')
            active = harness._active(entries[:index])
            qa = active.get(plan['reviewer']['contract_id'])
            if not qa or qa['contract_version'] != plan['reviewer']['version']:
                raise ValueError('QA authority changed before reconciliation')
            decision = entries[event['decision_seq'] - 1]
            expected_args = {'path': (Path(plan['intake_root']) / 'bugs' / (plan['bugs'][0] + '.json')).as_posix(),
                             'target': (Path(plan['intake_root']) / 'bugs' / (plan['bugs'][1] + '.json')).as_posix(), 'note': plan['note']}
            if (decision['seq'] >= event['seq'] or decision.get('contract_id') != plan['reviewer']['contract_id'] or
                    decision.get('contract_version') != plan['reviewer']['version'] or decision.get('action', {}).get('args') != expected_args or
                    event.get('intake_root') != plan['intake_root'] or event.get('detail', {}).get('scope') != 'bug_intake'):
                raise ValueError('owner reconciliation lacks matching QA gate and workspace')
            from .intake import seal
            expected = [seal(dict(b), event['seq']) for b in plan['result_records']]
            if event['records'] != expected or event.get('operation') != 'reconcile_duplicates':
                raise ValueError('reconciliation records differ from reviewed plan')
            consumed.add(ref)
