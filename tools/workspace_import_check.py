"""Real browser source-import rehearsal; synthetic owner choices, no provider calls."""
from contextlib import redirect_stdout
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ember_harness import chat_build, polish_runtime, project_plan, workspace
from ember_harness.local_ui import App, server
from ember_harness.muse_chat import CreditLedger
from tools.browser_check import FILES as COUNTER_FILES, synthetic_provider_guard
from tools.release_check import source_manifest

FILES = COUNTER_FILES | {
    'index.html': COUNTER_FILES['index.html'].replace('<head>', '<head><meta name="viewport" content="width=device-width,initial-scale=1">'),
    'style.css': COUNTER_FILES['style.css']+'\nbutton{min-width:44px;min-height:44px;touch-action:manipulation}',
    'app.js': 'let score=0;const button=document.querySelector("button");'
              'const collect=()=>{button.textContent="Started";document.querySelector("#score").textContent=++score};'
              'button.addEventListener("click",e=>{if(e.pointerType!=="touch")collect()});'
              'button.addEventListener("pointerdown",e=>{if(e.pointerType==="touch"){e.preventDefault();collect()}});'
              'addEventListener("keydown",e=>{if(e.key==="ArrowRight")collect()});',
}


def main():
    runtime = polish_runtime.discover(ROOT, fingerprints=False)
    output = ROOT / '.harness/workspace-import-checks' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    before = source_manifest()
    root, source = output/'fixture', output/'existing-browser-project'
    (root/'examples').mkdir(parents=True); (root/'examples/product_demo.py').touch()
    source.mkdir()
    for name, content in FILES.items():
        (source/name).write_bytes(content.encode())
    (source/'.env').write_text('SYNTHETIC PRIVATE never copy or display', encoding='utf-8')
    git = source/'.git'; (git/'refs/heads').mkdir(parents=True); (git/'hooks').mkdir()
    (git/'HEAD').write_text('ref: refs/heads/main\n', encoding='utf-8')
    (git/'refs/heads/main').write_text('a'*40+'\n', encoding='utf-8')
    (git/'config').write_text('[include]\n path=/outside/never-read\n', encoding='utf-8')
    (git/'hooks/post-checkout').write_text('NEVER RUN this project hook', encoding='utf-8')
    source_before = {p.relative_to(source).as_posix():sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    app = App(root); app.start('SYNTHETIC existing browser import', chat_only=True)
    folder = app.sessions_dir/app.session['id']
    document = project_plan.starter(folder)
    document['scope']['features'] = ['Import and play the existing browser counter']
    http = server(app); worker = threading.Thread(target=http.serve_forever, daemon=True); worker.start()
    error = None
    try:
        env = dict(os.environ, EMBER_PLAYWRIGHT_MODULE=runtime['module'], EMBER_BROWSER_EXECUTABLE=runtime['browser'],
                   EMBER_BROWSER_URL=f'http://127.0.0.1:{http.server_port}/', EMBER_BROWSER_TOKEN=app.token,
                   EMBER_BROWSER_OUTPUT=str(output), EMBER_WORKSPACE_SOURCE=str(source),
                   EMBER_IMPORT_PLAN_DOCUMENT=json.dumps(document))
        with synthetic_provider_guard(), redirect_stdout(io.StringIO()):
            with (output/'browser.log').open('w', encoding='utf-8') as log:
                result = subprocess.run([runtime['node'], str(ROOT/'tools/workspace_import_check.js')], cwd=ROOT,
                                        env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300)
            if result.returncode:
                raise ValueError('Browser source-import rehearsal failed; see browser.log')
        saved = workspace.status(folder)['latest']
        imported = workspace.imported_files(folder, saved['run_id'])
        if imported != FILES:
            raise ValueError('Retained import bytes differ from original fixture')
        current = chat_build.context(root, folder)
        if {row['path']:row['content'] for row in current['files']} != FILES:
            raise ValueError('Final current game differs from the exact imported snapshot')
        if len(chat_build.status(root,folder)['completed']) != 1:
            raise ValueError('Source-copy approval bypassed the single later exact-build review')
        if not project_plan.status(root,folder)['tasks'][0]['acceptance']:
            raise ValueError('Separate task outcome acceptance was not exercised')
        if source_before != {p.relative_to(source).as_posix():sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}:
            raise ValueError('Import or adoption changed original source bytes')
        if CreditLedger(root).read()['requests']:
            raise ValueError('Synthetic rehearsal unexpectedly reserved provider credits')
        if 'SYNTHETIC PRIVATE' in json.dumps(app.snapshot()):
            raise ValueError('Secret source content entered the workspace state')
        handoff = output/'imported-project-handoff.zip'
        with zipfile.ZipFile(handoff) as archive:
            with zipfile.ZipFile(io.BytesIO(archive.read('game.zip'))) as game:
                if any(game.read(name) != content.encode() for name,content in FILES.items()):
                    raise ValueError('Handoff game bytes differ from the imported game')
    except Exception as failure:
        error = str(failure)
    finally:
        http.shutdown(); http.server_close(); worker.join(timeout=5)
    unchanged = before == source_manifest()
    report = dict(passed=error is None and unchanged, error=error, source_unchanged=unchanged, source_manifest=before,
                  checks='Read-only scan and passive Git metadata → source-inspection contract → full import contents → copy contract → exact create-only action → reload → separate project scope → exact game proposal → desktop/mouse/keyboard and mobile touch → exact apply → separate task acceptance → handoff ZIP. Original source and secrets remain unchanged.',
                  basis='Synthetic owner decisions; real Chromium inputs, copies, byte checks and handoff. Provider reservations are forbidden; no model inference or credits.')
    (output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (output/'REPORT.md').write_text('# Existing browser project import rehearsal\n\n'+('PASS' if report['passed'] else 'FAIL')+'\n\n'+report['basis']+'\n\n'+report['checks']+'\n\nSource unchanged: '+str(unchanged)+('\n\n'+error if error else '')+'\n', encoding='utf-8')
    print('Report: '+str(output/'REPORT.md'))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
