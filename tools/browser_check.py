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
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ember_harness import chat_build, project_versions
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
    app.start('SYNTHETIC browser QA rehearsal', chat_only=True)
    folder = app.sessions_dir / app.session['id']
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
    fixed = {**FILES, 'app.js': FILES['app.js'] + '\ndocument.body.dataset.revision="fixed";'}
    reply = dict(response=json.dumps(dict(message='SYNTHETIC fixture fix: review before application.',
                 build=dict(title='Synthetic reviewed fix', summary='Remove the known fixture startup failure',
                            files=[dict(path=name, content=content) for name, content in fixed.items()]))))
    http = server(app)
    worker = threading.Thread(target=http.serve_forever, daemon=True)
    worker.start()
    env = dict(os.environ, EMBER_BROWSER_URL=f'http://127.0.0.1:{http.server_port}/',
               EMBER_BROWSER_TOKEN=app.token, EMBER_BROWSER_OUTPUT=str(output))
    if args.playwright_module:
        env['EMBER_PLAYWRIGHT_MODULE'] = str(Path(args.playwright_module).resolve())
    if args.browser_executable:
        env['EMBER_BROWSER_EXECUTABLE'] = str(Path(args.browser_executable).resolve())
    error = None
    try:
        with patch('ember_harness.session_chat.run_muse', return_value=reply), redirect_stdout(io.StringIO()):
            with (output / 'browser.log').open('w', encoding='utf-8') as stream:
                result = subprocess.run([args.node, str(ROOT / 'tools/browser_check.js')], env=env,
                                        cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=150)
            if result.returncode:
                raise ValueError('Browser rehearsal failed; see browser.log')
        versions = project_versions.history(folder)
        if len(versions) != 4 or project_versions.snapshot(fixture, folder, versions[-1]['request_ref'])['files'] != FILES:
            raise ValueError('Restore did not preserve all four versions and exact original files')
        reports = app.snapshot()['build']['smoke_checks']
        if [r['outcome'] for r in reports] != ['issues_observed', 'no_errors_observed', 'no_errors_observed']:
            raise ValueError('Browser reports did not capture failure, reviewed fix and restoration')
    except Exception as failure:
        error = str(failure)
    finally:
        http.shutdown()
        http.server_close()
        worker.join()
    unchanged = source_manifest() == before
    report = dict(passed=error is None and unchanged, error=error, source_unchanged=unchanged,
                  source_manifest=before, basis='Synthetic fixture decisions and real Chromium automation. No Muse calls or credit use.',
                  initial_version=first, checks='startup failure → report → reviewed fix → clean smoke → reviewed restore → clean smoke; history, preview isolation, keyboard/button input and ZIP export')
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (output / 'REPORT.md').write_text('# Browser QA and restore rehearsal\n\n**' + ('PASS' if report['passed'] else 'FAIL') + '**\n\n' +
        report['basis'] + '\n\n' + report['checks'] + '\n\nSource unchanged: ' + str(unchanged) +
        ('\n\n' + error if error else '') + '\n', encoding='utf-8')
    print('Report: ' + str(output / 'REPORT.md'))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
