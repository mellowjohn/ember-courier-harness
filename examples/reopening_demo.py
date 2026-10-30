"""Real closure -> QA reopening -> retriage -> new fix -> second closure."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ember_harness import canonical, content_hash, draft
from ember_harness.attempts import Attempts
from ember_harness.contract_lock import git, verify
from ember_harness.staged_fix import close_bug, run_test
from examples.intake_demo import ingest
from examples.staged_fix_demo import main as staged_demo, FIXED, REGRESSION


def closure_args(d):
    return dict(bug_id='BUG-0001', severity='S2', fix_id=d['fix']['id'], verifier_id=d['verifier']['id'],
        source_path=d['source'].as_posix(), pre_seq=d['pre']['execution_seq'], post_seq=d['post']['execution_seq'],
        review_seq=d['review']['execution_seq'], verify_seq=d['qa']['execution_seq'], build=d['build'], pre_build=d['pre_build'], repo=d['repo'])


def second_cycle(d, ctx, pre_build, regression):
    h, repo, source = d['harness'], d['repo'], d['source']
    fix_id, verifier_id = 'ct-fix-reopened-0002', 'ct-verifier-reopened-0002'
    branch = 'round/2/' + fix_id
    scope = draft('ct-reopen-fix-scope-0001', 'demo-planner', 'Fix the reported recurrence and verify a second closure', role='scope')
    old = json.loads(h._path('ct-fix-scope-0001', 1).read_text())
    for key in ('limits', 'allowed_paths', 'allowed_actions', 'required_evidence'):
        scope[key] = deepcopy(old[key])
    scope['approval_mode'] = 'approve_all'
    for action in scope['allowed_actions']:
        if action['action_id'] == 'regression':
            action['args_constraints']['script'] = {'equals': regression.as_posix()}
        if 'branch' in action['args_constraints']:
            action['args_constraints']['branch'] = {'equals': branch}
    original_regression = d['repo'] / 'scripts/test_reward.py'
    scope['allowed_actions'].append({'action_id': 'original_regression', 'tool': 'test.run', 'class': 'compute', 'args_constraints': {'script': {'equals': original_regression.as_posix()}}})
    scope['required_evidence']['original_regression'] = [{'kind': 'output_snippet', 'params': {'pattern': r'\bOK\b'}}]
    snap = ctx['intake'].snapshot('BUG-0001', fix_id)
    review_script = repo / 'scripts/review_reward.py'
    inputs = [{'name': name, 'path': path.as_posix(), 'sha256': sha256(path.read_bytes()).hexdigest()}
              for name, path in [('bug_snapshot', Path(snap['path'])), ('regression', regression), ('review_script', review_script), ('original_regression', original_regression)]]
    fix, verifier = deepcopy(scope), deepcopy(scope)
    fix.update(id=fix_id, agent='demo-fix-author')
    fix['extensions']['orchestration']['role'] = 'coding'
    fix['extensions']['triage'] = {'bug_id': 'BUG-0001', 'author': fix['agent'], 'reviewer': 'demo-verifier'}
    fix['allowed_actions'] = [a for a in fix['allowed_actions'] if a['action_id'] in ('edit', 'regression', 'stage', 'commit')]
    fix['required_evidence'] = {k: v for k, v in fix['required_evidence'].items() if k in ('edit', 'regression', 'commit')}
    verifier.update(id=verifier_id, agent='demo-verifier')
    verifier['extensions']['orchestration']['role'] = 'verifier'
    verifier['allowed_paths']['write'] = []
    verifier['allowed_actions'] = [a for a in verifier['allowed_actions'] if a['action_id'] in ('regression', 'review', 'close', 'original_regression')]
    verifier['required_evidence'] = {k: v for k, v in verifier['required_evidence'].items() if k in ('regression', 'review', 'original_regression')}
    for c in (fix, verifier):
        c['inputs'] = deepcopy(inputs)
    for c, parent in ((scope, None), (fix, scope['id']), (verifier, scope['id'])):
        h.save_draft(c)
        h.approve(c['id'], 1, approver='johnathan', quote='Explicit local reopening demo fixture approval', expected_hash=content_hash(c), parent_id=parent)
        assert h.verify_inputs(c['id'])
    def action(c, tool, args, read=(), write=()):
        return dict(agent=c['agent'], contract_id=c['id'], tool=tool, args=args, paths={'read': [p.as_posix() for p in read], 'write': [p.as_posix() for p in write]}, spend=0)
    def test(c, script, action_id, capture=True):
        run = run_test(h, action(c, 'test.run', {'script': script.as_posix()}, read=[source, script]))
        if capture:
            items = [{'kind': 'output_snippet', 'params': {'text': run['stdout'] + run['stderr']}}]
            if action_id == 'review':
                items.append({'kind': 'reviewer_note', 'params': {'reviewer': c['agent'], 'role': 'automated_verifier', 'note': run['stdout']}})
            assert h.verify_evidence(c['id'], action_id, items, decision_seq=run['decision_seq'])['status'] == 'complete'
        return run
    pre = test(fix, regression, 'regression', capture=False)
    assert pre['returncode'] == 1 and 'AssertionError' in pre['stderr']
    edit = h.check(action(fix, 'fs.write', {'path': source.as_posix(), 'content': FIXED}, write=[source]))
    assert edit['decision'] == 'allow'
    source.write_bytes(FIXED.encode())
    assert h.verify_evidence(fix_id, 'edit', [{'kind': 'file_hash', 'params': {'path': source.as_posix(), 'sha256': sha256(FIXED.encode()).hexdigest()}}], decision_seq=edit['audit_seq'])['status'] == 'complete'
    post = test(fix, regression, 'regression')
    git(repo, 'switch', '-c', branch)
    approved = json.loads(h._path(fix_id, 1).read_text())
    message = f"Fix BUG-0001 recurrence\n\nAuthor: demo-fix-author\nReviewer: demo-verifier\n\nRound: 2\nContract-Id: {fix_id}\nContract-Version: 1\nContract-Hash: {approved['content_hash']}\nSubsystem: triage\n"
    assert h.check(action(fix, 'git.add', {'branch': branch, 'path': source.as_posix()}, write=[source]))['decision'] == 'allow'
    git(repo, 'add', '--', 'src/reward.py')
    result = verify(h.root, repo=repo, base=pre_build, staged_message=message)
    assert result['ok'], result
    commit = h.check(action(fix, 'git.commit', {'branch': branch, 'message': message}, write=[source]))
    assert commit['decision'] == 'allow'
    message_path = d['folder'] / 'reopening-commit-message.txt'
    message_path.write_text(message, encoding='utf-8')
    git(repo, 'commit', '--file', str(message_path))
    build = git(repo, 'rev-parse', 'HEAD').decode().strip()
    assert h.verify_evidence(fix_id, 'commit', [{'kind': 'output_snippet', 'params': {'text': build}}], decision_seq=commit['audit_seq'])['status'] == 'complete'
    review = test(verifier, review_script, 'review')
    test(verifier, original_regression, 'original_regression')
    qa = test(verifier, regression, 'regression')
    index = h.root / 'triage/regression/index.json'
    registered = json.loads(index.read_text())
    registered.append(dict(bug_id='BUG-0001', test_path=regression.as_posix(), build_introduced=build, command='test.run'))
    index.write_bytes(canonical(registered))
    return close_bug(h, bug_id='BUG-0001', severity='S2', fix_id=fix_id, verifier_id=verifier_id, source_path=source.as_posix(),
        pre_seq=pre['execution_seq'], post_seq=post['execution_seq'], review_seq=review['execution_seq'], verify_seq=qa['execution_seq'],
        build=build, pre_build=pre_build, repo=repo)


def main():
    d = staged_demo(with_intake=True)
    h, ctx = d['harness'], d['intake_context']
    intake, attempts, rows = ctx['intake'], Attempts(h), []
    def show(label, result):
        rows.append((label, result))
        print(label + ': ' + result)
    show('First closure', 'Real failing regression, approved fix, local commit and distinct verifier; CLOSED at attempt 1')
    # Explicit fixture bootstrap introduces a new recurrence on an untested coin count.
    d['source'].write_bytes(b'def delivery_reward(coins):\n    return coins - 1 if coins == 2 else coins\n')
    regression = d['repo'] / 'scripts/test_reward_recurrence.py'
    regression.write_bytes(REGRESSION.replace('(0, 1, 5, 100)', '(0, 1, 2, 5, 100)').encode())
    git(d['repo'], 'add', '--', 'src/reward.py', 'scripts/test_reward_recurrence.py')
    git(d['repo'], 'commit', '-m', 'Fixture bootstrap: introduce recurrence on two-coin delivery')
    pre_build = git(d['repo'], 'rev-parse', 'HEAD').decode().strip()
    bug, state = intake.get('BUG-0001'), attempts.status('BUG-0001')
    reopened = intake.reopen('BUG-0001', contract_id=ctx['reviewer']['id'], expected_hash=bug['record_hash'],
        expected_state_hash=state['state_hash'], reason='Demo QA fixture reports delivery of two coins awards one on build ' + pre_build)
    assert reopened['bugs'][0]['state'] == 'reopened' and reopened['attempts']['attempts_started'] == 1
    show('QA reopens the closed bug', 'REOPENED; returned to QA; original successful attempt and closure preserved')
    try:
        intake.snapshot('BUG-0001', 'ct-fix-too-early-0001')
        raise AssertionError('reopened bug requires fresh triage')
    except ValueError as error:
        show('Start a fix before retriage', 'DENIED: ' + str(error))
    try:
        close_bug(h, **closure_args(d))
        raise AssertionError('old closure evidence cannot close reopened bug')
    except ValueError as error:
        show('Reuse the old fix and closure evidence', 'DENIED: ' + str(error))
    updated = {**ctx['finding'], 'build_id': pre_build, 'summary': 'Two-coin delivery loses one coin', 'steps': ['Deliver two coins', 'Inspect reward'], 'expected': 'Two coins', 'actual': 'One coin'}
    bug = ingest(ctx, 'recurrence', updated, bug_id='BUG-0001', expected_hash=intake.get('BUG-0001')['record_hash'])
    assert bug['state'] == 'triaged' and bug['reopen_count'] == 1
    show('Fresh finding is triaged', 'TRIAGED; next attempt is 2, counter unchanged')
    closure = second_cycle(d, ctx, pre_build, regression)
    assert closure['status'] == 'closed'
    state = attempts.status('BUG-0001')
    assert state['status'] == 'closed' and state['attempts_started'] == 2 and all(a['status'] == 'succeeded' for a in state['attempts'])
    show('Second fix and closure', 'New frozen snapshot, contract, regression failure, fix commit and verifier evidence; CLOSED at attempt 2')
    lock = verify(h.root, repo=d['repo'], base=pre_build)
    assert lock['ok'], lock
    show('Contract-lock and audit verification', 'PASS; both closure entries and reopening remain in history')
    report = d['folder'] / 'REOPENING_DEMO.md'
    lines = ['# Reopening a closed bug', '', 'All approvals and QA identities are explicit local fixtures. Both fix cycles execute actual tests and create local commits. Structural review uses a deterministic checker; no human or independent AI review is claimed. A fixture bootstrap introduces the recurrence.', '', '| Step | Actual result |', '|---|---|']
    lines += [f'| {label} | {result} |' for label, result in rows]
    lines += ['', f"[Audit log](<{h.audit_path.as_posix()}>) · [New regression](<{regression.as_posix()}>)", '', 'Reopening never resets spent attempts. At three attempts, a separate Johnathan retry decision is still required; S0/S1 reclosure still needs owner approval.', '', 'Rerun: `py examples/reopening_demo.py`']
    report.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Report: ' + str(report))
    return {**d, 'report': report, 'reopening_closure': closure}


if __name__ == '__main__':
    main()
