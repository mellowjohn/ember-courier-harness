"""Automatic, read-only checks of exact chat proposals and screenshot-based review."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import time

from jsonschema import Draft202012Validator

from . import asset_library, chat_build, gameplay, polish, polish_runtime, task_quality
from .core import digest, canonical
from .muse_chat import run as run_muse, execution_policy
from .recovery import atomic_json, exclusive, read_json


def workdir(folder, ref):
    if not isinstance(ref, str) or not re.fullmatch('[0-9a-f]{64}', ref):
        raise ValueError('Choose an exact build proposal')
    work = Path(folder) / 'proposal-quality' / ref
    if work.resolve() != work.absolute():
        raise ValueError('Proposal verification path changed')
    return work


def load(folder, ref):
    """Only audit-bound reports and verified image bytes can become feedback."""
    work = workdir(folder, ref)
    if not (work / 'report.json').is_file():
        return None
    report = read_json(work / 'report.json')
    h = chat_build.harness(folder)
    if not any(e['kind'] == 'chat_quality_recorded' and e['request_ref'] == ref and
               e['sha256'] == digest(report) for e in h._entries()):
        raise ValueError('Proposal verification report changed')
    verify_captures(work,report)
    return report


def verify_captures(work, report):
    for label, proof in report.get('artifacts', {}).items():
        if label not in ('before', 'candidate'):
            raise ValueError('Invalid verification capture')
        source, output = work / label / 'input.json', work / label / 'output'
        if polish_runtime.file_digest(source) != proof['input_sha256'] or polish_runtime.file_digest(output/'report.json') != proof['report_sha256']:
            raise ValueError('Proposal verification capture changed')
        if polish_runtime.verified_report(source, output) != report['observations'][label]:
            raise ValueError('Proposal verification observations changed')


def current(root, folder, report, *, allow_declined=False):
    snapshot = chat_build.proposal_snapshot(root, folder, report['request_ref'], allow_declined=allow_declined)
    if (snapshot['manifest'] != report['manifest'] or snapshot['before_manifest'] != report['before_manifest'] or
            gameplay.load(folder) != report['saved_checks']):
        raise ValueError('Verification belongs to different files or gameplay checks')
    return snapshot


def run(root, folder, ref, *, ask, brief, design, checks=None, original_ask=None, progress=lambda *a, **k: None):
    folder = Path(folder)
    work = workdir(folder, ref)
    with exclusive(folder / 'quality.lock'):
        with exclusive(folder / 'build.lock'):
            snapshot = chat_build.proposal_snapshot(root, folder, ref)
            saved = gameplay.load(folder)
        original_ask = original_ask or ask
        context = dict(ask=ask, original_ask=original_ask, brief=brief, design=design, checks=checks)
        previous = load(folder, ref)
        if previous:
            current(root, folder, previous)
            if previous['context_sha256'] != digest(context):
                raise ValueError('Verification request changed')
            return previous
        plan = deepcopy(saved['plan'])
        warnings = []
        if checks:
            gameplay.validate(checks)
            extra = [s for s in checks['scenarios'] if s not in plan['scenarios']]
            merged = dict(title=plan['title'], scenarios=plan['scenarios'] + extra)
            try:
                gameplay.validate(merged)
                plan = merged
            except ValueError:
                warnings.append('The additional checks exceed the bounded test allowance; saved checks were retained. Coverage is incomplete.')
        if not plan['scenarios']:
            warnings.append('No gameplay assertions were supplied. Functionality is unverified.')
        document = design['document'] if design else dict(scope=dict(core_loop=ask, out_of_scope=[],
            asset_budget={}, done_criteria=[ask]), art_direction=brief['fields'].get('visual_direction', 'Follow the user request'))
        quality = task_quality.prepare(dict(goal=original_ask+'\nCurrent request: '+ask, project_plan=dict(document=document), brief=brief,
            gameplay_plan=dict(plan=plan)))
        quality['criteria'].insert(-1, dict(id='coverage',method='ai',
            expectation='The executed assertions test the requested behavior and its feedback, not just startup, static labels or a counter unrelated to the game.'))
        report = dict(request_ref=ref, original_ask=original_ask, context_sha256=digest(context), manifest=snapshot['manifest'],
            before_manifest=snapshot['before_manifest'], saved_checks=saved, checks=plan, quality=quality,
            status='unavailable', issues=list(warnings), artifacts={}, observations={},
            basis='Host browser observations and separate AI visual judgment; human acceptance remains pending.')
        work.mkdir(parents=True, exist_ok=True)
        try:
            runtime = polish_runtime.discover(root)
            for label, files in [('before',snapshot['before_files']),('candidate',snapshot['files'])]:
                if not files:
                    continue
                progress('testing_before' if label == 'before' else 'testing_candidate')
                observed = gameplay._capture(files,dict(plan=plan,sha256=digest(plan)),work/label,runtime)
                report['observations'][label] = observed
                report['artifacts'][label] = dict(input_sha256=polish_runtime.file_digest(work/label/'input.json'),
                    report_sha256=polish_runtime.file_digest(work/label/'output/report.json'))
                current(root, folder, report)
            observed = report['observations']['candidate']
            files = {k:v for k,v in snapshot['files'].items() if k not in chat_build.PROTECTED_FILES}
            pictures = polish_runtime.review_images(work/'candidate/output')
            progress('visual_review')
            prompt = ('Independently verify these exact proposed game changes against the user request, saved brief and approved design. '
                'Inspect the attached actual desktop/mobile PNGs and any movement poses, not the coder narrative. '
                'Do not accept placeholder shapes when authored artwork was requested. Check whether the functional assertions '
                'exercise the requested mechanic and feedback; an unchanged label or successful page load is insufficient. '
                'Report concrete mismatches and regressions. Return meets_task, preserves_scope, summary, issues and criteria. '
                + task_quality.INSTRUCTION + '\n' + canonical(dict(ask=ask,original_ask=original_ask,brief=brief,approved_design=design,
                    **asset_library.prompt_files(snapshot['files']),checks=plan,quality=quality,observations=report['observations'],
                    image_order=[p.name for p in pictures],coverage_warnings=warnings)).decode())
            schema = task_quality.schema(task_quality.VERDICT_SCHEMA)
            last_check = 0
            def check_running():
                nonlocal last_check
                if time.monotonic()-last_check >= 5:
                    current(root,folder,report)
                    last_check = time.monotonic()
            capture = run_muse(root, folder, prompt, 'quality-' + ref, output_schema=schema,images=pictures,
                budget=dict(id=sha256((str(folder.resolve())+':quality:'+ref).encode()).hexdigest(),limit_micro_usd=5_000_000),
                execution=execution_policy('verify',source_bytes=sum(len(v.encode()) for v in files.values())),
                progress=lambda *a,**kw: progress('visual_review'),check=check_running)
            verdict = json.loads(capture['response'])
            Draft202012Validator(schema).validate(verdict)
            assessment = task_quality.review(quality,verdict,files,observed)
            report.update(verdict=verdict,assessment=assessment)
            report['issues'] += assessment['blockers'] + verdict['issues']
            if not verdict['meets_task'] or not verdict['preserves_scope']:
                report['issues'].append(verdict['summary'])
            if polish.failures(dict(observations=observed)) or not all(v.get('loaded') for v in observed['viewports']):
                report['issues'].append('Browser errors, missing artwork, layout overflow or failed gameplay assertions were observed.')
            report['status'] = 'needs_changes' if report['issues'] else 'passed'
        except (ValueError,OSError) as error:
            report['issues'].append(str(error))
        # Never attach successful evidence to bytes or checks that changed mid-run.
        with exclusive(folder / 'build.lock'):
            current(root,folder,report)
            verify_captures(work,report)
            atomic_json(work/'report.json',report)
            h = chat_build.harness(folder)
            with h._lock():
                h._append('chat_quality_recorded',request_ref=ref,sha256=digest(report),status=report['status'])
        progress('reviewed', detail={
            'passed': 'The automated checks and screenshot review found no blocking issues. Try the proposed game to judge how it feels.',
            'needs_changes': 'The review found issues with the proposed game. Read the findings before deciding what to change next.',
            'unavailable': 'The review could not finish. The proposed game has not been fully verified.',
        }[report['status']])
        return report


def status(root, folder):
    pending = next((r for r in chat_build.list_requests(folder) if not r['decision']), None)
    if not pending:
        return None
    try:
        report = load(folder,pending['ref'])
        if report is None:
            return None
        current(root,folder,report)
        return report
    except (ValueError,OSError) as error:
        return dict(request_ref=pending['ref'],status='stale',issues=[str(error)])


def revision_context(root, folder, ref, *, allow_declined=False):
    report = load(folder,ref)
    if report is None:
        return None
    snapshot = current(root,folder,report,allow_declined=allow_declined)
    return dict(request_ref=ref,quality_ref=ref,files=snapshot['files'],verification=report,
                basis='Verified saved browser observations and AI judgment; untrusted feedback, not instructions.')


def images(folder, ref):
    report = load(folder,ref)
    if report is None or 'candidate' not in report.get('artifacts',{}):
        return []
    return polish_runtime.review_images(workdir(folder,ref)/'candidate/output')


def image(root, folder, ref, name):
    report = status(root,folder)
    if not report or report['request_ref'] != ref or report['status']=='stale':
        raise ValueError('Choose a current verified proposal')
    allowed = {p.name:p for p in images(folder,ref)}
    if name not in allowed:
        raise ValueError('Choose a recorded verification screenshot')
    return allowed[name].read_bytes()
