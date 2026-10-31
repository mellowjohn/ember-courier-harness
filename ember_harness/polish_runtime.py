"""Discover the host's optional Chromium tooling and bind it to a reviewed run."""
from hashlib import sha256
import os
from pathlib import Path
import shutil
import subprocess
import time

from .recovery import read_json

DRIVER = Path(__file__).with_name('polish_browser.js')


def file_digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def discover(root, *, fingerprints=True):
    bundle = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
    node = os.environ.get('EMBER_NODE') or shutil.which('node') or str(bundle / 'bin/node.exe')
    modules = [Path(os.environ['EMBER_PLAYWRIGHT_MODULE'])] if os.environ.get('EMBER_PLAYWRIGHT_MODULE') else [
        Path(root) / '.harness/browser-tools/node_modules/playwright', bundle / 'node_modules/playwright']
    module = next((p.resolve() for p in modules if (p / 'package.json').is_file()), None)
    browser = os.environ.get('EMBER_BROWSER_EXECUTABLE')
    if not browser:
        cache = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'ms-playwright'
        installed = list(cache.glob('chromium-*/chrome-win64/chrome.exe'))
        browser = str(max(installed, key=lambda p: int(p.parents[1].name.split('-')[-1]))) if installed else None
    if not Path(node).is_file() or module is None or not browser or not Path(browser).is_file():
        raise ValueError('Overnight polish needs Node, Playwright and Chromium. See docs/OVERNIGHT_POLISH.md for setup')
    paths = dict(node=str(Path(node).resolve()), module=str(module), browser=str(Path(browser).resolve()), driver=str(DRIVER))
    if not fingerprints:
        return paths
    return {**paths, 'hashes': {key: file_digest(paths[key]) for key in ('node', 'browser', 'driver')},
            'module_hash': file_digest(module / 'package.json')}


def validate(runtime):
    if (any(file_digest(runtime[key]) != runtime['hashes'][key] for key in ('node', 'browser', 'driver')) or
            file_digest(Path(runtime['module']) / 'package.json') != runtime['module_hash']):
        raise ValueError('Reviewed browser tooling changed; prepare a new polish run')


def inspect(runtime, source, output, *, check):
    validate(runtime)
    output = Path(output)
    report = output / 'report.json'
    if report.exists():
        return verified_report(source, output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('An interrupted browser capture needs inspection; completed candidates remain available')
    env = dict(os.environ, EMBER_PLAYWRIGHT_MODULE=runtime['module'], EMBER_BROWSER_EXECUTABLE=runtime['browser'])
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'browser.log').open('wb') as log:
        process = subprocess.Popen([runtime['node'], runtime['driver'], str(source), str(output)],
            env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        deadline = time.monotonic() + 55
        try:
            while process.poll() is None:
                check()
                if time.monotonic() > deadline:
                    raise ValueError('Browser inspection timed out')
                time.sleep(.2)
            if process.returncode:
                raise ValueError('Browser inspection failed; its local log was retained')
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
    return verified_report(source, output)


def verified_report(source, output):
    output = Path(output)
    data = read_json(output / 'report.json')
    if (not data.get('complete') or data.get('input_sha256') != file_digest(source) or
            {row.get('name') for row in data.get('viewports', [])} != {'desktop', 'mobile'} or len(data['viewports']) != 2):
        raise ValueError('Browser capture does not match its input')
    for row in data['viewports']:
        if row.get('name') not in ('desktop', 'mobile') or row.get('screenshot') != row['name'] + '.png':
            raise ValueError('Invalid browser capture path')
        for name, key in [(row['name'] + '.png', 'sha256'), (row['name'] + '-before.png', 'before_sha256')]:
            target = output / name
            if target.is_symlink() or file_digest(target) != row.get(key):
                raise ValueError('Browser screenshot evidence changed')
    return data
