"""Manual PNG concept selection and create-only ingest through approved contracts."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import warnings

from jsonschema import Draft202012Validator
from PIL import Image

from .core import canonical, digest, draft, matches, normal

MAX_BYTES = 8 * 1024 * 1024
HASH = {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}
TEXT = {'type': 'string', 'minLength': 1, 'maxLength': 1000, 'pattern': r'\S'}
MANIFEST = {'type': 'object', 'additionalProperties': False, 'required': ['topic', 'candidates'],
    'properties': {'topic': TEXT, 'candidates': {'type': 'array', 'minItems': 3, 'maxItems': 4,
        'items': {'type': 'object', 'additionalProperties': False,
            'required': ['slug', 'path', 'sha256', 'pitch'], 'properties': {
                'slug': {'type': 'string', 'maxLength': 80, 'pattern': '^[a-z0-9]+(-[a-z0-9]+)*$'},
                'path': TEXT, 'sha256': HASH, 'pitch': TEXT,
                'target': {'type': 'array', 'minItems': 2, 'maxItems': 2,
                           'items': {'type': 'integer', 'minimum': 1, 'maximum': 4096}},
                'require_alpha': {'type': 'boolean'}}}}}}


def parse_manifest(raw):
    if len(raw) > 64 * 1024:
        raise ValueError('manifest exceeds 64 KiB')
    result = json.loads(raw.decode('utf-8-sig'))
    Draft202012Validator(MANIFEST).validate(result)
    for field in ('slug', 'path'):
        values = [c[field] if field == 'slug' else normal(c[field]) for c in result['candidates']]
        if len(set(values)) != len(values):
            raise ValueError('candidate slugs and resolved paths must be unique')
    return result


def capabilities(pattern):
    return [
        {'action_id': 'concept_select', 'tool': 'concept.select', 'class': 'direction_selection',
         'args_constraints': {'manifest': {'path_within': pattern}, 'review_ref': {'pattern': '^[0-9a-f]{64}$'},
                              'choice': {'pattern': '^[a-z0-9]+(-[a-z0-9]+)*$'}}, 'allow_no_evidence': True},
        {'action_id': 'asset_copy', 'tool': 'fs.copy', 'class': 'write',
         'args_constraints': {'src': {'path_within': pattern},
                              'dest': {'path_within': pattern, 'no_overwrite_unless_same_hash': True},
                              'expected_sha256': {'pattern': '^[0-9a-f]{64}$'}}, 'allow_no_evidence': False},
        {'action_id': 'asset_accept', 'tool': 'asset.accept', 'class': 'asset_acceptance',
         'args_constraints': {'path': {'path_within': pattern}, 'sha256': {'pattern': '^[0-9a-f]{64}$'}},
         'allow_no_evidence': True},
    ]


class Assets:
    def __init__(self, harness):
        self.h = harness

    def contract(self, cid, role='asset-step'):
        active = self.h._active(self.h._entries())
        if cid not in active:
            raise ValueError('active approved contract required')
        c = self.h._authority(active[cid], active)
        if c['extensions']['orchestration']['role'] != role or not c.get('art_direction'):
            raise ValueError('asset-step contract with inherited art direction required')
        return c

    def proposal(self, scope_id, manifest_path, cid, agent):
        scope = self.contract(scope_id, 'scope')
        path = normal(str(manifest_path))
        if not any(matches(path, p) for p in scope['allowed_paths']['read']):
            raise ValueError('manifest outside scope')
        with Path(path).open('rb') as stream:
            raw = stream.read(64 * 1024 + 1)
        manifest = parse_manifest(raw)
        c = draft(cid, agent, 'Review, select and ingest one supplied PNG concept', role='asset-step')
        c['allowed_paths'] = deepcopy(scope['allowed_paths'])
        c['allowed_actions'] = deepcopy([a for a in scope['allowed_actions']
                                        if a['tool'] in ('fs.read', 'fs.copy', 'concept.select', 'asset.accept')])
        if {a['tool'] for a in c['allowed_actions']} != {'fs.read', 'fs.copy', 'concept.select', 'asset.accept'}:
            raise ValueError('scope lacks asset capabilities; propose a scope amendment first')
        c['required_evidence'] = {a['action_id']: deepcopy(scope['required_evidence'][a['action_id']])
                                 for a in c['allowed_actions'] if a['action_id'] in scope['required_evidence']}
        c['limits'] = deepcopy(scope['limits'])
        c['approval_mode'] = scope.get('approval_mode', 'each')
        c['art_direction'] = deepcopy(scope['art_direction'])
        c['inputs'] = [{'name': 'concept_manifest', 'path': path, 'sha256': sha256(raw).hexdigest()}]
        c['inputs'] += [{'name': 'candidate_' + v['slug'], 'path': normal(v['path']), 'sha256': v['sha256']}
                        for v in manifest['candidates']]
        c['extensions']['asset_workflow'] = {'manifest': path}
        from .core import validate, subset
        validate(c)
        if not subset(c, scope):
            raise ValueError('asset contract exceeds scope')
        return c

    def action(self, c, tool, args):
        from .core import TOOLS
        paths = {mode: [args[k] for k, access in TOOLS[tool]['paths'].items() if access == mode]
                 for mode in ('read', 'write')}
        return dict(agent=c['agent'], contract_id=c['id'], contract_version=c['version'],
                    tool=tool, args=args, paths=paths, spend=0)

    def gate(self, c, tool, args):
        action = self.action(c, tool, args)
        result = self.h.check(action)
        return result, action

    def allowed(self, c, tool, args):
        result, _ = self.gate(c, tool, args)
        if result['decision'] != 'allow':
            raise ValueError('asset action denied: ' + result['reason'])
        return result['audit_seq']

    def pinned(self, c, path, limit=MAX_BYTES):
        path = normal(path)
        pin = next((v for v in c['inputs'] if v.get('path') == path and v.get('sha256') and not v.get('late_bind')), None)
        if not pin or not any(matches(path, p) for p in c['allowed_paths']['read']):
            raise ValueError('every input must be pinned inside approved read paths')
        with Path(path).open('rb') as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit or sha256(raw).hexdigest() != pin['sha256']:
            raise ValueError('input changed or exceeds byte limit')
        return raw

    def current(self, c):
        latest = self.contract(c['id'])
        if latest['content_hash'] != c['content_hash']:
            raise ValueError('asset contract changed')
        from .core import timestamp
        window = latest['limits']['time_window']
        if not timestamp(window['not_before']) <= self.h.clock() <= timestamp(window['not_after']):
            raise ValueError('asset contract expired')

    def review(self, cid):
        c = self.contract(cid)
        path = c['extensions']['asset_workflow']['manifest']
        seqs = [self.allowed(c, 'fs.read', {'path': path})]
        raw = self.pinned(c, path, 64 * 1024)
        manifest = parse_manifest(raw)
        candidates = []
        for v in manifest['candidates']:
            seqs.append(self.allowed(c, 'fs.read', {'path': v['path']}))
            data = self.pinned(c, v['path'])
            if sha256(data).hexdigest() != v['sha256']:
                raise ValueError('candidate differs from manifest hash')
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as image:
                    if image.format != 'PNG' or image.width * image.height > 16_777_216 or getattr(image, 'n_frames', 1) != 1:
                        raise ValueError('single PNG within pixel limit required')
                    image.verify()
                with Image.open(BytesIO(data)) as image:
                    image.load()
                    if v.get('target') and list(image.size) != v['target']:
                        raise ValueError('candidate dimensions differ from declared target')
                    alpha = 'A' in image.getbands() or 'transparency' in image.info
                    if v.get('require_alpha') and not alpha:
                        raise ValueError('candidate requires alpha')
                    candidates.append({**v, 'dimensions': list(image.size), 'alpha': alpha})
        payload = dict(contract_id=cid, contract_version=c['version'], contract_hash=c['content_hash'],
                       manifest=manifest, manifest_path=path, manifest_text=raw.decode('utf-8'),
                       manifest_sha256=sha256(raw).hexdigest(), art_direction_hash=digest(c['art_direction']),
                       art_direction=deepcopy(c['art_direction']), candidates=candidates,
                       label='Technically checked; awaiting Johnathan selection. Visual quality is unscored.')
        with self.h._lock():
            self.current(c)
            for p in [path] + [v['path'] for v in candidates]:
                self.pinned(c, p)
            ref = digest(payload)
            folder = self.h.root / 'concepts' / ref
            folder.mkdir(parents=True, exist_ok=True)
            snapshot = folder / 'review.json'
            if snapshot.exists() and snapshot.read_bytes() != canonical(payload):
                raise ValueError('concept review artifact changed')
            snapshot.write_bytes(canonical(payload))
            event = self.h._append('concept_review', contract_id=cid, contract_version=c['version'],
                                   review_ref=ref, decision_seqs=seqs)
        return dict(status='awaiting_pick', review_ref=ref, review_seq=event['seq'], review=payload)

    def snapshot(self, ref, c):
        payload = load_review(self.h, ref)
        if (payload['contract_id'], payload['contract_version'], payload['contract_hash']) != (c['id'], c['version'], c['content_hash']):
            raise ValueError('review belongs to a different contract version')
        if not any(e['kind'] == 'concept_review' and e['review_ref'] == ref for e in self.h._entries()):
            raise ValueError('audited concept review required')
        return payload

    def unchanged(self, c, payload):
        self.current(c)
        self.pinned(c, payload['manifest_path'], 64 * 1024)
        for v in payload['candidates']:
            self.pinned(c, v['path'])

    def select(self, cid, ref, choice):
        c = self.contract(cid)
        payload = self.snapshot(ref, c)
        if choice not in [v['slug'] for v in payload['candidates']]:
            raise ValueError('choice is not a reviewed candidate')
        result, action = self.gate(c, 'concept.select', dict(manifest=payload['manifest_path'], review_ref=ref, choice=choice))
        if result['decision'] != 'allow':
            return {**result, 'approval_action': action}
        with self.h._lock():
            self.unchanged(c, payload)
            if any(e['kind'] == 'concept_selection' and e['review_ref'] == ref for e in self.h._entries()):
                raise ValueError('selection already recorded; use an amendment for a new pick')
            event = self.h._append('concept_selection', contract_id=cid, contract_version=c['version'],
                                   review_ref=ref, choice=choice, decision_seq=result['audit_seq'])
        return dict(status='selected', choice=choice, selection_seq=event['seq'])

    def selected(self, c, ref):
        payload = self.snapshot(ref, c)
        selections = [e for e in self.h._entries() if e['kind'] == 'concept_selection' and e['review_ref'] == ref]
        if len(selections) != 1:
            raise ValueError('one owner-approved selection required')
        v = next(v for v in payload['candidates'] if v['slug'] == selections[0]['choice'])
        return payload, v, selections[0]

    def ingest(self, cid, ref, dest):
        c = self.contract(cid)
        payload, v, selection = self.selected(c, ref)
        dest = normal(str(dest))
        seq = self.allowed(c, 'fs.copy', dict(src=v['path'], dest=dest, expected_sha256=v['sha256']))
        with self.h._lock():
            self.unchanged(c, payload)
            raw = self.pinned(c, v['path'])
            if normal(dest) != dest:
                raise ValueError('destination path changed')
            if not Path(dest).parent.is_dir():
                raise ValueError('destination parent must already exist')
            # Exclusive creation also rejects identical existing files and concurrent creates.
            with Path(dest).open('xb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if sha256(self.destination(c, {'dest': dest})).hexdigest() != v['sha256']:
                raise ValueError('destination changed during ingest')
            event = self.h._append('asset_ingest', contract_id=cid, contract_version=c['version'],
                review_ref=ref, selection_seq=selection['seq'], choice=v['slug'], source=v['path'],
                dest=dest, sha256=v['sha256'], bytes=len(raw), decision_seq=seq)
        action_id = next(a['action_id'] for a in c['allowed_actions'] if a['tool'] == 'fs.copy')
        evidence = self.h.verify_evidence(cid, action_id, [{'kind': 'source_dest_hash', 'params': {
            'source_path': v['path'], 'dest_path': dest, 'sha256': v['sha256']}}], decision_seq=seq)
        return dict(status='ingested' if evidence['status'] == 'complete' else 'incomplete',
                    ingest_seq=event['seq'], dest=dest, sha256=v['sha256'], evidence=evidence)

    def ingest_event(self, c, ref, dest):
        dest = normal(str(dest))
        self.selected(c, ref)
        events = [e for e in self.h._entries() if e['kind'] == 'asset_ingest' and e['review_ref'] == ref and e['dest'] == dest]
        if len(events) != 1:
            raise ValueError('unique audited ingest required')
        return events[0]

    def accept(self, cid, ref, dest):
        c = self.contract(cid)
        payload, _, _ = self.selected(c, ref)
        ingest = self.ingest_event(c, ref, dest)
        evidence = self.copy_evidence(c, ingest)
        if evidence['status'] != 'complete':
            raise ValueError('complete copy evidence required for acceptance')
        result, action = self.gate(c, 'asset.accept', dict(path=ingest['dest'], sha256=ingest['sha256']))
        if result['decision'] != 'allow':
            return {**result, 'approval_action': action}
        with self.h._lock():
            self.unchanged(c, payload)
            if sha256(self.destination(c, ingest)).hexdigest() != ingest['sha256']:
                raise ValueError('ingested file changed; acceptance refused')
            event = self.h._append('asset_acceptance', contract_id=cid, contract_version=c['version'],
                review_ref=ref, ingest_seq=ingest['seq'], evidence_seq=evidence['status_basis'], decision_seq=result['audit_seq'])
        return dict(status='accepted', acceptance_seq=event['seq'])

    def status(self, cid, ref, dest):
        c = self.contract(cid)
        payload, _, _ = self.selected(c, ref)
        ingest = self.ingest_event(c, ref, dest)
        try:
            self.unchanged(c, payload)
            if sha256(self.destination(c, ingest)).hexdigest() != ingest['sha256']:
                raise ValueError('ingested file changed')
            if self.copy_evidence(c, ingest)['status'] != 'complete':
                raise ValueError('copy evidence incomplete')
            accepted = any(e['kind'] == 'asset_acceptance' and e['ingest_seq'] == ingest['seq'] for e in self.h._entries())
            return dict(status='accepted' if accepted else 'awaiting_acceptance', sha256=ingest['sha256'])
        except (ValueError, OSError) as error:
            return dict(status='incomplete', reason=str(error))

    def destination(self, c, ingest):
        path = normal(ingest['dest'])
        if path != ingest['dest'] or not any(matches(path, p) for p in c['allowed_paths']['write']):
            raise ValueError('destination path changed or escaped contract')
        with Path(path).open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('destination exceeds byte limit')
        return data

    def copy_evidence(self, c, ingest):
        self.destination(c, ingest)
        action_id = next(a['action_id'] for a in c['allowed_actions'] if a['tool'] == 'fs.copy')
        return self.h.verify_evidence(c['id'], action_id, [{'kind': 'source_dest_hash', 'params': {
            'source_path': ingest['source'], 'dest_path': ingest['dest'], 'sha256': ingest['sha256']}}],
            decision_seq=ingest['decision_seq'])


def load_review(h, ref):
    if not isinstance(ref, str) or len(ref) != 64 or any(c not in '0123456789abcdef' for c in ref):
        raise ValueError('concept review hash required')
    payload = json.loads((h.root / 'concepts' / ref / 'review.json').read_bytes())
    if digest(payload) != ref:
        raise ValueError('concept review artifact changed')
    return payload


def validate_history(h, entries):
    """Verify retained snapshots and decision/owner links without requiring old files to stay current."""
    reviews, selections, ingests = {}, {}, {}
    count = 0
    def decision(event, tool, args, owner=False):
        seq = event['decision_seq']
        d = entries[seq - 1]
        if (d['seq'] >= event['seq'] or d['kind'] != 'decision' or d.get('decision') != 'allow' or
            d.get('contract_id') != event['contract_id'] or d.get('contract_version') != event['contract_version'] or
            d['action']['tool'] != tool or d['action']['args'] != args):
            raise ValueError('asset history differs from allowed decision')
        if owner:
            approval = entries[d['approval_ref'] - 1]
            if (approval['kind'] != 'approval' or approval.get('scope') != 'action' or
                approval.get('actor') != 'johnathan' or approval.get('actor_type') != 'human' or
                approval.get('contract_id') != event['contract_id'] or
                approval.get('contract_version') != event['contract_version'] or approval['seq'] >= d['seq'] or
                approval['action_hash'] != digest({k: d['action'][k] for k in ('agent', 'tool', 'args', 'paths', 'spend')})):
                raise ValueError('explicit owner approval required for asset decision')
    for event in entries:
        kind = event['kind']
        if kind not in ('concept_review', 'concept_selection', 'asset_ingest', 'asset_acceptance'):
            continue
        count += 1
        ref = event['review_ref']
        payload = load_review(h, ref)
        if (event['contract_id'], event['contract_version']) != (payload['contract_id'], payload['contract_version']):
            raise ValueError('asset event belongs to different review contract')
        if kind == 'concept_review':
            from .core import content_hash
            c = json.loads(h._path(event['contract_id'], event['contract_version']).read_bytes())
            if (content_hash(c) != payload['contract_hash'] or digest(c['art_direction']) != payload['art_direction_hash'] or
                c['art_direction'] != payload['art_direction'] or c['extensions']['orchestration']['role'] != 'asset-step' or
                c['extensions']['asset_workflow']['manifest'] != payload['manifest_path']):
                raise ValueError('concept snapshot differs from approved contract or art direction')
            raw = payload['manifest_text'].encode('utf-8')
            if sha256(raw).hexdigest() != payload['manifest_sha256'] or parse_manifest(raw) != payload['manifest']:
                raise ValueError('concept manifest snapshot changed')
            pins = {i.get('path'): i.get('sha256') for i in c['inputs'] if not i.get('late_bind')}
            paths = [payload['manifest_path']] + [v['path'] for v in payload['candidates']]
            if pins.get(payload['manifest_path']) != payload['manifest_sha256'] or len(event['decision_seqs']) != len(paths):
                raise ValueError('manifest not pinned or inspection decisions missing')
            if len(payload['candidates']) != len(payload['manifest']['candidates']):
                raise ValueError('candidate set changed')
            for declared, checked in zip(payload['manifest']['candidates'], payload['candidates']):
                if any(checked[k] != v for k, v in declared.items()) or pins.get(normal(checked['path'])) != checked['sha256']:
                    raise ValueError('candidate differs from pinned manifest')
            for path, seq in zip(paths, event['decision_seqs']):
                decision({**event, 'decision_seq': seq}, 'fs.read', {'path': path})
            reviews[ref] = payload
        elif ref not in reviews:
            raise ValueError('asset event precedes concept review')
        elif kind == 'concept_selection':
            if ref in selections or event['choice'] not in [v['slug'] for v in payload['candidates']]:
                raise ValueError('duplicate or invalid concept selection')
            decision(event, 'concept.select', dict(manifest=payload['manifest_path'], review_ref=ref, choice=event['choice']), True)
            selections[ref] = event
        elif kind == 'asset_ingest':
            selected = selections.get(ref)
            if not selected or event['selection_seq'] != selected['seq'] or event['choice'] != selected['choice']:
                raise ValueError('ingest lacks earlier owner selection')
            v = next(v for v in payload['candidates'] if v['slug'] == selected['choice'])
            if event['source'] != v['path'] or event['sha256'] != v['sha256'] or not 0 < event['bytes'] <= MAX_BYTES:
                raise ValueError('ingest differs from selected candidate')
            decision(event, 'fs.copy', dict(src=event['source'], dest=event['dest'], expected_sha256=event['sha256']))
            ingests[event['seq']] = event
        else:
            ingest = ingests.get(event['ingest_seq'])
            if not ingest or ingest['review_ref'] != ref:
                raise ValueError('acceptance lacks prior ingest')
            evidence = entries[event['evidence_seq'] - 1]
            if (evidence['kind'] != 'evidence' or evidence.get('status') != 'complete' or
                evidence.get('decision_seq') != ingest['decision_seq'] or evidence['seq'] >= event['seq']):
                raise ValueError('acceptance lacks complete copy evidence')
            decision(event, 'asset.accept', dict(path=ingest['dest'], sha256=ingest['sha256']), True)
    return count
