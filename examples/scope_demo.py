"""Offline CLI end-to-end scope workflow; all approvals are isolated test fixtures."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    folder = ROOT / '.harness' / 'demos' / ('scope-' + uuid.uuid4().hex[:10])
    folder.mkdir(parents=True)
    store = folder / 'state'
    rows = []

    def save(name, value):
        path = folder / (name + '.json')
        path.write_text(json.dumps(value, indent=2), encoding='utf-8')
        return str(path)

    def cli(*args, fail=False):
        result = subprocess.run([sys.executable, '-m', 'ember_harness', '--store', str(store), *map(str, args)],
                                cwd=ROOT, capture_output=True, text=True, timeout=60)
        if fail:
            assert result.returncode != 0, result.stdout
            return json.loads(result.stderr or result.stdout)
        assert result.returncode == 0, result.stderr or result.stdout
        return json.loads(result.stdout)

    def check(label, request, decision):
        path = save('action', request)
        result = cli('check', path, fail=decision == 'deny')
        assert result['decision'] == decision, result
        rows.append((label, decision))
        return result

    proposal = cli('scope-propose', 'ct-scope-demo-0001', 'planner',
                   'Ember Courier: carry embers past water and deliver them to a brazier.',
                   '--workspace', folder)
    proposal_file = save('proposal', proposal)
    reviewed = cli('scope-review', proposal_file)
    assert reviewed['proposed_game']['game_concept'] == proposal['intent_text']
    assert reviewed['assumptions']['assumed_fields']
    cli('save', proposal_file)
    child = deepcopy(proposal)
    child.update(id='ct-scope-worker-0001', agent='writer')
    child['extensions']['orchestration']['role'] = 'coding'
    child_file = save('child', child)
    cli('save', child_file)
    target = folder / 'scope-output' / 'design.txt'
    message = 'Ember Courier local scope demonstration\n'
    request = dict(agent='writer', contract_id=child['id'], tool='fs.write',
                   args=dict(path=target.as_posix(), content=message),
                   paths=dict(read=[], write=[target.as_posix()]), spend=0)
    check('Draft child cannot execute', request, 'deny')
    quote = 'SIMULATED approval for isolated end-to-end test only; no production authority.'
    def approve(c, reviewed_hash, parent=None, fail=False):
        args = ['approve', c['id'], '1', '--reviewed-hash', reviewed_hash, '--quote', quote]
        if parent:
            args += ['--parent', parent]
        return cli(*args, fail=fail)
    from ember_harness import content_hash
    assert 'approved scope' in approve(child, content_hash(child), proposal['id'], fail=True)['error']
    rows.append(('Child approval before scope approval', 'rejected'))
    changed = deepcopy(proposal)
    changed['extensions']['scope']['features'].append('Unreviewed multiplayer')
    cli('save', save('changed-proposal', changed))
    assert 'reviewed draft changed' in approve(changed, reviewed['reviewed_hash'], fail=True)['error']
    rows.append(('Edited proposal with stale reviewed hash', 'rejected'))
    cli('save', proposal_file)
    approved = approve(proposal, reviewed['reviewed_hash'])['contract']
    rows.append(('Reviewed scope approval', 'approved fixture'))
    check('Scope approval alone cannot authorize child', request, 'deny')
    scope_action = {**request, 'agent': 'planner', 'contract_id': proposal['id']}
    check('Scope ceiling cannot execute a write', scope_action, 'deny')
    child['limits']['time_window'] = approved['limits']['time_window']
    cli('save', save('child', child))
    approve(child, content_hash(child), proposal['id'])
    allowed = check('Separately approved child writes inside scope', request, 'allow')
    target.parent.mkdir(parents=True)
    target.write_bytes(message.encode())
    evidence = [{'kind': 'file_hash', 'params': {'path': target.as_posix(), 'sha256': sha256(target.read_bytes()).hexdigest()}}]
    result = cli('verify-evidence', child['id'], 'write', save('evidence', evidence), '--decision-seq', allowed['audit_seq'])
    assert result['status'] == 'complete', result
    rows.append(('Executed output and SHA-256 evidence', 'complete'))
    outside = folder / 'outside.txt'
    denied = deepcopy(request)
    denied['args']['path'] = outside.as_posix()
    denied['paths']['write'] = [outside.as_posix()]
    check('Write outside scope', denied, 'deny')
    assert not outside.exists()
    wider = deepcopy(child)
    wider['id'] = 'ct-scope-wider-0001'
    wider['allowed_paths']['write'].append(folder.as_posix() + '/*.txt')
    cli('save', save('wider-child', wider))
    assert 'exceeds scope' in approve(wider, content_hash(wider), proposal['id'], fail=True)['error']
    rows.append(('Child requesting wider folders', 'rejected'))
    cli('revoke', proposal['id'], '--reason', 'End isolated fixture demo')
    check('Scope revocation disables child', request, 'deny')
    assert cli('audit-verify')['ok']
    assert cli('contract-lock')['ok']
    rows.append(('Audit and contract-lock', 'pass'))
    report = folder / 'SCOPE_DEMO.md'
    report.write_text('\n'.join(['# Intent-to-scope end-to-end demo', '',
        'Offline CLI run. All approvals are simulated fixtures. Review is deterministic; no live AI or human approval is claimed.', '',
        '| Scenario | Result |', '|---|---|'] + [f'| {a} | {b} |' for a, b in rows]) + '\n', encoding='utf-8')
    print(json.dumps({'passed': True, 'report': str(report), 'scenarios': rows}, indent=2))
    return {'report': report, 'scenarios': rows}


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    main()
