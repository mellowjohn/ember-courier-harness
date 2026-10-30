"""Real local failing-test → gated fix → commit → read-only verification demo.

Fixture identities and approvals are confined to this explicitly requested demo.
Automated structural review is not a human or independent AI peer review.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ember_harness import Harness, canonical, content_hash, draft
from ember_harness.contract_lock import git, verify as contract_lock
from ember_harness.staged_fix import run_test, close_bug


BROKEN = "def delivery_reward(coins):\n    return coins - 1\n"
FIXED = "def delivery_reward(coins):\n    return coins\n"
REGRESSION = '''from pathlib import Path
import runpy
import unittest
reward = runpy.run_path(str(Path(__file__).resolve().parents[1] / "src" / "reward.py"))["delivery_reward"]
class RewardRegression(unittest.TestCase):
    def test_delivery_reward(self):
        for coins in (0, 1, 5, 100):
            with self.subTest(coins=coins):
                self.assertEqual(reward(coins), coins)
if __name__ == "__main__":
    unittest.main()
'''
REVIEW = '''from pathlib import Path
import ast
path = Path(__file__).resolve().parents[1] / "src" / "reward.py"
tree = ast.parse(path.read_text())
expected = ast.parse("def delivery_reward(coins):\\n    return coins\\n")
assert ast.dump(tree) == ast.dump(expected), "Unexpected code or extra side effects"
print("REVIEW PASS: function returns the delivered coin count without extra operations")
'''


from types import SimpleNamespace
from ember_harness.recovery import step


def _show(state, label, result, detail):
    state.rows.append((label, result, detail))
    print(f'{label}: {result} ({detail})')

def _action(state, contract, tool, args, read=None, write=None):
    return {'agent': contract['agent'], 'contract_id': contract['id'], 'tool': tool, 'args': args, 'paths': {'read': [p.as_posix() for p in read or []], 'write': [p.as_posix() for p in write or []]}, 'spend': 0}

def _test(state, contract, script, action_id, read_source=None):
    reads = [read_source or state.source, script]
    if state.integration:
        reads.append(script.parent.parent / state.integration['asset_relative'])
    result = run_test(state.h, _action(state, contract, 'test.run', {'script': script.as_posix()}, read=reads))
    items = [{'kind': 'output_snippet', 'params': {'text': result['stdout'] + result['stderr']}}]
    if action_id == 'review':
        items.append({'kind': 'reviewer_note', 'params': {'reviewer': contract['agent'], 'role': 'automated_verifier', 'note': result['stdout']}})
    evidence = state.h.verify_evidence(contract['id'], action_id, items, decision_seq=result['decision_seq'])
    return result, evidence

def _bootstrap(state, *, recovery=None, with_rounds=False, with_intake=False, integrate=None):
    state.folder = Path(__file__).resolve().parents[1] / '.harness' / 'demos' / ('staged-fix-' + uuid.uuid4().hex[:10])
    state.repo = state.folder / 'sample'
    state.repro_repo, state.verification_repo = (state.folder / 'verify-before', state.folder / 'verify-fixed')
    for state.name in ('src', 'scripts', 'triage'):
        (state.repo / state.name).mkdir(parents=True, exist_ok=True)
    state.source, state.regression, state.review_script = (state.repo / 'src/reward.py', state.repo / 'scripts/test_reward.py', state.repo / 'scripts/review_reward.py')
    state.source.write_bytes(BROKEN.encode())
    state.regression.write_bytes(REGRESSION.encode())
    state.review_script.write_bytes(REVIEW.encode())
    state.snapshot = state.repo / 'triage/bug_snapshot.json'
    state.snapshot.write_bytes(canonical({'id': 'BUG-0001', 'severity': 'S2', 'title': 'Delivery rewards lose one coin', 'steps': ['Deliver five coins', 'Inspect reward'], 'expected': 5, 'actual': 4}))
    git(state.repo, 'init', '--initial-branch=main')
    for state.key, state.value in (('user.name', 'Ember demo fixture'), ('user.email', 'demo@example.invalid'), ('core.autocrlf', 'false'), ('commit.gpgsign', 'false'), ('core.hooksPath', str(state.folder / 'no-hooks'))):
        git(state.repo, 'config', '--local', state.key, state.value)
    state.h = Harness(state.repo / 'control')
    state.fix_id, state.verifier_id, state.scope_id = ('ct-fix-0001', 'ct-verifier-0001', 'ct-fix-scope-0001')
    state.intake_context = None
    if with_intake:
        from examples.intake_demo import setup as setup_intake, ingest
        state.intake_context = setup_intake(state.folder / 'intake-workspace', harness=state.h)
        state.finding = ingest(state.intake_context, 'initial')
        state.snapshot = Path(state.intake_context['intake'].snapshot(state.finding['id'], state.fix_id)['path'])
    state.branch = f'round/1/{state.fix_id}'
    state.now = datetime.now(timezone.utc)
    state.c = draft(state.scope_id, 'demo-planner', 'Fix the staged delivery-reward bug locally, verify regression and close S2.', role='scope')
    state.c['approval_mode'] = 'approve_all'
    state.c['limits'] = {'spend_usd': 0, 'max_calls': 30, 'time_window': {'not_before': state.now.isoformat(), 'not_after': (state.now + timedelta(hours=1)).isoformat()}}
    state.c['allowed_paths'] = {'read': [(state.repo / 'src').as_posix() + '/*.py', (state.repo / 'scripts').as_posix() + '/*.py', (state.repo / 'triage').as_posix() + '/*.json'], 'write': [(state.repo / 'src').as_posix() + '/*.py']}
    if with_intake:
        state.c['allowed_paths']['read'].append((state.h.root / 'triage/fix_contracts').as_posix() + '/*/*.json')
    if with_rounds:
        state.c['allowed_paths']['read'] += [(checkout / sub).as_posix() + '/*.py' for checkout in (state.repro_repo, state.verification_repo) for sub in ('src', 'scripts')]
    state.c['inputs'] = [{'name': name, 'path': path.as_posix(), 'sha256': sha256(path.read_bytes()).hexdigest()} for name, path in (('regression', state.regression), ('review_script', state.review_script), ('bug_snapshot', state.snapshot))]
    state.c['allowed_actions'] = [{'action_id': 'edit', 'tool': 'fs.write', 'class': 'write', 'args_constraints': {'path': {'equals': state.source.as_posix()}, 'content': {'equals': FIXED}}}, {'action_id': 'regression', 'tool': 'test.run', 'class': 'compute', 'args_constraints': {'script': {'equals': state.regression.as_posix()}}}, {'action_id': 'review', 'tool': 'test.run', 'class': 'compute', 'args_constraints': {'script': {'equals': state.review_script.as_posix()}}}, {'action_id': 'stage', 'tool': 'git.add', 'class': 'local_commit', 'args_constraints': {'branch': {'equals': state.branch}, 'path': {'equals': state.source.as_posix()}}, 'allow_no_evidence': True}, {'action_id': 'commit', 'tool': 'git.commit', 'class': 'local_commit', 'args_constraints': {'branch': {'equals': state.branch}, 'message': {'pattern': '^Fix BUG-0001[\\s\\S]+$'}}}, {'action_id': 'close', 'tool': 'triage.close', 'class': 'bug_close', 'args_constraints': {'bug_id': {'equals': 'BUG-0001'}, 'severity': {'equals': 'S2'}}, 'allow_no_evidence': True}]
    state.c['required_evidence'] = {'edit': [{'kind': 'file_hash', 'params': {'path': state.source.as_posix(), 'sha256': sha256(FIXED.encode()).hexdigest()}}], 'regression': [{'kind': 'output_snippet', 'params': {'pattern': '\\bOK\\b'}}], 'review': [{'kind': 'output_snippet', 'params': {'pattern': 'REVIEW PASS'}}, {'kind': 'reviewer_note', 'params': {'reviewer': 'demo-verifier', 'role': 'automated_verifier'}}], 'commit': [{'kind': 'output_snippet', 'params': {'pattern': '^[0-9a-f]{40}$'}}]}
    if with_rounds:
        next((a for a in state.c['allowed_actions'] if a['action_id'] == 'review'))['args_constraints']['script'] = {'equals': (state.verification_repo / 'scripts/review_reward.py').as_posix()}
        state.c['allowed_actions'] += [{'action_id': name, 'tool': 'test.run', 'class': 'compute', 'args_constraints': {'script': {'equals': (checkout / 'scripts/test_reward.py').as_posix()}}} for name, checkout in (('reproduce', state.repro_repo), ('verify', state.verification_repo))]
        state.c['required_evidence'].update(reproduce=[{'kind': 'output_snippet', 'params': {'pattern': 'AssertionError'}}], verify=[{'kind': 'output_snippet', 'params': {'pattern': '\\bOK\\b'}}])


def _integration(state, *, recovery=None, with_rounds=False, with_intake=False, integrate=None):
    state.integration = integrate(state.c, state.h, state.repo, state.folder) if integrate else None


def _fix_contracts(state, *, recovery=None, with_rounds=False, with_intake=False, integrate=None):
    if state.integration:
        state.scope_id = state.integration['scope']['id']
        state.c['art_direction'] = deepcopy(state.integration['scope']['art_direction'])
        state.c['limits']['time_window'] = deepcopy(state.integration['scope']['limits']['time_window'])
        state.snapshot = Path(state.integration['snapshot'])
        state.c['inputs'] = [i for i in state.c['inputs'] if i['name'] != 'bug_snapshot']
        state.c['inputs'].append({'name': 'bug_snapshot', 'path': state.snapshot.as_posix(), 'sha256': sha256(state.snapshot.read_bytes()).hexdigest()})
        state.c['inputs'].append({'name': 'accepted_asset', 'path': (state.repo / state.integration['asset_relative']).as_posix(), 'sha256': state.integration['asset_sha256']})
        state.intake_context = state.integration['intake_context']
    state.fix, state.verifier = (deepcopy(state.c), deepcopy(state.c))
    state.fix.update(id=state.fix_id, agent='demo-fix-author', approval_mode='each')
    state.fix['extensions']['orchestration']['role'] = 'coding'
    state.fix['extensions']['triage'] = {'bug_id': 'BUG-0001', 'author': 'demo-fix-author', 'reviewer': 'demo-verifier'}
    state.fix['allowed_actions'] = [a for a in state.fix['allowed_actions'] if a['action_id'] in ('edit', 'regression', 'stage', 'commit', 'agent')]
    state.fix['required_evidence'] = {k: v for k, v in state.fix['required_evidence'].items() if k in ('edit', 'regression', 'commit')}
    state.verifier.update(id=state.verifier_id, agent='demo-verifier')
    state.verifier['extensions']['orchestration']['role'] = 'verifier'
    state.verifier['allowed_paths']['write'] = []
    state.verifier_ids = ('reproduce', 'review', 'verify', 'close') if with_rounds else ('regression', 'review', 'close')
    state.verifier['allowed_actions'] = [a for a in state.verifier['allowed_actions'] if a['action_id'] in state.verifier_ids]
    state.verifier['required_evidence'] = {key: value for key, value in state.verifier['required_evidence'].items() if key in state.verifier_ids}
    if with_rounds:
        state.verifier['extensions']['triage'] = {'verification_repo': state.verification_repo.as_posix(), 'repro_repo': state.repro_repo.as_posix()}
        state.verifier['inputs'] = [{'name': name, 'path': path.as_posix(), 'sha256': sha256(original.read_bytes()).hexdigest()} for name, path, original in (('regression', state.repro_repo / 'scripts/test_reward.py', state.regression), ('fixed_regression', state.verification_repo / 'scripts/test_reward.py', state.regression), ('review_script', state.verification_repo / 'scripts/review_reward.py', state.review_script), ('bug_snapshot', state.snapshot, state.snapshot))]
        if state.integration:
            state.verifier['inputs'] += [{'name': name, 'path': (checkout / state.integration['asset_relative']).as_posix(), 'sha256': state.integration['asset_sha256']} for name, checkout in (('baseline_asset', state.repro_repo), ('fixed_asset', state.verification_repo))]
    state.quote = 'Lets do it'
    state.approvals = ((state.fix, state.scope_id), (state.verifier, state.scope_id)) if state.integration else ((state.c, None), (state.fix, state.scope_id), (state.verifier, state.scope_id))
    if state.integration:
        state.quote = 'SIMULATED contract approval for the isolated integrated product demo only.'


def _review_fix_contracts(state, *, recovery=None, with_rounds=False, with_intake=False, integrate=None):
    if state.integration:
        state.integration['owner'].contracts(state.h, list(state.approvals))


def _fix_inputs(state, *, recovery=None, with_rounds=False, with_intake=False, integrate=None):
    for state.contract, state.parent in state.approvals:
        if not state.integration:
            state.h.save_draft(state.contract)
            state.h.approve(state.contract['id'], 1, approver='johnathan', quote=state.quote, expected_hash=content_hash(state.contract), parent_id=state.parent)
        if not with_rounds or state.contract['id'] != state.verifier_id:
            assert state.h.verify_inputs(state.contract['id'])


def _amend_fix(state, *, recovery=None, with_rounds=False, with_intake=False, integrate=None):
    if state.integration:
        from examples.product_demo import prepare_fix
        state.fix = prepare_fix(state.h, state.fix, state.integration['owner'], recovery=recovery)


def _baseline(state, *, recovery=None, with_rounds=False, with_intake=False, integrate=None):
    git(state.repo, 'add', '--', 'src', 'scripts', 'triage', 'control', *(['scope-output'] if state.integration else []))
    git(state.repo, 'commit', '-m', 'Bootstrap isolated staged bug and approved demo contracts')
    state.pre_build = git(state.repo, 'rev-parse', 'HEAD').decode().strip()
    git(state.repo, 'switch', '-c', state.branch)
    state.rounds, state.task = (None, None)
    if with_rounds:
        from ember_harness.rounds import Rounds
        git(state.repo, 'worktree', 'add', '--detach', str(state.repro_repo), state.pre_build)
        git(state.repo, 'worktree', 'add', '--detach', str(state.verification_repo), state.pre_build)
        assert state.h.verify_inputs(state.verifier_id)
        state.rounds = Rounds(state.h)
        state.task = {'bug_id': 'BUG-0001', 'severity': 'S2', 'fix_contract_id': state.fix_id, 'fix_version': state.fix['version'], 'verifier_contract_id': state.verifier_id, 'verifier_version': 1, 'source_path': state.source.as_posix(), 'repo': state.repo.as_posix(), 'base': state.pre_build, 'branch': state.branch, 'repro_repo': state.repro_repo.as_posix(), 'verification_repo': state.verification_repo.as_posix()}
        state.rounds.start([state.task])
    state.rows = []


def _reproduce(state, *, recovery=None, with_rounds=False, with_intake=False, integrate=None):
    if with_rounds:
        _show(state, 'C0 plan', 'PLANNED', 'approved task versions and distinct read-only verifier')
        try:
            state.rounds.start([state.task])
            raise AssertionError('overlapping rounds must be refused')
        except ValueError as error:
            assert 'still open' in str(error)
            _show(state, 'Start a second round while round 1 is open', 'REFUSED', 'previous round is still open')
        state.pre, state._ = _test(state, state.verifier, state.repro_repo / 'scripts/test_reward.py', 'reproduce', state.repro_repo / 'src/reward.py')
    else:
        state.pre, state._ = _test(state, state.fix, state.regression, 'regression')
    assert state.pre['returncode'] == 1 and 'AssertionError' in state.pre['stderr']
    _show(state, 'Reproduce BUG-0001 on pre-fix commit', 'FAIL AS EXPECTED', 'actual regression assertions fail')


def _proposal(state, *, recovery=None, with_rounds=False, with_intake=False, integrate=None):
    state.edit = _action(state, state.fix, 'fs.write', {'path': state.source.as_posix(), 'content': FIXED}, write=[state.source])
    if state.integration and state.integration.get('agent'):
        state.edit = state.integration['agent'].propose(state.h, state.fix, state.source, state.pre)
    state.denied = deepcopy(state.edit)
    state.denied['args']['path'] = (state.repo / 'scripts/unapproved.py').as_posix()
    assert state.h.check(state.denied)['decision'] == 'deny'
    _show(state, 'Attempt edit outside fix contract', 'DENIED', 'no unauthorized file written')


def _edit(state, *, recovery=None, with_rounds=False, with_intake=False, integrate=None):
    state.permitted = state.h.check(state.edit)
    assert state.permitted['decision'] == 'allow'
    state.source.write_bytes(state.edit['args']['content'].encode('utf-8'))
    assert state.h.verify_evidence(state.fix_id, 'edit', [{'kind': 'file_hash', 'params': {'path': state.source.as_posix(), 'sha256': sha256(FIXED.encode()).hexdigest()}}], decision_seq=state.permitted['audit_seq'])['status'] == 'complete'


def _regression(state, *, recovery=None, with_rounds=False, with_intake=False, integrate=None):
    state.post, state.verified = _test(state, state.fix, state.regression, 'regression')
    assert state.post['returncode'] == 0 and state.verified['status'] == 'complete'
    _show(state, 'Apply approved fix and rerun regression', 'PASS', 'four coin-count cases pass')


def _stage_commit(state, *, recovery=None, with_rounds=False, with_intake=False, integrate=None):
    state.approved_fix = json.loads(state.h._path(state.fix_id, state.fix['version']).read_text())
    state.message = f'Fix BUG-0001 delivery reward off-by-one\n\nAuthor: demo-fix-author\nReviewer: demo-verifier\n\nRound: 1\nContract-Id: {state.fix_id}\nContract-Version: {state.fix['version']}\nContract-Hash: {state.approved_fix['content_hash']}\nSubsystem: triage\n'
    state.staged = state.h.check(_action(state, state.fix, 'git.add', {'branch': state.branch, 'path': state.source.as_posix()}, write=[state.source]))
    assert state.staged['decision'] == 'allow'
    git(state.repo, 'add', '--', 'src/reward.py')
    state.lock = contract_lock(state.h.root, repo=state.repo, base=state.pre_build, staged_message=state.message)
    assert state.lock['ok'], state.lock
    _show(state, 'contract-lock before local commit', 'PASS', 'approved history, staged path and all five trailers verified')


def _commit(state, *, recovery=None, with_rounds=False, with_intake=False, integrate=None):
    state.commit_action = _action(state, state.fix, 'git.commit', {'branch': state.branch, 'message': state.message}, write=[state.source])
    state.decision = state.h.check(state.commit_action)
    assert state.decision['decision'] == 'allow'
    state.message_file = state.folder / 'commit-message.txt'
    state.message_file.write_text(state.message, encoding='utf-8')
    git(state.repo, 'commit', '--file', str(state.message_file))
    state.build = git(state.repo, 'rev-parse', 'HEAD').decode().strip()
    assert state.h.verify_evidence(state.fix_id, 'commit', [{'kind': 'output_snippet', 'params': {'text': state.build}}], decision_seq=state.decision['audit_seq'])['status'] == 'complete'
    _show(state, 'Create local fix commit', 'COMMITTED', state.build[:12])


def _verification(state, *, recovery=None, with_rounds=False, with_intake=False, integrate=None):
    if with_rounds:
        git(state.verification_repo, 'checkout', '--detach', state.build)
        assert state.h.verify_inputs(state.verifier_id)
        state.review, state.reviewed = _test(state, state.verifier, state.verification_repo / 'scripts/review_reward.py', 'review', state.verification_repo / 'src/reward.py')
        state.rounds.reviewed(1, 'BUG-0001', build=state.build, review_seq=state.review['execution_seq'])
        _show(state, 'C1 reviewed commit', 'RECORDED', 'real commit and captured review on clean fixed checkout')
        state.qa, state.qa_evidence = _test(state, state.verifier, state.verification_repo / 'scripts/test_reward.py', 'verify', state.verification_repo / 'src/reward.py')
        state.rounds.verified(1, 'BUG-0001', repro_seq=state.pre['execution_seq'], verify_seq=state.qa['execution_seq'])
        _show(state, 'C2 verified', 'AWAITING APPROVAL', 'same regression fails on clean baseline and passes on clean fixed checkout')
        try:
            state.rounds.close(1)
            raise AssertionError('round closure needs bug closure')
        except ValueError as error:
            assert 'closure required' in str(error)
            _show(state, 'C3 before bug closure', 'REFUSED', 'verified bug closure required')
    else:
        state.review, state.reviewed = _test(state, state.verifier, state.review_script, 'review')
        state.qa, state.qa_evidence = _test(state, state.verifier, state.regression, 'regression')
    assert state.review['returncode'] == 0 and state.reviewed['status'] == 'complete' and (state.qa_evidence['status'] == 'complete')
    _show(state, 'Read-only verifier review and regression', 'PASS', 'automated AST review; verifier identity differs from author')


def _closure(state, *, recovery=None, with_rounds=False, with_intake=False, integrate=None):
    state.index = state.h.root / 'triage/regression/index.json'
    state.index.parent.mkdir(parents=True)
    state.index.write_bytes(canonical([{'bug_id': 'BUG-0001', 'test_path': state.regression.as_posix(), 'build_introduced': state.build, 'command': 'test.run'}]))
    state.closure = close_bug(state.h, bug_id='BUG-0001', severity='S2', fix_id=state.fix_id, verifier_id=state.verifier_id, source_path=state.source.as_posix(), pre_seq=state.pre['execution_seq'], post_seq=state.post['execution_seq'], review_seq=state.review['execution_seq'], verify_seq=state.qa['execution_seq'], build=state.build, pre_build=state.pre_build, repo=state.repo)
    assert state.closure['status'] == 'closed', state.closure
    _show(state, 'Closure gate', 'CLOSED', f'S2; evidence and named builds verified, audit #{state.closure['status_basis']}')


def _round_report(state, *, recovery=None, with_rounds=False, with_intake=False, integrate=None):
    if with_rounds:
        state.rounds.close(1, next_round=[] if state.integration else ['BUG-0002'])
        from ember_harness.reporting import write_round_report
        state.report_result = write_round_report(state.h, 1)
        _show(state, 'C3 round close', 'COMPLETE', 'audit-derived report; push not requested; ' + ('no bugs queued' if state.integration else 'BUG-0002 queued'))


def _report(state, *, recovery=None, with_rounds=False, with_intake=False, integrate=None):
    state.contract_path = state.h._path(state.fix_id, state.fix['version'])
    state.original = state.contract_path.read_bytes()
    state.tampered = json.loads(state.original)
    state.tampered['goal'] = 'Unapproved broader goal'
    state.contract_path.write_bytes(canonical(state.tampered))
    state.tamper_result = contract_lock(state.h.root, repo=state.repo, base=state.pre_build)
    assert not state.tamper_result['ok']
    state.contract_path.write_bytes(state.original)
    _show(state, 'Tamper with approved contract', 'REJECTED', 'contract-lock detects the edited version')
    state.final_lock, state.audit = (contract_lock(state.h.root, repo=state.repo, base=state.pre_build), state.h.audit_verify())
    assert state.final_lock['ok'], state.final_lock
    _show(state, 'Restore bytes and verify final history', 'PASS', f'{state.audit['entries']} audit entries; no remote configured')
    (state.folder / 'results.json').write_bytes(canonical({'closure': state.closure, 'contract_lock': state.final_lock, 'audit': state.audit, 'pre_build': state.pre_build, 'fix_build': state.build, 'rows': state.rows}))
    state.lines = ['# Staged bug-fix workflow', '', 'An isolated local demo with fixture approvals authorized by your request. The regression and structural review scripts actually ran, and the fix is a real local Git commit. The reviewer is a deterministic read-only checker under a separate fixture identity; no human or independent AI peer review is claimed.', '', '**BUG-0001 (S2):** delivering five coins incorrectly rewards four. The approved fix returns the delivered coin count.', '', '| Stage | Result | Evidence |', '|---|---|---|']
    state.lines += [f'| {label} | **{result}** | {detail} |' for label, result, detail in state.rows]
    state.lines += ['', f'Pre-fix commit: `{state.pre_build}`', '', f'Verified fix commit: `{state.build}`', '', f'[Fixed source](<{state.source.as_posix()}>) · [Regression test](<{state.regression.as_posix()}>) · [Structural review](<{state.review_script.as_posix()}>)', '', f'[Results and audit head](<{(state.folder / 'results.json').as_posix()}>) · [Raw audit log](<{state.h.audit_path.as_posix()}>)', '', 'No push, publish, paid call, or engine edit occurs. The sample repository remains local under this demo directory.']
    state.report = state.folder / 'DEMO.md'
    state.report.write_text('\n'.join(state.lines) + '\n', encoding='utf-8')
    print(f'Report: {state.report}')
    state.result = {'folder': state.folder, 'repo': state.repo, 'harness': state.h, 'fix': state.fix, 'verifier': state.verifier, 'source': state.source, 'pre': state.pre, 'post': state.post, 'review': state.review, 'qa': state.qa, 'build': state.build, 'pre_build': state.pre_build, 'closure': state.closure, 'intake_context': state.intake_context, 'rounds': state.rounds, 'task': state.task, 'round_report': state.report_result if with_rounds else None, 'integration': state.integration}

def main(*, with_rounds=False, with_intake=False, integrate=None, recovery=None):
    state = SimpleNamespace()
    state = step(recovery, 'fix.bootstrap', state, _bootstrap, retry=False, with_rounds=with_rounds, with_intake=with_intake, integrate=integrate)
    state = step(recovery, 'fix.integration', state, _integration, retry=True, with_rounds=with_rounds, with_intake=with_intake, integrate=integrate)
    state = step(recovery, 'fix.fix_contracts', state, _fix_contracts, retry=False, with_rounds=with_rounds, with_intake=with_intake, integrate=integrate)
    state = step(recovery, 'fix.review_fix_contracts', state, _review_fix_contracts, retry=True, with_rounds=with_rounds, with_intake=with_intake, integrate=integrate)
    state = step(recovery, 'fix.fix_inputs', state, _fix_inputs, retry=False, with_rounds=with_rounds, with_intake=with_intake, integrate=integrate)
    state = step(recovery, 'fix.amend_fix', state, _amend_fix, retry=True, with_rounds=with_rounds, with_intake=with_intake, integrate=integrate)
    state = step(recovery, 'fix.baseline', state, _baseline, retry=False, with_rounds=with_rounds, with_intake=with_intake, integrate=integrate)
    state = step(recovery, 'fix.reproduce', state, _reproduce, retry=False, with_rounds=with_rounds, with_intake=with_intake, integrate=integrate)
    state = step(recovery, 'fix.proposal', state, _proposal, retry=False, with_rounds=with_rounds, with_intake=with_intake, integrate=integrate)
    state = step(recovery, 'fix.edit', state, _edit, retry=False, with_rounds=with_rounds, with_intake=with_intake, integrate=integrate)
    state = step(recovery, 'fix.regression', state, _regression, retry=False, with_rounds=with_rounds, with_intake=with_intake, integrate=integrate)
    state = step(recovery, 'fix.stage_commit', state, _stage_commit, retry=False, with_rounds=with_rounds, with_intake=with_intake, integrate=integrate)
    state = step(recovery, 'fix.commit', state, _commit, retry=False, with_rounds=with_rounds, with_intake=with_intake, integrate=integrate)
    state = step(recovery, 'fix.verification', state, _verification, retry=False, with_rounds=with_rounds, with_intake=with_intake, integrate=integrate)
    state = step(recovery, 'fix.closure', state, _closure, retry=False, with_rounds=with_rounds, with_intake=with_intake, integrate=integrate)
    state = step(recovery, 'fix.round_report', state, _round_report, retry=False, with_rounds=with_rounds, with_intake=with_intake, integrate=integrate)
    state = step(recovery, 'fix.report', state, _report, retry=False, with_rounds=with_rounds, with_intake=with_intake, integrate=integrate)
    return state.result


if __name__ == '__main__':
    main()
