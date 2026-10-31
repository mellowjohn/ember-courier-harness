"""No-cost Muse transport and unverified review -> gated bug intake demo."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ember_harness import canonical, content_hash, draft
from ember_harness.contract_lock import verify
from ember_harness.muse_reviews import MuseReviews
from ember_harness.reporting import write_intake_report
from examples.intake_demo import setup as intake_setup


def setup(folder=None, provider='echo'):
    folder = Path(folder) if folder else Path(__file__).resolve().parents[1] / '.harness/demos' / ('muse-review-' + uuid.uuid4().hex[:10])
    ctx = intake_setup(folder)
    source = ctx['inputs'] / 'reward.py'
    source.write_text('def reward(coins):\n    return coins - 1\n', encoding='utf-8')
    claim = {'summary': 'Delivery reward loses one coin', 'area': 'balance', 'expected': 'Return the delivered coin count', 'actual': 'Source subtracts one; runtime reproduction has not been performed', 'severity': 'S2', 'symptom_tag': 'reward_loss', 'build_id': 'fixture-source-snapshot'}
    request = {'task': 'Review reward arithmetic and report suspected bugs only.', 'files': [source.as_posix()]}
    response = ctx['inputs'] / 'manual-response.json'
    response.write_bytes(canonical([claim]))
    if provider == 'manual':
        request['response_path'] = response.as_posix()
    else:
        request['fixture_findings'] = [claim]
    request_path = ctx['inputs'] / 'review-request.json'
    request_path.write_bytes(canonical(request))
    scope = draft('ct-muse-review-scope-0001', 'review-planner', 'Read selected source snapshots and capture review claims without modifying source', role='scope')
    scope['limits'] = deepcopy(ctx['scope']['limits'])
    scope['allowed_paths'] = {'read': [ctx['inputs'].as_posix() + '/*'], 'write': []}
    scope['allowed_actions'] = [
        {'action_id': 'inspect', 'tool': 'review.inspect', 'class': 'read', 'args_constraints': {'path': {'equals': request_path.as_posix()}}, 'allow_no_evidence': True},
        {'action_id': 'review', 'tool': 'review.muse', 'class': 'compute', 'args_constraints': {'request': {'equals': request_path.as_posix()}, 'provider': {'one_of': ['echo', 'manual', 'meta']}}, 'allow_no_evidence': True}]
    reviewer = deepcopy(scope)
    reviewer.update(id='ct-muse-reviewer-0001', agent='muse-review-fixture')
    reviewer['extensions']['orchestration']['role'] = 'verifier'
    reviewer['inputs'] = [{'name': path.stem, 'path': path.as_posix(), 'sha256': sha256(path.read_bytes()).hexdigest()} for path in [request_path, source] + ([response] if provider == 'manual' else [])]
    for c, parent in ((scope, None), (reviewer, scope['id'])):
        ctx['h'].save_draft(c)
        ctx['h'].approve(c['id'], 1, approver='johnathan', quote='Explicit local Muse adapter demo fixture approval', expected_hash=content_hash(c), parent_id=parent)
    assert ctx['h'].verify_inputs(reviewer['id'])
    return {**ctx, 'reviewer_contract': reviewer, 'request_path': request_path, 'request': request, 'source': source, 'response': response}


def intake_findings(ctx, reviews, ref):
    # A separate approved intake contract reads captures. The reviewer has no bug-write authority.
    h = ctx['h']
    source_glob = (h.root / 'muse_reviews').as_posix() + '/*/finding-*.json'
    scope = deepcopy(ctx['scope'])
    scope.update(id='ct-muse-intake-scope-0001')
    scope['allowed_paths']['read'] = [(h.root / 'muse_reviews').as_posix() + '/*/*.json']
    scope['allowed_actions'] = [
        {'action_id': 'inspect', 'tool': 'triage.inspect', 'class': 'read', 'args_constraints': {'path': {'path_within': source_glob}}, 'allow_no_evidence': True},
        {'action_id': 'ingest', 'tool': 'triage.ingest', 'class': 'write', 'args_constraints': {'source': {'path_within': source_glob}, 'dest': {'path_within': (ctx['data'] / 'bugs').as_posix() + '/BUG-*.json'}}, 'allow_no_evidence': True}]
    child = deepcopy(scope)
    child.update(id='ct-muse-intake-0001', agent='review-intake-fixture')
    child['extensions']['orchestration']['role'] = 'triage'
    for c, parent in ((scope, None), (child, scope['id'])):
        h.save_draft(c)
        h.approve(c['id'], 1, approver='johnathan', quote='Explicit local review intake fixture approval', expected_hash=content_hash(c), parent_id=parent)
    return [ctx['intake'].ingest(item['path'], contract_id=child['id'])['bugs'][0] for item in reviews.findings(ref)]


def main(binary=None):
    ctx = setup(provider='echo' if binary else 'manual')
    if binary:
        binary = Path(binary).resolve()
    reviews = MuseReviews(ctx['h'], binary=binary, binary_sha256=sha256(binary.read_bytes()).hexdigest() if binary else None)
    original = ctx['source'].read_bytes()
    result = reviews.run(ctx['request_path'], contract_id=ctx['reviewer_contract']['id'], provider='echo' if binary else 'manual')
    assert result['status'] == 'captured', result
    assert ctx['source'].read_bytes() == original
    bugs = intake_findings(ctx, reviews, result['capture_ref'])
    assert len(bugs) == 1 and bugs[0]['state'] == 'needs_repro' and bugs[0]['owner'] == 'QA'
    assert 'independent_repro' in bugs[0]['completeness']['missing']
    try:
        ctx['intake'].snapshot(bugs[0]['id'], 'ct-fix-unverified-review-0001')
        raise AssertionError('review claims cannot authorize a fix')
    except ValueError:
        pass
    try:
        reviews.run(ctx['request_path'], contract_id=ctx['reviewer_contract']['id'], provider='meta')
        raise AssertionError('automatic credit use must be blocked')
    except ValueError as error:
        assert 'muse_credit_limit_unavailable' in str(error), str(error)
    lock = verify(ctx['h'].root)
    assert lock['ok'], lock
    queue = write_intake_report(ctx['h'], ctx['data'])
    report = ctx['folder'] / 'DEMO.md'
    report.write_text('\n'.join([
        '# Optional Muse review adapter', '',
        'This is a transport/intake demonstration with approved fixture contracts. Echo uses the installed Muse CLI but produces no AI judgment. Manual mode imports a fixture response. No AI credits are consumed.', '',
        '| Check | Actual result |', '|---|---|',
        f"| Backend | {result['label']} |", '| Source access | Only approved, hashed source snapshots; original bytes unchanged |',
        '| Suspected reward bug | Captured and ingested through a separate approved intake contract |',
        '| Bug route | QA / needs_repro; independent reproduction required |',
        '| Premature fix snapshot | DENIED |', '| Automatic Meta credit use | DENIED: no verified hard credit cap |',
        '| Contract-lock / audit | PASS |', '',
        f"[Captured review](<{result['path']}>) · [Audit-backed bug queue](<{Path(queue['path']).as_posix()}>)", '',
        'Live Meta review is deliberately unavailable in this version. Muse reported no allowance, and its inspected CLI has no verified dollar-cap control. Credit-consuming runs need a separately implemented, enforceable budget policy. The existing spend-$0 and owner approval gates remain intact.', '',
        'Rerun offline: `py examples/muse_review_demo.py`',
        'Use the installed CLI echo backend: `py examples/muse_review_demo.py --binary PATH_TO_MUSE_EXE`', ''
    ]), encoding='utf-8')
    print(json.dumps({'status': result['status'], 'backend': result['label'], 'bug': bugs[0]['id'], 'bug_state': bugs[0]['state'], 'integrity_ok': lock['ok'], 'report': str(report)}, indent=2))
    return {**ctx, 'report': report, 'result': result}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary')
    main(parser.parse_args().binary)
