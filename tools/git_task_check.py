"""Real private Git + Chromium repair rehearsal; owner decisions are fixtures."""
from contextlib import redirect_stdout
import argparse
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ember_harness import chat_build, gameplay, git_task, polish_runtime, project_plan
from ember_harness.local_ui import App, server
from ember_harness.muse_chat import CreditLedger
from tools.browser_check import synthetic_provider_guard
from tools.release_check import source_manifest


FILES = {
    'index.html': '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="style.css"></head><body><main><h1>Parcel counter</h1><p>Press Space or collect a parcel. Each delivery earns two points.</p><p>Score: <span id="score">0</span></p><button id="collect">Collect parcel</button><button id="reset">Restart</button></main><script src="app.js"></script></body></html>',
    'style.css': '*{box-sizing:border-box}body{margin:0;padding:24px;min-height:100vh;background:#182034;color:#fff4d3;font:18px system-ui;display:grid;place-items:center}main{max-width:38rem;width:100%}button{font:inherit;padding:16px;margin:8px 8px 8px 0;background:#ffb96c;border:0;border-radius:12px;color:#221a29}',
    'app.js': 'let score=0;const hud=document.querySelector("#score");function collect(){score+=1;hud.textContent=score}document.querySelector("#collect").onclick=collect;document.querySelector("#reset").onclick=()=>{score=0;hud.textContent=score};addEventListener("keydown",e=>{if(e.code==="Space"&&!e.repeat){e.preventDefault();collect()}});',
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ui', action='store_true', help='Operate the real permission card, candidate and exact approval controls with Chromium')
    parser.add_argument('--form', action='store_true', help='Use the exact edit form instead of a pending source proposal; requires --ui')
    args = parser.parse_args(argv)
    if args.form and not args.ui:
        parser.error('--form requires --ui')
    output = ROOT / '.harness/git-task-checks' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
    output.mkdir(parents=True)
    before = source_manifest()
    root = Path(tempfile.mkdtemp(prefix='g', dir=ROOT / '.harness'))
    (root / 'examples').mkdir(parents=True); (root / 'examples/product_demo.py').touch()
    error = None
    result = None
    try:
        with synthetic_provider_guard(), redirect_stdout(io.StringIO()):
            app = App(root); app.start('SYNTHETIC Git browser repair rehearsal', chat_only=True)
            folder = app.sessions_dir / app.session['id']
            initial = chat_build.propose_build(root, folder, 'git-initial-fixture', 'SYNTHETIC initial game',
                dict(title='Original parcel counter', summary='SYNTHETIC starting source', files=[dict(path=k, content=v) for k, v in FILES.items()]))
            app.respond(initial, 'approve', 'SYNTHETIC initial game setup')
            document = project_plan.starter(folder)
            document['scope']['features'] = ['Repair two-point parcel scoring without changing keyboard, touch or restart controls']
            scope = project_plan.prepare(root, folder, document, None)['request_ref']
            app.respond(scope, 'approve', 'SYNTHETIC reviewed project ceiling')
            checks = dict(title='Two-point delivery and restart', scenarios=[
                dict(name='Keyboard delivery and reset', viewport='desktop', coverage=['success', 'reset'], steps=[
                    dict(action='press', key='Space'), dict(action='text', selector='#score', value='2'),
                    dict(action='click', selector='#reset'), dict(action='text', selector='#score', value='0')]),
                dict(name='Touch delivery and reset', viewport='mobile', coverage=['success', 'reset'], steps=[
                    dict(action='tap', selector='#collect'), dict(action='text', selector='#score', value='2'),
                    dict(action='tap', selector='#reset'), dict(action='text', selector='#score', value='0')])])
            saved = gameplay.save(folder, checks, 0)
            candidate = {**FILES, 'app.js': FILES['app.js'].replace('score+=1', 'score+=2')}
            current = chat_build.context(root, folder)
            proposal = None if args.form else chat_build.propose_build(root, folder, 'git-repair-fixture', 'SYNTHETIC exact repair proposal',
                dict(title='Two-point parcel delivery', summary='Repair reward amount and preserve controls', files=[dict(path=k, content=v) for k, v in candidate.items()]),
                expected_before=current['sha256'])
            if args.ui:
                runtime = polish_runtime.discover(root)
                http = server(app); thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
                try:
                    env = dict(os.environ, EMBER_PLAYWRIGHT_MODULE=runtime['module'], EMBER_BROWSER_EXECUTABLE=runtime['browser'],
                        EMBER_BROWSER_URL=f'http://127.0.0.1:{http.server_port}/', EMBER_BROWSER_TOKEN=app.token, EMBER_BROWSER_OUTPUT=str(output),
                        EMBER_GIT_FORM='1' if args.form else '0')
                    with (output / 'browser.log').open('w', encoding='utf-8') as log:
                        completed = subprocess.run([runtime['node'], str(ROOT / 'tools/git_task_ui_check.js')], cwd=ROOT, env=env,
                            stdout=log, stderr=subprocess.STDOUT, timeout=240)
                    transcript = (output / 'browser.log').read_text(encoding='utf-8').replace(app.token, '[private]')
                    (output / 'browser.log').write_text(transcript, encoding='utf-8')
                    if completed.returncode:
                        raise ValueError('Git UI rehearsal failed; see browser.log')
                finally:
                    http.shutdown(); http.server_close(); thread.join(timeout=5)
                run = git_task.history(root, folder)[-1]['id']
                work = git_task.run_folder(folder, run)
            else:
                prepared = git_task.prepare(root, folder, candidate_files=candidate, origin=dict(proposal_ref=proposal), expected_manifest=current['manifest'])
                run = prepared['id']
                work = git_task.run_folder(folder, run)
                assert not (work / 'baseline/.git').exists()
                try:
                    git_task.Worker(root, folder, run).run()
                except ValueError as denied:
                    assert 'Approve exact' in str(denied)
                else:
                    raise AssertionError('Unapproved Git execution was accepted')
                git_task.respond(root, folder, run, 'approve', 'SYNTHETIC exact local Git worker/verifier contracts')
                git_task.Worker(root, folder, run).run()
            row = git_task.history(root, folder)[-1]
            assert row['status'] == ('promoted' if args.ui else 'ready_review'), row.get('error')
            report = row['report']
            assert report['qualified'] and report['before']['gameplay']['outcome'] == 'failed'
            assert report['after']['gameplay']['outcome'] == 'passed'
            assert report['gameplay_plan_sha256'] == saved['sha256']
            assert report['author'] != report['reviewer']
            if not args.ui:
                assert chat_build.context(root, folder)['manifest'] == current['manifest']
                assert git_task.promote(root, folder, run)['request_ref'] == proposal
                assert not chat_build.list_requests(folder)[-1]['decision']
            first_zip, _ = git_task.export(folder, run)
            assert first_zip == git_task.export(folder, run)[0]
            (output / 'verified-repair.zip').write_bytes(first_zip)
            capture = work / 'captures/0/output/mobile.png'
            raw = capture.read_bytes(); capture.write_bytes(b'SYNTHETIC tampered image')
            try:
                git_task.completed_report(folder, run)
            except ValueError:
                pass
            else:
                raise AssertionError('Changed baseline screenshot was accepted')
            capture.write_bytes(raw)
            if not args.ui:
                app.respond(proposal, 'approve', 'SYNTHETIC final exact game approval; no task acceptance')
            assert chat_build.context(root, folder)['manifest'] == report['candidate_manifest']
            assert project_plan.status(root, folder)['tasks'][0]['state'] == 'applied_needs_review'
            assert CreditLedger(root).summary()['reserved_usd'] == 0
            assert CreditLedger(root).summary()['estimated_spent_usd'] == 0
            result = dict(base=report['base'], head=report['head'], before=report['before']['gameplay'], after=report['after']['gameplay'],
                contracts_distinct=True, original_source_preserved_until_exact_approval=True, human_task_acceptance_pending=True,
                deterministic_export=True, changed_capture_refused=True, real_ui_controls=args.ui, exact_edit_form=args.form,
                extra_attempt_ui_basis='Synthetic three-finished-attempt render and intercepted click; actual allowance API tested separately' if args.ui else None,
                existing_proposal_bridge=not args.form, session=str(folder), report=str(work / 'report.json'))
    except Exception as failure:
        error = str(failure)
    unchanged = source_manifest() == before
    record = dict(passed=error is None and unchanged, error=error, source_unchanged=unchanged, source_manifest=before, result=result,
        basis='Real isolated local Git commits, clean named verification copies and Chromium keyboard/touch/reset assertions. '
              'Owner decisions are synthetic; no model calls, credits, source repository writes, canonical bug closure or human quality acceptance.')
    (output / 'report.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    (output / 'REPORT.md').write_text('# Git browser repair rehearsal\n\n' + ('PASS' if record['passed'] else 'FAIL') + '\n\n' + record['basis'] + '\n\nSource unchanged: ' + str(unchanged) + ('\n\n' + error if error else '') + '\n', encoding='utf-8')
    print(output / 'REPORT.md')
    return 0 if record['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
