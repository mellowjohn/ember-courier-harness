"""One scope and audit: accepted asset -> intake -> amended fix -> clean verification."""
from types import SimpleNamespace
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ember_harness.recovery import step
from ember_harness import Harness, canonical, content_hash
from ember_harness.assets import Assets
from ember_harness.attempts import Attempts
from ember_harness.contract_lock import git, verify as contract_lock
from ember_harness.core import digest
from ember_harness.scope import propose, review as review_scope
from ember_harness.staged_fix import execution
from ember_harness.rounds import Rounds
from examples.asset_demo import fixture_images
from examples.intake_demo import setup as intake_setup, ingest as intake_finding
from examples.staged_fix_demo import main as staged_fix

QUOTE = 'SIMULATED owner approval for the isolated product demonstration only.'


def approve(h, c, parent=None):
    h.save_draft(c)
    return h.approve(c['id'], c['version'], approver='johnathan', quote=QUOTE,
                     expected_hash=content_hash(c), parent_id=parent)['contract']


class FixtureOwner:
    mode = 'fixture'

    def contract(self, h, c, parent=None):
        return approve(h, c, parent)

    def contracts(self, h, items):
        return [self.contract(h, c, parent) for c, parent in items]

    def action(self, h, action):
        return h.approve_action(action, approver='johnathan', quote=QUOTE)

    def select(self, h, assets, c, review):
        choice = review['review']['candidates'][0]['slug']
        pending = assets.select(c['id'], review['review_ref'], choice)
        self.action(h, pending['approval_action'])
        assert assets.select(c['id'], review['review_ref'], choice)['status'] == 'selected'
        return choice


def _asset_setup(state, *, recovery=None):
    state.ctx = intake_setup(state.folder / 'intake-workspace', harness=state.h, approve=False)
    if state.local_agent:
        state.code['allowed_actions'].append(state.local_agent.capability((state.repo / 'src/reward.py').as_posix()))
    state.candidates = fixture_images(state.repo / 'scope-output/candidates')
    state.selected = state.candidates[0]
    state.dest = state.repo / 'scope-output/assets/player.png'
    state.dest.parent.mkdir()
    state.manifest = state.repo / 'scope-output/concepts.json'
    state.manifest.write_bytes(canonical(dict(topic='Ember Courier player', candidates=state.candidates)))
    state.asset_relative = state.dest.relative_to(state.repo).as_posix()
    state.regression = state.repo / 'scripts/test_reward.py'
    state.text = state.regression.read_text()
    state.text = state.text.replace('import runpy', 'import runpy\nfrom hashlib import sha256')
    state.text = state.text.replace('        for coins in', f'        self.assertEqual(sha256((Path(__file__).resolve().parents[1] / {state.asset_relative!r}).read_bytes()).hexdigest(), {state.selected['sha256']!r})\n        for coins in')
    state.regression.write_text(state.text, encoding='utf-8')
    next((i for i in state.code['inputs'] if i['name'] == 'regression'))['sha256'] = sha256(state.regression.read_bytes()).hexdigest()
    state.code['allowed_paths']['read'].append((state.h.root / 'triage/fix_contracts').as_posix() + '/*/*.json')
    for state.checkout in (state.repo, state.folder / 'verify-before', state.folder / 'verify-fixed'):
        state.code['allowed_paths']['read'].append(state.checkout.as_posix() + '/scope-output/**')
    state.scope = propose('ct-product-scope-0001', 'product-planner', 'Ember Courier: choose and accept one original ember asset, then fix and verify delivery rewards locally.', state.repo, asset_workflow=True)
    state.scope['approval_mode'] = 'approve_all'
    state.scope['limits']['max_calls'] = 100
    for state.mode in ('read', 'write'):
        state.scope['allowed_paths'][state.mode] = list(dict.fromkeys(state.scope['allowed_paths'][state.mode] + state.code['allowed_paths'][state.mode] + state.ctx['scope']['allowed_paths'][state.mode]))
    state.scope['allowed_actions'] += deepcopy(state.code['allowed_actions'])
    state.triage_actions = deepcopy(state.ctx['scope']['allowed_actions'])
    for state.a in state.triage_actions:
        state.a['action_id'] = 'finding_' + state.a['action_id']
    state.scope['allowed_actions'] += state.triage_actions
    state.scope['required_evidence'].update(deepcopy(state.code['required_evidence']))
    state.reviewed = review_scope(state.scope)


def _scope_review(state, *, recovery=None):
    state.scope = state.owner.contract(state.h, state.scope)


def _asset_contract(state, *, recovery=None):
    state.assets = Assets(state.h)
    state.child = state.owner.contract(state.h, state.assets.proposal(state.scope['id'], state.manifest, 'ct-product-assets-0001', 'asset-worker'), state.scope['id'])


def _concept_review(state, *, recovery=None):
    assert state.h.verify_inputs(state.child['id'])
    state.reviewed_assets = state.assets.review(state.child['id'])
    state.ref = state.reviewed_assets['review_ref']


def _concept_choice(state, *, recovery=None):
    state.choice = state.owner.select(state.h, state.assets, state.child, state.reviewed_assets)


def _ingest(state, *, recovery=None):
    state.selected = next((v for v in state.candidates if v['slug'] == state.choice))
    if state.choice != state.candidates[0]['slug']:
        state.text = state.regression.read_text(encoding='utf-8').replace(state.candidates[0]['sha256'], state.selected['sha256'])
        state.regression.write_text(state.text, encoding='utf-8')
        next((i for i in state.code['inputs'] if i['name'] == 'regression'))['sha256'] = sha256(state.regression.read_bytes()).hexdigest()
    assert state.assets.ingest(state.child['id'], state.ref, state.dest)['status'] == 'ingested'
    state.pending = state.assets.accept(state.child['id'], state.ref, state.dest)
    assert state.pending['decision'] == 'needs_approval'


def _accept_review(state, *, recovery=None):
    state.owner.action(state.h, state.pending['approval_action'])


def _accept(state, *, recovery=None):
    assert state.assets.accept(state.child['id'], state.ref, state.dest)['status'] == 'accepted'
    for state.c in (state.ctx['contract'], state.ctx['reviewer']):
        state.c['limits']['time_window'] = deepcopy(state.scope['limits']['time_window'])
        state.c['art_direction'] = deepcopy(state.scope['art_direction'])


def _intake_review(state, *, recovery=None):
    state.owner.contracts(state.h, [(c, state.scope['id']) for c in (state.ctx['contract'], state.ctx['reviewer'])])


def _intake(state, *, recovery=None):
    state.ctx['scope'] = state.scope
    state.bug = intake_finding(state.ctx, 'product-finding')
    assert state.bug['state'] == 'triaged' and state.bug['severity'] == 'S2'
    state.snapshot = state.ctx['intake'].snapshot(state.bug['id'], 'ct-fix-0001')
    state.result = dict(scope=state.scope, reviewed_hash=state.reviewed['reviewed_hash'], snapshot=state.snapshot['path'], intake_context=state.ctx, asset_contract=state.child['id'], review_ref=state.ref, asset_relative=state.asset_relative, asset_sha256=state.selected['sha256'], agent=state.local_agent, owner=state.owner)

def integrate(code, h, repo, folder, local_agent=None, owner=None, recovery=None):
    state = SimpleNamespace(code=code, h=h, repo=repo, folder=folder, local_agent=local_agent, owner=owner)
    state = step(recovery, 'product.asset_setup', state, _asset_setup, retry=False)
    state = step(recovery, 'product.scope_review', state, _scope_review, retry=True)
    state = step(recovery, 'product.asset_contract', state, _asset_contract, retry=True)
    state = step(recovery, 'product.concept_review', state, _concept_review, retry=False)
    state = step(recovery, 'product.concept_choice', state, _concept_choice, retry=True)
    state = step(recovery, 'product.ingest', state, _ingest, retry=False)
    state = step(recovery, 'product.accept_review', state, _accept_review, retry=True)
    state = step(recovery, 'product.accept', state, _accept, retry=False)
    state = step(recovery, 'product.intake_review', state, _intake_review, retry=True)
    state = step(recovery, 'product.intake', state, _intake, retry=False)
    if code is not state.code:
        code.clear()
        code.update(state.code)
    return state.result



def _amendment(state, *, recovery=None):
    from ember_harness.amendments import amend
    amend(state.h, state.fix['id'], dict(reason='Tighten the local fix call budget before execution', round=1, source=dict(kind='bug', id='BUG-0001'), changes=[dict(op='replace', pointer='/limits/max_calls', value=20)]), actor='product-planner')
    state.c = json.loads(state.h._path(state.fix['id'], 2).read_bytes())


def _amendment_review(state, *, recovery=None):
    state.owner.contract(state.h, state.c)


def _amendment_inputs(state, *, recovery=None):
    assert state.h.verify_inputs(state.c['id'])
    state.old = dict(agent=state.fix['agent'], contract_id=state.fix['id'], contract_version=1, tool='fs.write', args={k: rule['equals'] for k, rule in next((a for a in state.fix['allowed_actions'] if a['tool'] == 'fs.write'))['args_constraints'].items()}, paths=dict(read=[], write=[]), spend=0)
    assert state.h.check(state.old)['decision'] == 'deny'
    assert Attempts(state.h).status('BUG-0001')['attempts_started'] == 1
    state.result = state.c

def prepare_fix(h, fix, owner, recovery=None):
    state = SimpleNamespace(h=h, fix=fix, owner=owner)
    state = step(recovery, 'product.amendment', state, _amendment, retry=False)
    state = step(recovery, 'product.amendment_review', state, _amendment_review, retry=True)
    state = step(recovery, 'product.amendment_inputs', state, _amendment_inputs, retry=False)
    return state.result



def verify_product(manifest):
    """Refresh current bytes and cross-workflow provenance, not just stage exit codes."""
    h = Harness(manifest['store'])
    entries = h._entries()
    if not any(e['kind'] == 'product_demo' and e['manifest_hash'] == digest(manifest) for e in entries):
        raise ValueError('product manifest lacks its audited binding')
    approvals = [e for e in entries if e['kind'] == 'approval' and e.get('scope') == 'contract']
    roots = [e for e in approvals if e.get('role') == 'scope']
    if len(roots) != 1 or roots[0]['contract_id'] != manifest['scope_id'] or roots[0]['reviewed_hash'] != manifest['reviewed_hash']:
        raise ValueError('one shared reviewed root scope required')
    if any(e.get('parent_id') != manifest['scope_id'] for e in approvals if e.get('role') != 'scope'):
        raise ValueError('every workflow must belong to the shared scope')
    if manifest.get('owner_mode') == 'owner_review':
        from ember_harness.owner_review import validate_history
        validate_history(h, entries)
        covered = {seq for e in entries if e['kind'] == 'owner_decision' and e['choice'] != 'decline' for seq in e['approval_seqs']}
        explicit = [e for e in entries if e['kind'] == 'approval' and e.get('scope') in ('contract', 'action')]
        if any(e['seq'] not in covered for e in explicit):
            raise ValueError('product contains approvals without owner review receipts')
    asset = manifest['asset']
    state = Assets(h).status(asset['contract_id'], asset['review_ref'], asset['path'])
    if state['status'] != 'accepted' or state['sha256'] != asset['sha256']:
        raise ValueError('current owner-accepted asset required')
    for seq in manifest['executions']:
        _, captured = execution(h, seq)
        path = (Path(captured['script']).parent.parent / asset['relative']).as_posix()
        if captured['inputs'].get(path) != asset['sha256']:
            raise ValueError('every regression and review must capture the accepted asset')
        if any(sha256(Path(p).read_bytes()).hexdigest() != expected for p, expected in captured['inputs'].items()):
            raise ValueError('captured source, script or asset changed after verification')
    accepted = next(e for e in entries if e['kind'] == 'asset_acceptance' and e['review_ref'] == asset['review_ref'])
    snapshot = next(e for e in entries if e['kind'] == 'bug_snapshot' and e['fix_contract_id'] == manifest['fix_id'])
    closure = entries[manifest['closure_seq'] - 1]
    round_state = Rounds(h).status(1)
    task = round_state['tasks'][0]
    for key, build in (('repro_repo', manifest['pre_build']), ('verification_repo', manifest['build'])):
        if git(task[key], 'rev-parse', 'HEAD').decode().strip() != build or git(task[key], 'status', '--porcelain'):
            raise ValueError('verification checkouts must remain clean on their named builds')
    attempt = Attempts(h).status('BUG-0001')
    if (not accepted['seq'] < snapshot['seq'] < manifest['executions'][0] < closure['seq'] < round_state['checkpoints']['C3'] or
        closure.get('status') != 'closed' or closure.get('build') != manifest['build'] or
        closure.get('fix_contract_id') != manifest['fix_id'] or closure.get('fix_version') != 2 or
        closure.get('execution_seqs') != manifest['executions'] or
        attempt['status'] != 'closed' or attempt['attempts_started'] != 1 or round_state['status'] != 'complete'):
        raise ValueError('asset, bug, amended fix and round completion are not linked')
    from ember_harness.intake import Intake
    if Intake(h, manifest['intake_root']).get('BUG-0001')['state'] != 'closed':
        raise ValueError('intake bug is not closed')
    repo = Path(manifest['repo'])
    if (git(repo, 'rev-parse', 'HEAD').decode().strip() != manifest['build'] or
        sha256((repo / 'src/reward.py').read_bytes()).hexdigest() != sha256(git(repo, 'show', manifest['build'] + ':src/reward.py')).hexdigest()):
        raise ValueError('current source differs from verified build')
    for build in (manifest['pre_build'], manifest['build']):
        if sha256(git(repo, 'show', build + ':' + asset['relative'])).hexdigest() != asset['sha256']:
            raise ValueError('accepted asset missing from a named build')
    lock = contract_lock(h.root, repo=repo, base=manifest['pre_build'])
    if not lock['ok']:
        raise ValueError('product contract-lock failed: ' + '; '.join(lock['errors']))
    agent_events = [e for e in entries if e['kind'] == 'agent_proposal' and e.get('contract_id') == manifest['fix_id']]
    agent_capture = manifest.get('agent_capture')
    if agent_capture:
        if len(agent_events) != 1 or agent_events[0]['capture_ref'] != agent_capture or agent_events[0]['status'] != 'proposed':
            raise ValueError('real agent proposal capture required')
        payload = json.loads((h.root / 'agent-captures' / (agent_capture + '.json')).read_bytes())
        if payload['pre_execution_seq'] != manifest['executions'][0]:
            raise ValueError('agent did not receive this product regression failure')
        writes = [e for e in entries if e['kind'] == 'decision' and e.get('decision') == 'allow' and
            e.get('contract_id') == manifest['fix_id'] and e['action']['tool'] == 'fs.write' and
            agent_events[0]['seq'] < e['seq'] < manifest['executions'][1]]
        if not any(e['action']['args'] == payload['proposal']['args'] for e in writes):
            raise ValueError('actual gated write differs from agent proposal')
    elif agent_events:
        raise ValueError('product manifest omitted its agent provenance')
    audit = h.audit_verify()
    return dict(passed=True, asset_status=state['status'], bug_status=attempt['status'],
                round_status=round_state['status'], attempts=attempt['attempts_started'],
                audit_head=audit['head'], audit_entries=audit['entries'], agent='ollama_local' if agent_capture else 'deterministic_fixture',
                owner_mode=manifest.get('owner_mode', 'fixture'))


def _workflow(state, *, recovery=None):
    setup = lambda code, h, repo, folder: integrate(code, h, repo, folder, state.local_agent, state.owner, recovery=recovery)
    state.d = staged_fix(with_rounds=True, integrate=setup, recovery=recovery)


def _manifest(state, *, recovery=None):
    state.h, state.linked = (state.d['harness'], state.d['integration'])
    state.manifest = dict(store=state.h.root.as_posix(), repo=state.d['repo'].as_posix(), scope_id=state.linked['scope']['id'], reviewed_hash=state.linked['reviewed_hash'], fix_id=state.d['fix']['id'], intake_root=state.linked['intake_context']['data'].as_posix(), build=state.d['build'], pre_build=state.d['pre_build'], closure_seq=state.d['closure']['status_basis'], executions=[state.d[name]['execution_seq'] for name in ('pre', 'post', 'review', 'qa')], owner_mode=state.owner.mode, asset=dict(contract_id=state.linked['asset_contract'], review_ref=state.linked['review_ref'], path=(state.d['repo'] / state.linked['asset_relative']).as_posix(), relative=state.linked['asset_relative'], sha256=state.linked['asset_sha256']))
    if state.local_agent:
        state.manifest['agent_capture'] = next((e['capture_ref'] for e in state.h._entries() if e['kind'] == 'agent_proposal'))
    with state.h._lock():
        state.h._append('product_demo', manifest_hash=digest(state.manifest))
    state.path = state.d['folder'] / 'product.json'
    state.path.write_bytes(canonical(state.manifest))


def _product_report(state, *, recovery=None):
    state.result = verify_product(state.manifest)
    state.report = state.d['folder'] / 'PRODUCT_DEMO.md'
    state.lines = ['# Ember Courier: integrated product demonstration', '', '**PASS** — one approved scope and audit chain links every stage.', '', 'The intake finding is a fixture. Tests and local Git commits are real. Review is a separate deterministic checker. This is a harness demonstration, not a playable game or engine import.', '', 'Owner decisions: ' + ('explicit responses through the trusted local review host; not identity authentication.' if state.owner.mode == 'owner_review' else 'SIMULATED fixtures for unattended tests.'), '', 'Fix author: ' + ('real local Ollama inference; cloud disabled; $0 model/API charges.' if state.local_agent else 'deterministic fixture; no model inference.'), '', '| Stage | Verified result |', '|---|---|', '| Intent and scope | Proposed design reviewed; all children share the same approved root |', '| Concepts | Three original fixture PNGs decoded and hashed against inherited art direction |', '| Owner selection | Exact one-use approval, including under approve_all |', '| Ingest and acceptance | Exclusive copy, hash evidence, separate owner acceptance |', '| Bug intake | Finding triaged and frozen after asset acceptance |', '| Amendment | Fix v1 superseded by reviewed v2 with tighter budget; still one attempt |', '| Regression | Same test checks accepted asset bytes and reward logic; fails before fix |', '| Fix | Gated source edit and real local commit |', '| Verification | Distinct read-only checker; clean baseline and fixed checkouts |', '| Closure | BUG-0001 closed; C0–C3 complete with no next bug queued |', '', f'![Accepted original test fixture](<{state.manifest['asset']['path']}>)', '', f'Pre-fix build: `{state.d['pre_build']}`', '', f'Fixed build: `{state.d['build']}`', '', f'Audit head at verification: `{state.result['audit_head']}` ({state.result['audit_entries']} entries)', '', f'[Audit](<{state.h.audit_path.as_posix()}>) · [Run manifest](<{state.path.as_posix()}>) · [Round evidence](<{state.d['round_report']['path']}>)', '', 'This report records verification at generation time. Refresh current bytes and provenance:', '', f'`py examples/product_demo.py --verify "{state.path}"`', '']
    state.report.write_text('\n'.join(state.lines), encoding='utf-8')
    print(json.dumps({**state.result, 'report': str(state.report), 'manifest': str(state.path)}, indent=2))
    state.result = dict(manifest=state.manifest, report=state.report, result=state.result)

def main(*, local_agent=None, fixture_approvals=False, owner=None, recovery=None):
    if owner is None:
        from ember_harness.owner_review import OwnerReview
        owner = FixtureOwner() if fixture_approvals else OwnerReview()
    if recovery and fixture_approvals:
        raise ValueError('Recovery requires explicit owner reviews')
    state = SimpleNamespace(local_agent=local_agent, owner=owner)
    state = step(recovery, 'product.workflow', state, _workflow, retry=True)
    state = step(recovery, 'product.manifest', state, _manifest, retry=False)
    state = step(recovery, 'product.product_report', state, _product_report, retry=True)
    return state.result



if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint-dir', help='private UI session checkpoint folder')
    parser.add_argument('--verify', help='refresh an existing product.json run without creating another demo')
    parser.add_argument('--local-agent-binary', help='trusted Ollama executable; enables real local inference')
    parser.add_argument('--local-agent-model', default='qwen2.5-coder:7b')
    parser.add_argument('--fixture-approvals', action='store_true', help='explicitly simulate owner approvals for unattended regression tests')
    args = parser.parse_args()
    try:
        from ember_harness.recovery import Recovery
        recovery = Recovery(args.checkpoint_dir, ROOT) if args.checkpoint_dir else None
        if args.verify:
            print(json.dumps(verify_product(json.loads(Path(args.verify).read_bytes())), indent=2))
        else:
            if args.local_agent_binary:
                from ember_harness.local_agent import LocalAgent
                main(local_agent=LocalAgent(args.local_agent_binary, args.local_agent_model), fixture_approvals=args.fixture_approvals, recovery=recovery)
            else:
                main(fixture_approvals=args.fixture_approvals, recovery=recovery)
    except Exception as error:
        print(json.dumps({'passed': False, 'error': str(error)}), file=sys.stderr)
        raise SystemExit(1)
