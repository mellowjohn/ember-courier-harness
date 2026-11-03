"""Saved, bounded gameplay observations. Plans are data, never action authority."""
from copy import deepcopy
from datetime import datetime, timezone
import math
from pathlib import Path
import re

from . import chat_build, project_versions
from .core import digest
from .recovery import atomic_json, exclusive, read_json

KEYS = ('ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Space', 'Enter', 'Escape', 'a', 'd', 'w', 's', 'r')
COVERAGE_PATHS = ('discoverability', 'success', 'failure', 'reset', 'repeated_play')
SELECTOR = r'(?:[a-z][a-z0-9-]*)?(?:#[a-zA-Z_][a-zA-Z0-9_-]*|\[data-testid="[a-zA-Z0-9 _-]+"\])?'
ACTIONS = {
    'click': {'action', 'selector'}, 'tap': {'action', 'selector'},
    'press': {'action', 'key'}, 'wait': {'action', 'ms'},
    'hold': {'action', 'key', 'ms'},
    'visible': {'action', 'selector'}, 'hidden': {'action', 'selector'},
    'text': {'action', 'selector', 'value'}, 'contains': {'action', 'selector', 'value'},
    'number_at_least': {'action', 'selector', 'value'},
}
LIMIT = ('Fixed Chromium actions and DOM assertions only; game code can influence observable state. '
         'Passing these checks does not prove game rules, canvas-only scores, fun or human acceptance.')


def validate(plan):
    if (not isinstance(plan, dict) or set(plan) != {'title', 'scenarios'} or
            not isinstance(plan['title'], str) or not 1 <= len(plan['title'].strip()) <= 120 or
            not isinstance(plan['scenarios'], list) or len(plan['scenarios']) > 4):
        raise ValueError('Use a gameplay plan title and at most four scenarios')
    cost = 0
    for scenario in plan['scenarios']:
        if (not isinstance(scenario, dict) or not {'name', 'viewport', 'steps'} <= set(scenario) or
                set(scenario) - {'name', 'viewport', 'steps', 'coverage'} or
                not isinstance(scenario['name'], str) or not 1 <= len(scenario['name'].strip()) <= 120 or
                scenario['viewport'] not in ('desktop', 'mobile') or not isinstance(scenario['steps'], list) or
                not 1 <= len(scenario['steps']) <= 16):
            raise ValueError('Each scenario needs a name, desktop/mobile, and 1–16 steps')
        coverage = scenario.get('coverage', [])
        if (not isinstance(coverage, list) or len(coverage) > len(COVERAGE_PATHS) or
                any(not isinstance(path, str) or path not in COVERAGE_PATHS for path in coverage) or
                len(set(coverage)) != len(coverage)):
            raise ValueError('Choose each supported gameplay coverage path at most once')
        assertions = 0
        for step in scenario['steps']:
            if not isinstance(step, dict) or not isinstance(step.get('action'), str):
                raise ValueError('Invalid gameplay step')
            action = step['action']
            if action not in ACTIONS or set(step) != ACTIONS[action]:
                raise ValueError('Use only fixed gameplay actions and their declared fields')
            if 'selector' in step and (not isinstance(step['selector'], str) or not step['selector'] or
                    len(step['selector']) > 160 or not re.fullmatch(SELECTOR, step['selector'])):
                raise ValueError('Choose a simple tag, #id or [data-testid="name"] target')
            if action in ('press','hold') and step['key'] not in KEYS:
                raise ValueError('Choose a supported gameplay key')
            if action == 'tap' and scenario['viewport'] != 'mobile':
                raise ValueError('Use a mobile scenario for real touch taps')
            if action in ('wait','hold') and (type(step['ms']) is not int or not 1 <= step['ms'] <= 2000):
                raise ValueError('Waits must be 1–2000 milliseconds')
            if action in ('text', 'contains') and (not isinstance(step['value'], str) or not 1 <= len(step['value']) <= 200):
                raise ValueError('Expected text must contain 1–200 characters')
            if action == 'number_at_least' and (type(step['value']) not in (int, float) or
                    not math.isfinite(step['value']) or abs(step['value']) > 1_000_000):
                raise ValueError('Expected score must be a finite number within one million')
            assertions += action in ('visible', 'hidden', 'text', 'contains', 'number_at_least')
            cost += step['ms'] if action in ('wait','hold') else 1000
        if not assertions:
            raise ValueError('Each scenario needs at least one observable assertion')
    if cost > 20000:
        raise ValueError('Gameplay plan exceeds its 20-second action budget; use fewer steps or shorter waits')
    return deepcopy(plan)


def load(folder):
    path = Path(folder) / 'gameplay-plan.json'
    if not path.exists():
        plan = dict(title='Game loop checks', scenarios=[])
        return dict(revision=0, updated_at=None, plan=plan, sha256=digest(plan))
    saved = read_json(path)
    validate(saved['plan'])
    if type(saved.get('revision')) is not int or saved['revision'] < 1 or saved.get('sha256') != digest(saved['plan']):
        raise ValueError('The saved gameplay plan is damaged')
    return saved


def save(folder, plan, revision):
    plan = validate(plan)
    if type(revision) is not int or revision < 0:
        raise ValueError('A valid gameplay plan revision is required')
    with exclusive(Path(folder) / 'chat.lock'):
        if load(folder)['revision'] != revision:
            raise ValueError('This gameplay plan changed in another window; reload the saved plan')
        result = dict(revision=revision + 1, updated_at=datetime.now(timezone.utc).isoformat(), plan=plan, sha256=digest(plan))
        atomic_json(Path(folder) / 'gameplay-plan.json', result)
        return result


def validate_result(plan, result):
    """Bind every host result to its frozen scenario and step sequence."""
    validate(plan)
    if not plan['scenarios']:
        if result is not None:
            raise ValueError('Unexpected gameplay results without a plan')
        return None
    if not isinstance(result, dict) or result.get('plan_sha256') != digest(plan):
        raise ValueError('Gameplay result does not match the frozen plan')
    scenarios = result.get('scenarios')
    if not isinstance(scenarios, list) or len(scenarios) != len(plan['scenarios']):
        raise ValueError('Gameplay result is incomplete')
    statuses = []
    for expected, observed in zip(plan['scenarios'], scenarios):
        if observed.get('name') != expected['name'] or observed.get('viewport') != expected['viewport']:
            raise ValueError('Gameplay scenario identity changed')
        steps = observed.get('steps')
        if not isinstance(steps, list) or len(steps) != len(expected['steps']):
            raise ValueError('Gameplay steps are incomplete')
        failed = False
        for index, step in enumerate(steps):
            if (type(step.get('index')) is not int or step['index'] != index or step.get('status') not in ('passed', 'failed', 'skipped') or
                    not isinstance(step.get('observed'), str) or len(step['observed']) > 300 or
                    (failed and step['status'] != 'skipped') or (not failed and step['status'] == 'skipped')):
                raise ValueError('Invalid gameplay step result')
            failed |= step['status'] == 'failed'
        errors = observed.get('errors')
        if not isinstance(errors, list) or len(errors) > 5 or any(not isinstance(v, str) or len(v) > 300 for v in errors):
            raise ValueError('Invalid gameplay browser observations')
        status = 'failed' if failed or errors else 'passed'
        if observed.get('outcome') != status:
            raise ValueError('Gameplay scenario outcome differs from its steps')
        statuses.append(status)
    outcome = 'passed' if all(s == 'passed' for s in statuses) else 'failed'
    if result.get('outcome') != outcome:
        raise ValueError('Gameplay outcome differs from its scenarios')
    return result


def reports(folder):
    if not (Path(folder) / 'build-authority').exists():
        return []
    return [e for e in chat_build.harness(folder)._entries() if e['kind'] == 'chat_gameplay_recorded'][-20:]


def _capture(files, saved, output, runtime, *, build_ref=None):
    from . import polish_runtime
    output = Path(output)
    if output.resolve() != output.absolute():
        raise ValueError('Gameplay output path changed')
    output.mkdir(parents=True, exist_ok=True)
    source = output / 'input.json'
    parser = chat_build.ResourcePreview(files)
    parser.feed(files['index.html']); parser.close()
    data = dict(html=''.join(parser.output), gameplay_plan=saved['plan'], gameplay_plan_sha256=saved['sha256'], runtime=runtime)
    # Freeze the matrix with the exact candidate; old retained reports keep their protocol.
    if not source.exists() or read_json(source).get('aspect_ratios'):
        data.update(aspect_ratios=polish_runtime.ASPECT_RATIOS, review_sheets=True)
    from .mechanic_workflow import capture_binding
    bound = capture_binding(files, build_ref or 'capture:' + str(output.name), saved)
    if bound is not None:
        data['mechanic_binding'] = bound
    if source.is_symlink():
        raise ValueError('Gameplay input path changed')
    if source.exists() and read_json(source) != data:
        raise ValueError('Interrupted gameplay input changed; start a new check')
    if not source.exists():
        atomic_json(source, data)
    result = polish_runtime.inspect(runtime, source, output / 'output', check=lambda: None)
    validate_result(saved['plan'], result.get('gameplay'))
    return result


def mechanic_evidence(output, observed):
    if observed.get('mechanics') is None:
        return None
    from .mechanic_recipes import validate_report
    return validate_report(read_json(Path(output) / 'input.json')['mechanic_binding'], observed['mechanics'])


def capture_outcome(observed):
    from .polish_runtime import aspect_failures
    return 'passed' if (not aspect_failures(observed) and observed['gameplay']['outcome'] == 'passed' and
        observed.get('mechanics', {}).get('outcome', 'passed') == 'passed') else 'failed'


def verified_current_report(folder, event):
    from . import polish_runtime
    area = Path(folder) / 'gameplay-runs' / event['report_id']
    report = area / 'output/report.json'
    if report.as_posix() != event['report_path'] or polish_runtime.file_digest(report) != event['report_sha256']:
        raise ValueError('Retained gameplay report changed')
    observed = polish_runtime.verified_report(area / 'input.json', report.parent)
    request = read_json(area / 'input.json')
    if (observed.get('gameplay') != event['gameplay'] or capture_outcome(observed) != event['outcome'] or
            request.get('gameplay_plan') != event['plan'] or request.get('gameplay_plan_sha256') != event['plan_sha256'] or
            event.get('mechanics') != mechanic_evidence(area, observed)):
        raise ValueError('Retained gameplay observations differ from the recorded build and plan')
    return event


def run_current(root, folder, revision, request_ref, report_id):
    """Explicit human-host inspection, no model inference or project writes."""
    from . import polish_runtime
    if not isinstance(report_id, str) or not re.fullmatch('[a-zA-Z0-9-]{16,64}', report_id):
        raise ValueError('A stable gameplay report ID is required')
    folder = Path(folder)
    with exclusive(folder / 'gameplay.lock'):
        with exclusive(folder / 'build.lock'):
            saved = load(folder)
            if type(revision) is not int or saved['revision'] != revision or not saved['plan']['scenarios']:
                raise ValueError('Save a nonempty current gameplay plan before running it')
            chat_build.verify(root, folder)
            state = chat_build.status(root, folder)
            if state['completed'][-1]['request_ref'] != request_ref:
                raise ValueError('The selected game changed; run checks against the current version')
            snapshot = project_versions.snapshot(root, folder, request_ref)
            h = chat_build.harness(folder)
            previous = next((e for e in reports(folder) if e['report_id'] == report_id), None)
            if previous:
                if previous['request_ref'] != request_ref or previous['plan_sha256'] != saved['sha256'] or previous['plan_revision'] != revision:
                    raise ValueError('Gameplay report ID belongs to another version or plan')
                if previous['manifest'] != snapshot['manifest']:
                    raise ValueError('Gameplay report belongs to different game bytes')
                return verified_current_report(folder, previous)
        runtime = polish_runtime.discover(root)
        output = folder / 'gameplay-runs' / report_id
        result = _capture(snapshot['files'], saved, output, runtime, build_ref=request_ref)
        with exclusive(folder / 'build.lock'):
            verified = chat_build.verify(root, folder)
            if (chat_build.status(root, folder)['completed'][-1]['request_ref'] != request_ref or
                    verified['manifest'] != snapshot['manifest'] or load(folder) != saved):
                raise ValueError('The game or plan changed during inspection; retained observations are stale')
            with h._lock():
                return h._append('chat_gameplay_recorded', report_id=report_id, request_ref=request_ref,
                    plan_revision=revision, plan_sha256=saved['sha256'], plan=saved['plan'], manifest=snapshot['manifest'],
                    outcome=capture_outcome(result), gameplay=result['gameplay'], mechanics=mechanic_evidence(output, result),
                    report_path=(output / 'output/report.json').as_posix(),
                    report_sha256=polish_runtime.file_digest(output / 'output/report.json'), basis='host_chromium_assertions', limit=LIMIT)


def proposal_reports(folder):
    if not (Path(folder) / 'build-authority').exists():
        return []
    return [e for e in chat_build.harness(folder)._entries() if e['kind'] == 'chat_proposal_gameplay_recorded'][-20:]


def compare(plan, before, proposed):
    validate_result(plan, before) if before is not None else None
    validate_result(plan, proposed)
    rows = []
    for index, scenario in enumerate(proposed['scenarios']):
        old = before['scenarios'][index]['outcome'] if before else 'not_run'
        new = scenario['outcome']
        change = ('new_coverage' if not before else 'preserved' if old == new == 'passed' else
                  'regression' if old == 'passed' else 'fixed' if new == 'passed' else 'still_failing')
        rows.append(dict(name=scenario['name'], viewport=scenario['viewport'], before=old, proposed=new, change=change))
    return rows


def _verified_proposal_report(folder, report):
    from . import polish_runtime
    for label, proof in report['artifacts'].items():
        if label not in ('before', 'proposed'):
            raise ValueError('Unexpected proposal capture')
        output = Path(folder) / 'proposal-checks' / report['report_id'] / label
        source, artifact = output / 'input.json', output / 'output/report.json'
        if (polish_runtime.file_digest(source) != proof['input_sha256'] or
                polish_runtime.file_digest(artifact) != proof['report_sha256']):
            raise ValueError('Proposal gameplay evidence changed')
        observed = polish_runtime.verified_report(source, artifact.parent)
        if observed.get('gameplay') != report[label]:
            raise ValueError('Proposal gameplay observations changed')
        if report.get('mechanics', {}).get(label) != mechanic_evidence(output, observed):
            raise ValueError('Proposal mechanic observations changed')
        validate_result(report['plan'], report[label])
    if set(report['artifacts']) != ({'before', 'proposed'} if report['before'] is not None else {'proposed'}):
        raise ValueError('Proposal gameplay captures are incomplete')
    if report['comparison'] != compare(report['plan'], report['before'], report['proposed']):
        raise ValueError('Proposal gameplay comparison changed')
    return report


def run_proposal(root, folder, revision, request_ref, report_id):
    """Compare untouched current and pending projects with one frozen saved plan."""
    from . import polish_runtime
    if not isinstance(report_id, str) or not re.fullmatch('[a-zA-Z0-9-]{16,64}', report_id):
        raise ValueError('A stable proposal check ID is required')
    folder = Path(folder)
    with exclusive(folder / 'gameplay.lock'):
        with exclusive(folder / 'build.lock'):
            saved = load(folder)
            if type(revision) is not int or saved['revision'] != revision or not saved['plan']['scenarios']:
                raise ValueError('Save a nonempty current gameplay plan before checking a proposal')
            snapshot = chat_build.proposal_snapshot(root, folder, request_ref)
            completed = chat_build.status(root, folder)['completed']
            before_ref = completed[-1]['request_ref'] if completed else None
            from .mechanic_workflow import binding as mechanic_binding, review as mechanic_review
            source_review = mechanic_review(mechanic_binding(snapshot['before_files']), snapshot['files'])
            previous = next((r for r in chat_build.harness(folder)._entries()
                             if r['kind'] == 'chat_proposal_gameplay_recorded' and r['report_id'] == report_id), None)
            if previous:
                if (previous['request_ref'] != request_ref or previous['plan_revision'] != revision or
                        previous['plan_sha256'] != saved['sha256']):
                    raise ValueError('Proposal check ID belongs to another proposal or plan')
                return _verified_proposal_report(folder, previous)
        runtime = polish_runtime.discover(root)
        work = folder / 'proposal-checks' / report_id
        captures, artifacts, mechanics = {}, {}, {}
        for label, files in [('before', snapshot['before_files']), ('proposed', snapshot['files'])]:
            if not files:
                captures[label] = None
                continue
            observed = _capture(files, saved, work / label, runtime,
                build_ref=before_ref if label == 'before' else request_ref)
            captures[label] = observed['gameplay']
            if observed.get('mechanics') is not None:
                mechanics[label] = mechanic_evidence(work / label, observed)
            artifacts[label] = dict(input_sha256=polish_runtime.file_digest(work / label / 'input.json'),
                                   report_sha256=polish_runtime.file_digest(work / label / 'output/report.json'))
        comparisons = compare(saved['plan'], captures['before'], captures['proposed'])
        outcome = ('regressions_observed' if any(r['change'] == 'regression' for r in comparisons) else
                   'passed' if captures['proposed']['outcome'] == 'passed' else 'checks_failed')
        if mechanics.get('proposed') and not mechanics['proposed']['qualified']:
            outcome = 'checks_failed'
        if source_review and source_review['blockers']:
            outcome = 'checks_failed'
        with exclusive(folder / 'build.lock'):
            if chat_build.proposal_snapshot(root, folder, request_ref) != snapshot or load(folder) != saved:
                raise ValueError('The game, proposal or plan changed during inspection; retained captures are stale')
            h = chat_build.harness(folder)
            with h._lock():
                return h._append('chat_proposal_gameplay_recorded', report_id=report_id, request_ref=request_ref,
                    plan_revision=revision, plan_sha256=saved['sha256'], plan=saved['plan'],
                    manifest=snapshot['manifest'], before_manifest=snapshot['before_manifest'],
                    before=captures['before'], proposed=captures['proposed'], comparison=comparisons, outcome=outcome,
                    mechanics=mechanics,
                    mechanic_review=source_review,
                    artifacts=artifacts, basis='host_chromium_proposal_comparison', limit=LIMIT)


def proposal_status(root, folder):
    pending = next((r for r in chat_build.list_requests(folder) if not r['decision']), None)
    if not pending:
        return None
    saved = load(folder)
    report = next((r for r in reversed(proposal_reports(folder)) if r['request_ref'] == pending['ref']), None)
    result = dict(request_ref=pending['ref'], configured=bool(saved['plan']['scenarios']),
                  revision=saved['revision'], plan_sha256=saved['sha256'], report=report)
    if not result['configured']:
        return dict(result, state='not_configured', reason='Save a gameplay plan to test proposed changes')
    if report is None:
        return dict(result, state='not_run', reason='This proposal has not been checked against the saved plan')
    try:
        with exclusive(Path(folder) / 'build.lock'):
            _current_proposal_report(root, folder, report)
        return dict(result, state=report['outcome'], reason='Observations of the exact current and proposed files')
    except (ValueError, OSError, KeyError) as error:
        return dict(result, state='stale', reason=str(error))


def _current_proposal_report(root, folder, report, *, allow_declined=False):
    snapshot = chat_build.proposal_snapshot(root, folder, report['request_ref'], allow_declined=allow_declined)
    saved = load(folder)
    if (snapshot['manifest'] != report['manifest'] or snapshot['before_manifest'] != report['before_manifest'] or
            saved['sha256'] != report['plan_sha256'] or saved['revision'] != report['plan_revision']):
        raise ValueError('The gameplay plan or proposal changed; run a fresh comparison')
    _verified_proposal_report(folder, report)
    return snapshot


def revision_context(root, folder, ref, report_id, *, allow_declined=False):
    with exclusive(Path(folder) / 'build.lock'):
        report = next((r for r in proposal_reports(folder) if r['report_id'] == report_id), None)
        if report is None or report['request_ref'] != ref:
            raise ValueError('Choose a gameplay report for this proposal')
        snapshot = _current_proposal_report(root, folder, report, allow_declined=allow_declined)
        return dict(request_ref=ref, report_id=report_id, title=snapshot['title'], files=snapshot['files'],
                    plan=report['plan'], before=report['before'], proposed=report['proposed'],
                    comparison=report['comparison'], basis=report['basis'], limit=LIMIT)


def context(root, folder):
    saved = load(folder)
    state = chat_build.status(root, folder)
    latest = state['completed'][-1]['request_ref'] if state['completed'] and not state['resumable'] else None
    current = []
    if latest and chat_build.context(root, folder)['manifest'] == state['completed'][-1].get('manifest', {'index.html': state['completed'][-1]['sha256']}):
        current = [{key:r[key] for key in ('report_id','plan_revision','plan_sha256','outcome','gameplay','basis')}
                   for r in reports(folder) if r['request_ref'] == latest and r['plan_sha256'] == saved['sha256']][-3:]
    return dict(saved_plan=saved, reports=current, limit=LIMIT)
