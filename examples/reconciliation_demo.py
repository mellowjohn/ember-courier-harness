"""Run real failed fixes, then reconcile late duplicates using fixture approvals."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ember_harness import content_hash, draft
from ember_harness.attempts import Attempts
from ember_harness.reconciliation import Reconciliation
from ember_harness.contract_lock import verify
from examples.intake_demo import setup as intake_setup, ingest
from examples.attempt_demo import CANDIDATES, TEST, exercise


def setup(folder=None):
    folder = Path(folder) if folder else Path(__file__).resolve().parents[1] / '.harness/demos' / ('reconciliation-' + uuid.uuid4().hex[:10])
    ctx = intake_setup(folder)
    for name in ('src', 'scripts'):
        (folder / name).mkdir()
    ctx['source'], ctx['script'] = folder / 'src/reward.py', folder / 'scripts/regression.py'
    ctx['source'].write_bytes(CANDIDATES[0].encode())
    ctx['script'].write_bytes(TEST.encode())
    scope = draft('ct-reconcile-fix-scope-0001', 'fix-planner', 'Bounded regression fixes for the local reconciliation demo', role='scope')
    scope['approval_mode'] = 'approve_all'
    scope['limits'] = deepcopy(ctx['scope']['limits'])
    scope['allowed_paths'] = {'read': [(folder / 'src').as_posix() + '/*.py', (folder / 'scripts').as_posix() + '/*.py', (ctx['h'].root / 'triage/fix_contracts').as_posix() + '/*/*.json'], 'write': [(folder / 'src').as_posix() + '/*.py']}
    scope['allowed_actions'] = [
        {'action_id': 'edit', 'tool': 'fs.write', 'class': 'write', 'args_constraints': {'path': {'equals': ctx['source'].as_posix()}, 'content': {'one_of': CANDIDATES}}, 'allow_no_evidence': True},
        {'action_id': 'regression', 'tool': 'test.run', 'class': 'compute', 'args_constraints': {'script': {'equals': ctx['script'].as_posix()}}, 'allow_no_evidence': True}]
    ctx['h'].save_draft(scope)
    ctx['h'].approve(scope['id'], 1, approver='johnathan', quote='Local demo fixture scope approval', expected_hash=content_hash(scope))
    ctx['fix_scope'] = scope
    return ctx


def fix(ctx, bug_id, number):
    c = deepcopy(ctx['fix_scope'])
    c.update(id=f'ct-fix-{bug_id[4:]}-{number:04d}', agent=f'fix-{bug_id}-{number}')
    c['extensions']['orchestration']['role'] = 'coding'
    snap = ctx['intake'].snapshot(bug_id, c['id'])
    c['inputs'] = [{'name': 'bug_snapshot', 'path': snap['path'], 'sha256': snap['sha256']}, {'name': 'regression', 'path': ctx['script'].as_posix(), 'sha256': sha256(ctx['script'].read_bytes()).hexdigest()}]
    code = CANDIDATES[min(number - 1, 3)]
    c['allowed_actions'][0]['args_constraints']['content'] = {'equals': code}
    c['required_evidence'] = {'edit': [{'kind': 'file_hash', 'params': {'path': ctx['source'].as_posix(), 'sha256': sha256(code.encode()).hexdigest()}}]}
    h = ctx['h']
    h.save_draft(c)
    h.approve(c['id'], 1, approver='johnathan', quote='Local demo fixture fix approval', expected_hash=content_hash(c), parent_id=ctx['fix_scope']['id'])
    assert h.verify_inputs(c['id'])
    return c


def fail(ctx, bug, number):
    c = fix(ctx, bug, number)
    run, _ = exercise(ctx, c)
    assert run['returncode'] == 1 and 'AssertionError' in run['stderr']
    return Attempts(ctx['h']).fail(c['id'], execution_seq=run['execution_seq'], reason='Actual edited candidate fails pinned regression')


def propose(ctx, a, b):
    return Reconciliation(ctx['intake']).propose(a['id'], b['id'], contract_id=ctx['reviewer']['id'], bug_hash=a['record_hash'], target_hash=b['record_hash'], note='Demo QA fixture confirms identical reproduction and symptom')


def main():
    ctx = setup()
    a, b = ingest(ctx, 'first'), ingest(ctx, 'second')
    rows = []
    def show(label, value):
        rows.append((label, value))
        print(label + ': ' + value)
    fail(ctx, a['id'], 1)
    fail(ctx, a['id'], 2)
    fail(ctx, b['id'], 1)
    show('Before merge', 'Oldest bug: 2 failed attempts; duplicate: 1 failed attempt (real regression runs)')
    recon = Reconciliation(ctx['intake'])
    plan = propose(ctx, a, b)
    show('QA proposes', 'No merge yet; owner reviews immutable plan ' + plan['plan_hash'])
    try:
        recon.approve(plan['plan_hash'], approver='demo-qa', quote='QA cannot impersonate owner')
        raise AssertionError('QA approval must fail')
    except ValueError as error:
        show('QA tries owner approval', 'DENIED: ' + str(error))
    result = recon.approve(plan['plan_hash'], approver='johnathan', quote='Demo fixture owner approval of this exact reconciliation plan')
    st = result['attempts']
    assert st['attempts_started'] == 3 and st['failed_attempts'] == 3 and st['status'] == 'awaiting_decision'
    assert Attempts(ctx['h']).status(b['id'])['state_hash'] == st['state_hash']
    show('Owner approves merge', f"{b['id']} becomes alias of {a['id']}; all 3 attempts retained; awaiting owner decision")
    try:
        fix(ctx, a['id'], 4)
        raise AssertionError('fourth fix must be blocked')
    except ValueError as error:
        show('Attempt 4 after merge under approve_all', 'DENIED: ' + str(error))
    Attempts(ctx['h']).decide(a['id'], choice='retry', expected_state_hash=st['state_hash'], approver='johnathan', quote='Separate demo fixture owner decision authorizes one additional attempt')
    state = fail(ctx, a['id'], 4)
    assert state['attempts_started'] == 4 and state['status'] == 'awaiting_decision'
    show('Separate owner retry decision', 'Exactly one additional fix runs; its actual regression fails; escalated again at 4 attempts')
    lock = verify(ctx['h'].root)
    assert lock['ok'], lock
    show('Contract-lock and audit verification', 'PASS')
    report = ctx['folder'] / 'DEMO.md'
    lines = ['# Late duplicate owner reconciliation', '', 'All QA, contract and owner approvals below are local demo fixtures. Regression failures are actual captured executions. No authenticated human review is claimed.', '', '| Step | Actual result |', '|---|---|']
    lines += [f'| {label} | {value} |' for label, value in rows]
    lines += ['', '## Preserved attempt history', '', '| Combined number | Original bug | Original number | Contract | Status |', '|---|---|---|---|---|']
    lines += [f"| {x['number']} | {x.get('origin_bug_id', a['id'])} | {x.get('origin_number', x['number'])} | {x['contract_id']} | {x['status']} |" for x in state['attempts']]
    lines += ['', f"[Reviewed reconciliation plan](<{plan['path']}>) · [Audit log](<{ctx['h'].audit_path.as_posix()}>)", '', 'Rerun: `py examples/reconciliation_demo.py`']
    report.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Report: ' + str(report))
    return {**ctx, 'report': report}


if __name__ == '__main__':
    main()
