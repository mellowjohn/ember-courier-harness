"""Real UI/model-to-Git repair rehearsal; model and owner choices are fixtures."""
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'tests'))
from quality_fixture import assessments, comparison
from ember_harness import chat_build, findings, gameplay, git_automation, git_task, polish_runtime, project_plan, task_run
from ember_harness.attempts import Attempts
from ember_harness.local_ui import App, server
from ember_harness.muse_chat import CreditLedger
from tools.browser_check import synthetic_provider_guard
from tools.git_task_check import FILES
from tools.release_check import source_manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finding', action='store_true', help='Use a canonical finding and separately review C3 closure')
    args = parser.parse_args(argv)
    output = ROOT / '.harness/git-automation-checks' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
    output.mkdir(parents=True); before = source_manifest()
    root = Path(tempfile.mkdtemp(prefix='a', dir=ROOT / '.harness'))
    (root / 'examples').mkdir(); (root / 'examples/product_demo.py').touch()
    app = App(root); app.start('SYNTHETIC automated Git repair', chat_only=True)
    folder = app.sessions_dir / app.session['id']
    binary = root / 'synthetic-muse.exe'; binary.write_bytes(b'SYNTHETIC identity; never executed')
    runtime = polish_runtime.discover(ROOT)
    files = dict(FILES)
    files['app.js'] = ('let score=0;const hud=document.querySelector("#score");'
        'function collect(){score+=1;hud.textContent=score}'
        'function activate(id,action){const b=document.querySelector(id);b.onpointerdown=e=>{if(e.button===0){e.preventDefault();action()}};b.onclick=e=>{if(e.detail===0)action()}}'
        'activate("#collect",collect);activate("#reset",()=>{score=0;hud.textContent=score});'
        'addEventListener("keydown",e=>{if(e.code==="Space"&&!e.repeat){e.preventDefault();collect()}});')
    candidate = {**files, 'app.js': files['app.js'].replace('score+=1', 'score+=2')}
    calls = []; workers = []; error = None; result = None

    def model(root, folder, prompt, phase, **kwargs):
        data = json.loads(prompt.split('\n', 1)[1]); calls.append(dict(phase=phase, image_count=len(kwargs['images'])))
        if phase.startswith('generate'):
            reply = dict(title='Generated two-point Git repair', summary='SYNTHETIC repair from frozen source and checks',
                edits=[dict(path='app.js', before='score+=1', after='score+=2')])
        else:
            reply = dict(meets_task=True, preserves_scope=True, issues=[], summary='SYNTHETIC separate source/capture judgment')
            if data.get('quality'): reply['criteria'] = assessments(data)
            if data.get('comparison'): reply['comparison'] = comparison(data)
        return dict(response=json.dumps(reply))

    def launch(project, session, run_id):
        task = threading.Thread(target=task_run.Worker(project, session, run_id).run, daemon=True)
        task.start(); workers.append(task)
        return dict(status='running')

    with synthetic_provider_guard(), patch('ember_harness.task_run.installed_binary', return_value=binary), \
            patch('ember_harness.task_run.run_muse', side_effect=model), patch('ember_harness.task_run.launch', side_effect=launch), redirect_stdout(io.StringIO()):
        initial = chat_build.propose_build(root, folder, 'git-automation-initial', 'SYNTHETIC initial source',
            dict(title='Original one-point counter', summary='SYNTHETIC starting browser game', files=[dict(path=k, content=v) for k,v in files.items()]))
        app.respond(initial, 'approve', 'SYNTHETIC initial source setup')
        document = project_plan.starter(folder)
        document['scope']['features'] = ['Repair two-point parcel scoring; preserve keyboard, touch and restart']
        ref = project_plan.prepare(root, folder, document, None)['request_ref']
        app.respond(ref, 'approve', 'SYNTHETIC approved project task and permissions ceiling')
        checks = dict(title='Two-point reward with keyboard/touch/reset', scenarios=[
            dict(name='Keyboard two-point reward and reset', viewport='desktop', coverage=['success', 'reset'], steps=[
                dict(action='press', key='Space'), dict(action='text', selector='#score', value='2'),
                dict(action='click', selector='#reset'), dict(action='text', selector='#score', value='0')]),
            dict(name='Touch two-point reward and reset', viewport='mobile', coverage=['success', 'reset'], steps=[
                dict(action='tap', selector='#collect'), dict(action='text', selector='#score', value='2'),
                dict(action='tap', selector='#reset'), dict(action='text', selector='#score', value='0')])])
        gameplay.save(folder, checks, 0)
        if args.finding:
            app.record_playtest(report_id='synthetic-auto-git-finding-001', request_ref=initial, outcome='problem',
                note='SYNTHETIC parcel reward is one point; expected two', observations=[])
            ref = app.finding_control(folder.name, 'prepare', report_id='synthetic-auto-git-finding-001',
                fields=dict(summary='Parcel reward is one point', area='browser_game', symptom_tag='one_point_reward',
                    steps=['Collect parcel', 'Inspect score'], expected='Two points', actual='One point', frequency='always', impact='degraded'))['request_ref']
            app.respond(ref, 'approve', 'SYNTHETIC reviewed canonical finding intake')
        http = server(app); thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
        previous_pythonpath = os.environ.get('PYTHONPATH')
        os.environ['PYTHONPATH'] = str(ROOT)
        try:
            env = dict(os.environ, EMBER_PLAYWRIGHT_MODULE=runtime['module'], EMBER_BROWSER_EXECUTABLE=runtime['browser'],
                EMBER_BROWSER_URL=f'http://127.0.0.1:{http.server_port}/', EMBER_BROWSER_TOKEN=app.token,
                EMBER_BROWSER_OUTPUT=str(output), EMBER_GIT_FINDING='1' if args.finding else '0')
            with (output / 'browser.log').open('w', encoding='utf-8') as log:
                completed = subprocess.run([runtime['node'], str(ROOT / 'tools/git_automation_check.js')], cwd=ROOT,
                    env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
            if completed.returncode: raise ValueError('Automated Git browser rehearsal failed; see browser.log')
            for task in workers: task.join(timeout=10)
            source = git_automation.history(root, folder)[-1]
            git = git_task.history(root, folder)[-1]
            source_plan = task_run.load(folder, source['task_run_id'])[3]
            if not git['report']['qualified'] or chat_build.context(root, folder)['manifest'] != git['candidate_manifest']:
                raise ValueError('Generated source did not pass clean Git verification and exact application')
            if len(source['attempts']['attempts']) != 1: raise ValueError('Source and Git stages must share exactly one allocation')
            if [row['phase'] for row in calls] != ['generate-1', 'verify-1']:
                raise ValueError('Expected one coding call and one independent review, no calls in the Git stage')
            if project_plan.status(root, folder)['tasks'][0]['state'] != 'applied_needs_review':
                raise ValueError('Exact application must not accept the task')
            if args.finding:
                bug = findings.intake(folder).list()[0]
                if bug['state'] != 'closed' or findings.validate_history(chat_build.harness(folder), chat_build.harness(folder)._entries()) != 1:
                    raise ValueError('Canonical finding closure lost its explicit owner and Git witnesses')
                if len(Attempts(chat_build.harness(folder)).status(bug['id'])['attempts']) != 1:
                    raise ValueError('Git verification allocated a second canonical finding attempt')
            usage = CreditLedger(root).summary()
            if usage['reserved_usd'] or usage['estimated_spent_usd']: raise ValueError('Synthetic rehearsal used credits')
            result = dict(source_run=source['task_run_id'], git_run=git['id'], source_manifest=source_plan['base_manifest'],
                candidate_manifest=git['candidate_manifest'], base=git['report']['base'], head=git['report']['head'],
                shared_single_attempt=True, model_calls=calls, canonical_finding=args.finding,
                human_task_acceptance='pending', zero_credit_use=True, fixture_workspace=str(root))
        except Exception as failure:
            error = str(failure)
        finally:
            http.shutdown(); http.server_close(); thread.join(timeout=5)
            if previous_pythonpath is None: os.environ.pop('PYTHONPATH', None)
            else: os.environ['PYTHONPATH'] = previous_pythonpath
    unchanged = source_manifest() == before
    report = dict(passed=error is None and unchanged, error=error, source_unchanged=unchanged, source_manifest=before,
        result=result, basis='Real UI, isolated Git commits, clean before/head Chromium keyboard/touch/reset checks and exact apply. Model replies and owner decisions are synthetic; no live quality or human task acceptance.')
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (output / 'REPORT.md').write_text('# Automated Git product rehearsal\n\n' + ('PASS' if report['passed'] else 'FAIL') +
        '\n\n' + report['basis'] + '\n\nSource unchanged: ' + str(unchanged) + ('\n\n' + error if error else '') + '\n', encoding='utf-8')
    print(output / 'REPORT.md')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
