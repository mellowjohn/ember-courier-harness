"""Trusted-host review inbox. Agents may propose; only an explicit owner response decides."""
import json
from pathlib import Path
import re
import time

from .core import canonical, content_hash, digest


class OwnerReview:
    mode = 'owner_review'

    def _request(self, h, kind, body, *, wait=True):
        payload = dict(kind=kind, store=h.root.as_posix(), body=body)
        ref = digest(payload)
        folder = h.root / 'owner-review' / ref
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / 'request.json'
        if path.exists() and path.read_bytes() != canonical(payload):
            raise ValueError('owner request changed')
        path.write_bytes(canonical(payload))
        lines = ['# Owner review: ' + kind, '', 'Pending — no approval has been granted.', '',
            f'Request hash: `{ref}`', '',
            'Review this exact packet. Approval grants only the contracts or action shown here. '
            'Declining stops the run. The local host records your response; this is not identity authentication.', '']
        if kind == 'contracts':
            for item in body['contracts']:
                c = item['contract']
                lines += [f"## {c['id']} v{c['version']}", '', c['goal'], '',
                          f"Reviewed hash: `{content_hash(c)}`", '', '```json',
                          json.dumps(c, indent=2), '```', '']
        elif kind == 'choice':
            lines += ['Choose one supplied original concept. Technical checks do not replace your visual judgment.', '']
            for option in body['options']:
                lines += ['## ' + option['choice'], '', option['pitch'], '',
                          f"![{option['choice']}](<{option['path']}>)", '',
                          f"SHA-256: `{option['sha256']}`", '']
        else:
            action = body['action']
            lines += ['```json', json.dumps(action, indent=2), '```', '']
            if action['tool'] == 'asset.accept':
                lines += [f"![Asset awaiting acceptance](<{action['args']['path']}>)", '']
        (folder / 'REVIEW.md').write_text('\n'.join(lines), encoding='utf-8')
        with h._lock():
            if not any(e['kind'] == 'owner_request' and e['request_ref'] == ref for e in h._entries()):
                h._append('owner_request', request_ref=ref, review_kind=kind)
        print(json.dumps(dict(status='awaiting_owner', request_ref=ref, store=h.root.as_posix(),
                              review=(folder / 'REVIEW.md').as_posix())), flush=True)
        if not wait:
            return ref
        while True:
            events = h._entries()
            result = next((e for e in events if e['kind'] == 'owner_decision' and e['request_ref'] == ref), None)
            if result:
                validate_history(h, events)
                if result['choice'] == 'decline':
                    raise ValueError('owner declined this request; run stopped')
                return result
            time.sleep(.5)

    def contracts(self, h, items):
        records = []
        for c, parent in items:
            if parent is None and c['extensions']['orchestration']['role'] != 'scope':
                parent = h._active(h._entries()).get(c['id'], {}).get('parent_id')
            prior = next((e for e in h._entries() if e['kind'] == 'approval' and
                e.get('scope') == 'contract' and e.get('contract_id') == c['id'] and
                e.get('contract_version') == c['version']), None)
            if prior:
                # Reopen the original review after a worker restart. Authority
                # still comes from its existing receipt; never approve on replay.
                if content_hash(c) != prior['reviewed_hash']:
                    raise ValueError('reviewed contract changed since approval')
                h._load(prior)
            else:
                h.save_draft(c)
            records.append(dict(contract=c, parent_id=parent))
        self._request(h, 'contracts', dict(contracts=records))
        active = h._active(h._entries())
        return [h._authority(active[c['id']], active) for c, _ in items]

    def contract(self, h, c, parent=None):
        return self.contracts(h, [(c, parent)])[0]

    def select(self, h, assets, c, review):
        options = []
        for v in review['review']['candidates']:
            action = assets.action(c, 'concept.select', dict(manifest=review['review']['manifest_path'],
                                   review_ref=review['review_ref'], choice=v['slug']))
            options.append(dict(choice=v['slug'], pitch=v['pitch'], path=v['path'], sha256=v['sha256'], action=action))
        result = self._request(h, 'choice', dict(options=options, contract_hash=c['content_hash']))
        chosen = result['choice']
        existing = [e for e in h._entries() if e['kind'] == 'concept_selection' and
                    e['review_ref'] == review['review_ref']]
        if existing:
            assets.unchanged(c, review['review'])
            if len(existing) != 1 or existing[0]['choice'] != chosen:
                raise ValueError('saved selection differs from owner response')
        elif assets.select(c['id'], review['review_ref'], chosen)['status'] != 'selected':
            raise ValueError('owner selection did not execute')
        return chosen

    def action(self, h, action):
        active = h._active(h._entries())
        c = h._authority(active[action['contract_id']], active)
        return self._request(h, 'action', dict(action=action, contract_hash=c['content_hash']))


def load_request(h, ref):
    if not re.fullmatch('[0-9a-f]{64}', ref):
        raise ValueError('owner request hash required')
    p = h.root / 'owner-review' / ref / 'request.json'
    payload = json.loads(p.read_bytes())
    if digest(payload) != ref or payload['store'] != h.root.as_posix():
        raise ValueError('owner request hash or store mismatch')
    if not any(e['kind'] == 'owner_request' and e['request_ref'] == ref for e in h._entries()):
        raise ValueError('audited owner request required')
    return payload


def decide(h, ref, choice, quote):
    """Human-facing host only. quote must relay the owner's actual response."""
    if not isinstance(quote, str) or not quote.strip():
        raise ValueError('actual owner response required')
    payload = load_request(h, ref)
    if any(e['kind'] == 'owner_decision' and e['request_ref'] == ref for e in h._entries()):
        raise ValueError('owner request already decided')
    kind, body = payload['kind'], payload['body']
    refs = []
    request_seq = next(e['seq'] for e in h._entries() if e['kind'] == 'owner_request' and e['request_ref'] == ref)
    # Check every reviewed draft before approving any member of a contract batch.
    if choice != 'decline':
        if kind == 'contracts':
            if choice != 'approve':
                raise ValueError('approve or decline required')
            for item in body['contracts']:
                c = item['contract']
                prior = next((e for e in h._entries() if e['kind'] == 'approval' and e.get('scope') == 'contract' and
                    e.get('contract_id') == c['id'] and e.get('contract_version') == c['version'] and
                    e.get('reviewed_hash') == content_hash(c) and e.get('quote') == quote and e['seq'] > request_seq), None)
                if prior:
                    continue
                current = json.loads(h._path(c['id'], c['version']).read_bytes())
                if current != c:
                    raise ValueError('reviewed contract changed; new owner review required')
            for item in body['contracts']:
                c = item['contract']
                prior = next((e for e in h._entries() if e['kind'] == 'approval' and e.get('scope') == 'contract' and
                    e.get('contract_id') == c['id'] and e.get('contract_version') == c['version'] and
                    e.get('reviewed_hash') == content_hash(c) and e.get('quote') == quote and e['seq'] > request_seq), None)
                if prior:
                    refs.append(prior['seq'])
                else:
                    result = h.approve(c['id'], c['version'], approver='johnathan', quote=quote,
                        expected_hash=content_hash(c), parent_id=item['parent_id'])
                    refs.append(result['approval_seq'])
        else:
            if kind == 'choice':
                option = next((v for v in body['options'] if v['choice'] == choice), None)
                if option is None:
                    raise ValueError('choose a reviewed candidate or decline')
                action = option['action']
            elif kind == 'action' and choice == 'approve':
                action = body['action']
            else:
                raise ValueError('invalid owner response')
            active = h._active(h._entries())
            c = h._authority(active[action['contract_id']], active)
            if c['content_hash'] != body['contract_hash']:
                raise ValueError('action authority changed since review')
            action_hash = digest({k: action[k] for k in ('agent', 'tool', 'args', 'paths', 'spend')})
            prior = next((e for e in h._entries() if e['kind'] == 'approval' and e.get('scope') == 'action' and
                e.get('action_hash') == action_hash and e.get('contract_id') == c['id'] and e.get('contract_version') == c['version'] and
                e.get('quote') == quote and e['seq'] > request_seq), None)
            refs.append(prior['seq'] if prior else h.approve_action(action, approver='johnathan', quote=quote)['seq'])
    with h._lock():
        event = h._append('owner_decision', request_ref=ref, choice=choice, quote=quote,
                          actor='johnathan', actor_type='human', approval_seqs=refs)
    report = h.root / 'owner-review' / ref / 'REVIEW.md'
    try:
        report.write_text(report.read_text(encoding='utf-8').replace('Pending — no approval has been granted.',
            ('DECLINED' if choice == 'decline' else 'APPROVED') + f" — owner response recorded at audit #{event['seq']}."), encoding='utf-8')
    except OSError:
        pass  # Audit is authoritative; a display failure must not duplicate the decision.
    return dict(status='declined' if choice == 'decline' else 'approved', decision_seq=event['seq'])


def validate_history(h, entries):
    count = 0
    seen = set()
    requested = {}
    for event in entries:
        if event['kind'] not in ('owner_request', 'owner_decision'):
            continue
        ref = event['request_ref']
        payload = load_request(h, ref)
        if event['kind'] == 'owner_request':
            if payload['kind'] != event['review_kind']:
                raise ValueError('owner review kind changed')
            requested[ref] = event['seq']
            continue
        count += 1
        if ref not in requested or ref in seen or event['actor'] != 'johnathan' or event['actor_type'] != 'human' or not event['quote'].strip():
            raise ValueError('duplicate or invalid owner decision')
        seen.add(ref)
        approvals = [entries[seq - 1] for seq in event['approval_seqs']]
        if event['choice'] == 'decline':
            if approvals:
                raise ValueError('decline cannot grant authority')
            continue
        for approval in approvals:
            if (approval['kind'] != 'approval' or approval.get('actor') != 'johnathan' or
                approval.get('actor_type') != 'human' or approval['quote'] != event['quote'] or not requested[ref] < approval['seq'] < event['seq']):
                raise ValueError('owner decision lacks corresponding explicit approval')
        if payload['kind'] == 'contracts':
            if event['choice'] != 'approve':
                raise ValueError('invalid owner contract response')
            expected = payload['body']['contracts']
            if len(approvals) != len(expected):
                raise ValueError('owner contract batch is incomplete')
            for approval, item in zip(approvals, expected):
                c = item['contract']
                if (approval.get('scope') != 'contract' or approval['contract_id'] != c['id'] or
                    approval['contract_version'] != c['version'] or approval['reviewed_hash'] != content_hash(c)):
                    raise ValueError('owner approval differs from reviewed draft')
        else:
            body = payload['body']
            if payload['kind'] == 'action' and event['choice'] != 'approve':
                raise ValueError('invalid owner action response')
            action = body['action'] if payload['kind'] == 'action' else next(v['action'] for v in body['options'] if v['choice'] == event['choice'])
            if len(approvals) != 1 or approvals[0].get('scope') != 'action' or approvals[0]['action_hash'] != digest({k: action[k] for k in ('agent', 'tool', 'args', 'paths', 'spend')}):
                raise ValueError('owner action differs from reviewed request')
    return count
