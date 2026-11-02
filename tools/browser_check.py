"""Run the local browser QA/restore rehearsal with synthetic fixtures and no Muse calls."""
import argparse
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ember_harness import chat_build, project_versions, gameplay, project_plan, project_brief, task_run, findings, workspace, session_chat
from ember_harness.local_ui import App, server
from tools.release_check import source_manifest

FILES = {
    'index.html': '<!doctype html><html><head><title>Browser QA fixture</title><link rel="stylesheet" href="style.css"></head>'
                  '<body><h1>Original counter fixture</h1><button>Start</button><p id="score">0</p><script src="app.js"></script></body></html>',
    'style.css': 'body {background:#e8f0e4;color:#18251b;font:20px sans-serif;padding:20px}',
    'app.js': 'let score=0;const button=document.querySelector("button");'
              'button.onclick=()=>{button.textContent="Started";document.querySelector("#score").textContent=++score};'
              'addEventListener("keydown",e=>{if(e.key==="ArrowRight")document.querySelector("#score").textContent=++score});',
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', default='node')
    parser.add_argument('--ui-only', action='store_true', help='Run chat/game layout, preview controls and old-server state regressions only')
    parser.add_argument('--playtest-fix-only', action='store_true', help='Check notes-only scoped fixes, observed progress and browser dictation')
    parser.add_argument('--playwright-module', help='optional path to an installed Playwright module')
    parser.add_argument('--browser-executable', help='optional Chromium executable; otherwise use Playwright browser')
    args = parser.parse_args(argv)
    output = ROOT / '.harness/browser-checks' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    before = source_manifest()
    fixture = output / 'fixture'
    (fixture / 'examples').mkdir(parents=True)
    (fixture / 'examples/product_demo.py').touch()
    app = App(fixture)
    workspace_source = output / 'existing-workspace'
    workspace_source.mkdir()
    (workspace_source / 'AGENTS.md').write_text('SYNTHETIC existing owner instructions', encoding='utf-8')
    (workspace_source / '.env').write_text('SYNTHETIC secret: must never enter reports', encoding='utf-8')
    (workspace_source / '.gitignore').write_text('*.log\n', encoding='utf-8')
    (workspace_source / 'ignored.log').write_text('SYNTHETIC ignored content', encoding='utf-8')
    (workspace_source / 'game.js').write_text('throw Error("SYNTHETIC source must not execute");', encoding='utf-8')
    from hashlib import sha256
    workspace_before = {p.name: sha256(p.read_bytes()).hexdigest() for p in workspace_source.iterdir()}
    copy_parent = output / 'User Projects'; copy_parent.mkdir()
    app.start('SYNTHETIC browser QA rehearsal', chat_only=True)
    folder = app.sessions_dir / app.session['id']
    gameplay.save(folder,dict(title='Counter scoring',scenarios=[
        dict(name='Keyboard scoring',viewport='desktop',steps=[dict(action='press',key='ArrowRight'),dict(action='number_at_least',selector='#score',value=1)]),
        dict(name='Touch scoring',viewport='mobile',steps=[dict(action='tap',selector='button'),dict(action='number_at_least',selector='#score',value=1)])]),0)
    def complete(files, turn):
        with redirect_stdout(io.StringIO()):
            ref = chat_build.propose_build(fixture, folder, turn, 'Synthetic browser fixture',
                dict(title='Synthetic counter', summary='Original browser QA fixture',
                     files=[dict(path=name, content=content) for name, content in files.items()]),
                expected_before=chat_build.context(fixture, folder)['sha256'])
        app.respond(ref, 'approve', 'SYNTHETIC browser rehearsal: fixture setup')
        return ref
    first = complete(FILES, 'browser-first-fixture')
    broken = {**FILES, 'app.js': FILES['app.js'] + '\nthrow Error("SYNTHETIC startup failure");'}
    complete(broken, 'browser-broken-fixture')
    if args.playtest_fix_only:
        saved=gameplay.load(folder)
        gameplay.save(folder,dict(title='No manual checks required',scenarios=[]),saved['revision'])
        prepared=project_plan.prepare(fixture,folder,project_plan.starter(folder),None)
        app.respond(prepared['request_ref'],'approve','SYNTHETIC TEST: approve fixture game scope')
    fixed = {**FILES, 'app.js': FILES['app.js'] + '\ndocument.body.dataset.revision="fixed";'}
    reply = dict(response=json.dumps(dict(message='SYNTHETIC fixture fix: review before application.',
                 build=dict(title='Synthetic reviewed fix', summary='Remove the known fixture startup failure',
                            edits=[dict(path='app.js', before='throw Error("SYNTHETIC startup failure");',
                                        after='document.body.dataset.revision="fixed";')]))))
    revised_contexts=[];planned_contexts=[];task_calls=[];task_workers=[];note_calls=[]
    task_binary=fixture/'synthetic-muse.exe';task_binary.write_bytes(b'Synthetic task identity; never executed')
    def task_model(root,folder,prompt,phase,**kwargs):
        task_calls.append(phase)
        if phase.startswith('generate'):
            data=json.loads(prompt.split('\n',1)[1]);files=data['files']
            name='app.js' if data.get('finding') else 'style.css'
            before=files[name]
            after=before.replace('++score','(score+=10)') if data.get('finding') else before+'\nbutton {border-radius:14px}'
            result=dict(title='SYNTHETIC verified finding fix' if data.get('finding') else 'SYNTHETIC independently verified task',summary='Coder narrative is not verification',
                        edits=[dict(path=name,before=before,after=after)])
        else:
            result=dict(meets_task=True,preserves_scope=True,summary='SYNTHETIC separate task assessment',issues=[])
            data=json.loads(prompt.split('\n',1)[1])
            if data.get('quality'):
                result['criteria']=[]
                for c in data['quality']['criteria']:
                    method=c['method'];evidence=[]
                    if method=='gameplay':
                        evidence=[dict(kind='gameplay',ref=str(c['scenario']),detail='SYNTHETIC passing scenario')]
                    elif method=='visual':
                        evidence=[dict(kind='capture',ref=v['screenshot'],detail='SYNTHETIC visual judgment') for v in data['observations']['viewports']]
                    elif method!='human':
                        name,content=next(iter(data['files'].items()))
                        evidence=[dict(kind='source',ref=name,detail=content[:200])]
                    result['criteria'].append(dict(id=c['id'],status='not_observed' if method=='human' else 'met',reason='SYNTHETIC assessment',evidence=evidence))
        return dict(response=json.dumps(result))
    def launch_task(root,folder,run_id):
        thread=threading.Thread(target=task_run.Worker(root,folder,run_id).run,daemon=True)
        task_workers.append(thread);thread.start();return dict(status='running')
    def model(root,folder,prompt,turn,**kwargs):
        if kwargs.get('output_schema')==session_chat.DIAGNOSIS_SCHEMA:
            note_calls.append('investigate');kwargs['progress']('muse_working');time.sleep(3)
            return dict(response=json.dumps(dict(summary='A startup exception follows the counter handlers.',
                cause='app.js explicitly throws an error after registering its controls.',files=['app.js'],
                plan='Remove the exception and preserve the counter controls.')))
        data=json.loads(prompt.split('\n',1)[1])
        text=data['conversation'][-1]['content']
        if data.get('playtest_fix'):
            note_calls.append('fix');kwargs['progress']('muse_working');time.sleep(3)
            return dict(response=json.dumps(dict(message='Proposed fix from your notes. Try it before applying.',build=dict(
                title='SYNTHETIC playtest notes fix',summary='Remove the startup exception without changing controls',
                edits=[dict(path='app.js',before='throw Error("SYNTHETIC startup failure");',after='// Startup exception removed')]))))
        if text.startswith('SYNTHETIC remember brief'):
            updates = dict(goal='Original offline courier game') if text.endswith('goal') else dict(controls='Touch')
            return dict(response=json.dumps(dict(message='SYNTHETIC remembered. What should the game look like?',
                                                 brief_updates=updates,build=None)))
        if text in ('SYNTHETIC prepare conversational project plan','SYNTHETIC add a delivery streak to the plan'):
            document=project_plan.starter(folder) if data['project_plan'] is None else data['project_plan']['document']
            document['scope'].update(game_concept='SYNTHETIC complete courier project',core_loop='Start, score, deliver and restart',
                features=['Core scoring loop','Keyboard and touch controls'],out_of_scope=['Combat','Multiplayer'],
                done_criteria=['Score with keyboard and touch','Human playtest and exact asset acceptance'])
            if 'delivery streak' in text:document['scope']['features'].append('Delivery streak')
            return dict(response=json.dumps(dict(message='SYNTHETIC conversational plan. Review below.',build=None,plan=document)))
        revision=data.get('proposal_context')
        if data.get('project_plan'):
            plan=data['project_plan'];planned_contexts.append(plan)
            if not plan['active'] or plan['selected_task']!='task-2' or plan['document']['scope']['out_of_scope']!=['Combat','Multiplayer']:
                raise ValueError('The selected task lost its approved project scope')
            files={row['path']:row['content'] for row in data['project']['files']}
            build=dict(title='SYNTHETIC planned controls task',summary='Preserve scoring and improve the active controls task',
                       edits=[dict(path='style.css',before=files['style.css'],after=files['style.css']+'\nbutton {outline-offset:3px}')])
        elif revision:
            revised_contexts.append(revision)
            build=dict(title='Synthetic repaired gameplay',summary='Keep the rounded controls and repair keyboard scoring',edits=[
                dict(path='app.js',before='SYNTHETIC_DISABLED_CONTROL',after='ArrowRight'),
                dict(path='app.js',before='proposal-broken',after='fixed')])
        elif any('SYNTHETIC propose a scoring regression' in item['content'] for item in data['conversation']):
            files={**FILES,'style.css':FILES['style.css']+' button {border-radius:12px}',
                   'app.js':FILES['app.js'].replace('if(e.key==="ArrowRight")','if(e.key==="SYNTHETIC_DISABLED_CONTROL")')+'\ndocument.body.dataset.revision="proposal-broken";'}
            build=dict(title='Synthetic unapproved scoring regression',summary='Rounded controls with a deliberately broken keyboard path',files=[dict(path=k,content=v) for k,v in files.items()])
        else:return reply
        return dict(response=json.dumps(dict(message='SYNTHETIC proposal; review before applying.',build=build)))
    http = server(app)
    worker = threading.Thread(target=http.serve_forever, daemon=True)
    worker.start()
    env = dict(os.environ, EMBER_UI_ONLY='1' if args.ui_only else '0', EMBER_BROWSER_URL=f'http://127.0.0.1:{http.server_port}/',
               EMBER_BROWSER_TOKEN=app.token, EMBER_BROWSER_OUTPUT=str(output), EMBER_PROJECT_PARENT=str(copy_parent),
               EMBER_WORKSPACE_SOURCE=str(workspace_source))
    if args.playwright_module:
        env['EMBER_PLAYWRIGHT_MODULE'] = str(Path(args.playwright_module).resolve())
    if args.browser_executable:
        env['EMBER_BROWSER_EXECUTABLE'] = str(Path(args.browser_executable).resolve())
    error = None
    try:
        with patch('ember_harness.session_chat.run_muse', side_effect=model), \
                patch('ember_harness.project_locations.pick', return_value=str(copy_parent)), \
                patch('ember_harness.task_run.run_muse', side_effect=task_model), \
                patch('ember_harness.task_run.installed_binary', return_value=task_binary), \
                patch('ember_harness.task_run.launch', side_effect=launch_task), redirect_stdout(io.StringIO()):
            with (output / 'browser.log').open('w', encoding='utf-8') as stream:
                result = subprocess.run([args.node, str(ROOT / 'tools' / ('playtest_fix_check.js' if args.playtest_fix_only else 'browser_check.js'))], env=env,
                                        cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=900)
            if result.returncode:
                raise ValueError('Browser rehearsal failed; see browser.log')
        if args.playtest_fix_only:
            if note_calls!=['investigate','fix'] or len(project_versions.history(folder))!=3 or findings.history(fixture,folder):
                raise ValueError('Notes-only fixing did not preserve the two-pass workflow, approval or optional findings')
        elif not args.ui_only:
            versions = project_versions.history(folder)
            if len(versions) != 5 or project_versions.snapshot(fixture, folder, versions[-1]['request_ref'])['files'] != FILES:
                raise ValueError('Restore did not preserve all five versions and exact original files')
            comparisons=gameplay.proposal_reports(folder)
            if [r['outcome'] for r in comparisons]!=['regressions_observed','passed','passed'] or len(revised_contexts)!=1:
                raise ValueError('Proposal comparisons did not preserve regression, repaired proposal and restore results')
            if 'SYNTHETIC_DISABLED_CONTROL' not in revised_contexts[0]['files']['app.js']:
                raise ValueError('The fix request lost the unapplied proposed source')
            reports = app.snapshot()['build']['smoke_checks']
            if [r['outcome'] for r in reports] != ['issues_observed', 'no_errors_observed', 'no_errors_observed']:
                raise ValueError('Browser reports did not capture failure, reviewed fix and restoration')
            copies = [s for s in app.history() if s['name'] == 'SYNTHETIC saved project copy']
            if len(copies) != 1:
                raise ValueError('Save as did not retain a separate saved session')
            copied_folder = app.sessions_dir / copies[0]['id']
            copied = project_versions.history(copied_folder)
            if len(copied) != 4 or project_versions.snapshot(fixture, copied_folder, copied[0]['request_ref'])['files'] != FILES:
                raise ValueError('Save as did not preserve the exact latest approved game')
            plan_state=project_plan.status(fixture,copied_folder)
            if len(planned_contexts)!=1 or plan_state['approved']['version']!=2 or not plan_state['active']:
                raise ValueError('Persistent project plan, selected task or reviewed amendment was not exercised')
            entries=chat_build.harness(copied_folder)._entries()
            if len([e for e in entries if e['kind']=='project_task_accepted'])!=2:
                raise ValueError('Applying a task must not replace its separate human outcome acceptance')
            runs=task_run.history(fixture,copied_folder)
            planned_run=next(r for r in runs if r['goal']=='Delivery streak' and r['status']=='promoted')
            planned_build=next(r for r in chat_build.list_requests(copied_folder) if r['ref']==planned_run['proposal_ref'])['payload']['body']
            if len(planned_build['contracts'])!=1 or planned_build['build']['project_scope']['task_id']!='task-3':
                raise ValueError('The planned build did not use its existing approved project root')
            queued=[r for r in runs if r['status'] in ('scope_inactive','declined')]
            executed=[r for r in runs if r not in queued]
            if (task_calls!=['generate-1','verify-1']*2 or len(executed)!=4 or len(queued)!=2 or
                    {r['status'] for r in queued}!={'scope_inactive','declined'} or any(r['reports'] for r in queued) or
                    any(r['status']!='promoted' or not r['reports'][0]['qualified'] for r in executed[:2]) or
                    any(r['status']!='stopped' or r['reports'] for r in executed[2:])):
                raise ValueError('Sequential task execution, independent verifier or final promotion was not exercised')
            queue=findings.history(fixture,copied_folder)
            if (len(queue)!=1 or queue[0]['bug']['state']!='triaged' or not queue[0]['closure'] or
                    queue[0]['attempts']['attempts_started']!=3 or queue[0]['attempts']['status']!='ready' or
                    not queue[0]['attempts']['retry_approval_ref']):
                raise ValueError('Browser findings, verified closure, recurrence and owner escalation after non-reproducing stopped runs were not exercised')
            from ember_harness.contract_lock import verify as contract_lock
            locked=contract_lock(chat_build.harness(copied_folder).root)
            if not locked['ok']:
                raise ValueError('Browser finding contract-lock failed: '+str(locked['errors']))
            saved_workspace = workspace.status(folder)['latest']
            if not saved_workspace or 'apply' not in saved_workspace:
                raise ValueError('Workspace scan, setup diff and exact sandbox application were not exercised')
            if workspace_before != {p.name: sha256(p.read_bytes()).hexdigest() for p in workspace_source.iterdir()}:
                raise ValueError('Workspace onboarding changed source bytes')
            if 'SYNTHETIC secret: must never enter reports' in json.dumps(workspace.status(folder)):
                raise ValueError('Workspace scan disclosed secret contents')
            locked = contract_lock(workspace.authority(folder).root)
            if not locked['ok']:
                raise ValueError('Workspace contract-lock failed: ' + str(locked['errors']))
            fresh = App(fixture)
            if Path(fresh.resume(copied_folder.name)['build']['project']).parent != copy_parent:
                raise ValueError('The chosen project location was lost after restart')
            if fresh.snapshot()['project_settings']['parent'] != str(copy_parent):
                raise ValueError('New-project folder preference was lost after restart')
    except Exception as failure:
        error = str(failure)
    finally:
        for task_worker in task_workers:
            task_worker.join(timeout=30)
        http.shutdown()
        http.server_close()
        worker.join()
    unchanged = source_manifest() == before
    report = dict(passed=error is None and unchanged, error=error, source_unchanged=unchanged,
                  source_manifest=before, basis='Synthetic fixture decisions and real Chromium automation. No Muse calls or credit use.',
                  initial_version=first, checks='startup failure → targeted reviewed fix → compare an unapplied scoring regression → targeted proposal repair retaining visual improvements → passing comparison → approve → checked restore; independent preview state, history, isolation, keyboard/touch input, ZIP export and chosen project folder → reviewed Save as → persistent project scope → selected task → targeted scope-bound exact build → gameplay comparison → separate task acceptance → reload → separate amendment acknowledgement and approval → reviewed task coder/verifier with targeted edits → real frozen Chromium checks → retained independent report after reload → exact promotion and approval → separate task acceptance → recorded problem → hash-bound finding intake → targeted scoped fix → failing frozen baseline and passing candidate checks → independent report → exact apply → explicit closure → reload and contract-lock → remembered new-project folder → reviewed read-only workspace inventory → setup diff and conflicts → pending exact-action reload → verified create-only sandbox → source preservation and contract-lock. Native dialog selection is simulated.')
    if args.ui_only:report['checks']='Enter-to-send, Shift+Enter newlines, IME/modifier/repeat/duplicate-send guards, shared typography and SVG icon gallery, reduced motion, observed work status with current task and retained progress counters, Known assets in Project tools, desktop/tablet/mobile layouts, retained drafts and live preview state, isolated full-window play session, fullscreen and restart, and legacy server compatibility. Local chat transport checks are intercepted; no provider calls.'
    if args.playtest_fix_only:report['checks']='Notes-only fix in an approved project with no saved gameplay plan; separate investigation and code proposal; observed phase transitions and diagnosis; exact application; persistent receipt; idempotent retry; simulated browser speech, interim/final replacement, permission failure, text limits, session switching and unsupported-browser fallback; desktop/mobile layouts. No real microphone or transcription provider was used.'
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (output / 'REPORT.md').write_text('# Browser QA and restore rehearsal\n\n**' + ('PASS' if report['passed'] else 'FAIL') + '**\n\n' +
        report['basis'] + '\n\n' + report['checks'] + '\n\nSource unchanged: ' + str(unchanged) +
        ('\n\n' + error if error else '') + '\n', encoding='utf-8')
    print('Report: ' + str(output / 'REPORT.md'))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
