"""Rehearse the Windows launcher against an installed wheel, without live model calls.

Run with the fresh virtual environment created by clean_install_check.py.
The desktop workspace contains examples and the real launcher, but no package source.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.release_check import source_manifest


def request(base, token, route, body=None):
    headers = {'X-Ember-Token': token, 'Content-Type': 'application/json'}
    data = None if body is None else json.dumps(body).encode()
    with build_opener(ProxyHandler({})).open(Request(base + route, data=data, headers=headers), timeout=30) as response:
        return json.load(response)


def require_denied(base, token):
    try:
        request(base, token, '/api/state')
    except HTTPError as error:
        if error.code == 403:
            return
        raise
    raise ValueError('A missing or retired private-link token was accepted')


@contextmanager
def launched(workspace, output, name):
    env = dict(os.environ, VIRTUAL_ENV=sys.prefix, EMBER_NO_PAUSE='1', EMBER_NO_BROWSER='1', PYTHONNOUSERSITE='1')
    for key in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONOPTIMIZE'):
        env.pop(key, None)
    process = subprocess.Popen('cmd.exe /d /c call "Start Ember.cmd"', cwd=workspace, env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
    lines, messages = [], queue.Queue()

    def collect():
        for line in process.stdout:
            lines.append(re.sub(r'(http://127\.0\.0\.1:\d+/#)\S+', r'\1[private]', line))
            match = re.search(r'Ember app: (http://127\.0\.0\.1:\d+/)#([\w-]+)', line)
            if match:
                messages.put(match.groups())

    reader = threading.Thread(target=collect, daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + 45
        while True:
            try:
                base, token = messages.get(timeout=.2)
                break
            except queue.Empty:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise ValueError('The Windows launcher did not print a private launch link; see ' + name + '.log')
        yield base, token
    finally:
        # This PID belongs to this rehearsal. No session worker is started here.
        if process.poll() is None:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW, check=True)
        process.wait(timeout=15)
        reader.join(timeout=5)
        process.stdout.close()
        (output / (name + '.log')).write_text(''.join(lines), encoding='utf-8')


def main():
    if os.name != 'nt' or sys.prefix == sys.base_prefix:
        raise ValueError('Run this Windows check with the clean-installed virtual environment')
    output = ROOT / '.harness/desktop-launch-checks' / uuid.uuid4().hex[:8]
    workspace = output / 'Desktop workspace'
    workspace.mkdir(parents=True)
    before = source_manifest()
    shutil.copyfile(ROOT / 'Start Ember.cmd', workspace / 'Start Ember.cmd')
    shutil.copytree(ROOT / 'examples', workspace / 'examples', ignore=shutil.ignore_patterns('__pycache__'))
    ledger = workspace / '.harness/muse-credits.json'
    ledger.parent.mkdir()
    ledger.write_text(json.dumps(dict(version=1, limit_micro_usd=0, requests={})), encoding='utf-8')
    original_ledger = ledger.read_bytes()
    project_parent = workspace / 'Saved projects'
    project_parent.mkdir()
    checks, error, runtime, imports = [], None, None, None

    def browser(base, token, phase):
        env = dict(os.environ, EMBER_PLAYWRIGHT_MODULE=runtime['module'],
            EMBER_BROWSER_EXECUTABLE=runtime['browser'], EMBER_BROWSER_URL=base,
            EMBER_BROWSER_TOKEN=token, EMBER_BROWSER_OUTPUT=str(output),
            EMBER_PROJECT_PARENT=str(project_parent), EMBER_LAUNCH_PHASE=phase)
        result = subprocess.run([runtime['node'], str(ROOT / 'tools/desktop_launch_check.js')],
            env=env, cwd=workspace, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW)
        (output / (phase + '-browser.log')).write_text(result.stdout.replace(token, '[private]'), encoding='utf-8')
        if result.returncode:
            raise ValueError('Desktop browser ' + phase + ' failed; see its browser log')

    try:
        # -I excludes both the checkout and user-site/editable import paths.
        probe = subprocess.run([sys.executable, '-I', '-c',
            'import ember_harness, json, pathlib, sys; '
            'p=pathlib.Path(ember_harness.__file__).resolve(); '
            'assert p.is_relative_to(pathlib.Path(sys.prefix).resolve()); '
            'print(json.dumps(dict(module=str(p), prefix=sys.prefix)))'],
            cwd=workspace, capture_output=True, text=True, timeout=30, check=True,
            creationflags=subprocess.CREATE_NO_WINDOW)
        imports = json.loads(probe.stdout)
        from ember_harness.polish_runtime import discover
        runtime = discover(ROOT)
        checks.append('Installed package imports from the fresh virtual environment; no desktop package source')
        with launched(workspace, output, 'first-launch') as (base, token):
            require_denied(base, '')
            state = request(base, token, '/api/state')
            if state['session'] is not None or state['credit_budget']['limit_usd'] != 0:
                raise ValueError('The initial session or zero-credit display is incorrect')
            browser(base, token, 'create')
            state = request(base, token, '/api/state')
            session_id = state['session']['id']
            if state['session']['name'] != 'Desktop launch rehearsal' or state['project_brief']['fields']['goal'] != 'Original offline courier game':
                raise ValueError('The browser did not save its session and brief')
            checks.append('Real launcher, private link, desktop/mobile UI, saved session, brief and project location')
        with launched(workspace, output, 'second-launch') as (base, new_token):
            if new_token == token:
                raise ValueError('The restarted host reused its private link')
            require_denied(base, token)
            browser(base, new_token, 'resume')
            state = request(base, new_token, '/api/state')
            if state['session']['id'] != session_id or state['project_brief']['fields']['goal'] != 'Original offline courier game':
                raise ValueError('Restart did not retain the exact session and brief')
            # Exercise the actual HTTP/chat/ledger path. A zero ceiling denies before dispatch.
            if state['models']['muse']:
                try:
                    request(base, new_token, '/api/chat', dict(text='Rehearsal: this request must be denied by the zero-credit budget', id='desktop-budget-check'))
                except HTTPError as blocked:
                    if blocked.code != 400 or 'free-credit budget cannot cover' not in blocked.read().decode():
                        raise
                else:
                    raise ValueError('The zero-credit request was not refused')
                checks.append('Real installed Muse request denied by zero-credit ceiling before model dispatch')
            else:
                checks.append('Muse is unavailable; dispatch denial remains covered by the offline suite')
            checks.append('Restart, fresh private link, retired-token refusal and exact saved-session recovery')
        if ledger.read_bytes() != original_ledger or list(workspace.glob('.harness/ui/sessions/*/muse-captures/*.json')):
            raise ValueError('The no-credit rehearsal altered its ledger or captured a model reply')
        checks.append('Zero-credit ledger unchanged; no model replies or approval decisions created')
    except Exception as failure:
        error = str(failure)
    unchanged = before == source_manifest()
    report = dict(passed=error is None and unchanged, error=error, checks=checks,
        completed_at=datetime.now(timezone.utc).isoformat(), source_unchanged=unchanged,
        source_manifest=before, installed=imports, runtime=runtime,
        evidence={p.name: sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()},
        coverage='Real Windows launcher and Chromium against a clean-installed wheel. Synthetic session text; '
                 'no model output, contract approvals or human gameplay acceptance. Current source snapshot, not a clean Git checkout.')
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (output / 'REPORT.md').write_text('# Installed desktop launch rehearsal\n\n**' +
        ('PASS' if report['passed'] else 'FAIL') + '**\n\n' + report['coverage'] + '\n\n' +
        '\n'.join('- ' + check for check in checks) + '\n\nSource unchanged: ' + str(unchanged) +
        ('\n\nFailure: ' + error if error else '') + '\n', encoding='utf-8')
    print('Report: ' + str(output / 'REPORT.md'), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
