"""Build/install a wheel offline, then reuse release checks without local package source."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.release_check import source_manifest, run_check


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheelhouse', required=True, help='local wheels for declared runtime and build dependencies')
    args = parser.parse_args(argv)
    wheelhouse = Path(args.wheelhouse).resolve()
    if not wheelhouse.is_dir() or not any(wheelhouse.glob('*.whl')):
        parser.error('wheelhouse must contain dependency wheels')
    output = ROOT / '.harness/clean-installs' / uuid.uuid4().hex[:8]
    output.mkdir(parents=True)
    build, validation, environment = [output / name for name in ('build-source', 'validation', 'venv')]
    before = source_manifest()
    # Copy only explicit source files; never include prior artifacts, Git state or installed packages.
    for name in before:
        target = build if name.startswith('ember_harness/') else validation
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
    shutil.copyfile(ROOT / 'pyproject.toml', build / 'pyproject.toml')
    if (validation / 'ember_harness').exists():
        raise ValueError('validation harness must not contain package source')
    rows = []
    nested = None
    error = None
    python = environment / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')

    def check(name, command, *, tests=False):
        print('Running ' + name, flush=True)
        row = run_check(name, list(map(str, command)), output, require_tests=tests, cwd=validation)
        rows.append(row)
        (output / 'progress.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
        if not row['passed']:
            raise RuntimeError(name + ' failed; see ' + row['log'])
        print('PASS ' + name, flush=True)
        return row

    try:
        check('create-environment', [sys.executable, '-I', '-m', 'venv', environment])
        wheels = output / 'wheels'
        check('build-wheel', [python, '-I', '-m', 'pip', 'wheel', '--no-index', '--find-links', wheelhouse,
                             '--no-deps', '--wheel-dir', wheels, build])
        wheel = next(wheels.glob('ember_courier_harness-*.whl'))
        check('install-wheel', [python, '-I', '-m', 'pip', 'install', '--no-index', '--find-links', wheelhouse, wheel])
        check('dependency-check', [python, '-I', '-m', 'pip', 'check'])
        probe = """import importlib.resources as r, json, pathlib, site, sys
import ember_harness, ember_harness.assets, ember_harness.core
prefix = pathlib.Path(sys.prefix).resolve()
modules = [ember_harness, ember_harness.assets, ember_harness.core]
assert sys.prefix != sys.base_prefix and not site.ENABLE_USER_SITE
assert all(pathlib.Path(m.__file__).resolve().is_relative_to(prefix) for m in modules)
for name in ('contract.schema.json', 'finding.schema.json', 'tools.json'):
    json.loads(r.files('ember_harness').joinpath('schema/' + name).read_text())
print(json.dumps({'prefix': str(prefix), 'user_site_enabled': site.ENABLE_USER_SITE,
                  'module_paths': [m.__file__ for m in modules], 'schemas': 'verified'}))
"""
        check('installed-imports-and-schemas', [python, '-I', '-c', probe])
        cli = environment / ('Scripts/contract-lock.exe' if sys.platform == 'win32' else 'bin/contract-lock')
        check('installed-entry-point', [cli, '--help'])
        check('full-release', [python, '-I', validation / 'tools/release_check.py'])
        reports = list((validation / '.harness/release-checks').glob('*/report.json'))
        if len(reports) != 1:
            raise ValueError('exactly one nested release report required')
        nested = json.loads(reports[0].read_text(encoding='utf-8'))
        if not nested['passed']:
            raise ValueError('nested release check failed')
        check('installed-versions', [python, '-I', '-m', 'pip', 'freeze', '--all'])
    except Exception as failure:
        error = str(failure)
    unchanged = before == source_manifest()
    wheel_files = list((output / 'wheels').glob('*.whl'))
    report = dict(passed=error is None and unchanged, error=error,
                  completed_at=datetime.now(timezone.utc).isoformat(), source_unchanged=unchanged,
                  source_manifest=before, checks=rows, release=nested,
                  wheels={p.name: sha256(p.read_bytes()).hexdigest() for p in wheel_files},
                  dependencies={p.name: sha256(p.read_bytes()).hexdigest() for p in wheelhouse.glob('*.whl')},
                  coverage='Fresh virtual environment, no shared packages or editable install; source-free '
                           'validation harness uses the installed wheel. Offline fixture workflows, not live AI or engine tests.')
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    lines = ['# Clean installation and end-to-end verification', '',
             '**' + ('PASS' if report['passed'] else 'FAIL') + '**', '', report['coverage'], '',
             '| Check | Result | Log |', '|---|---|---|']
    lines += [f"| {row['name']} | {'PASS' if row['passed'] else 'FAIL'} | [log](<{row['log']}>) |" for row in rows]
    if error:
        lines += ['', 'Failure: ' + error]
    if nested:
        lines += ['', f"Nested release checks: {len(nested['checks'])}; all passed: {nested['passed']}."]
    lines += ['', 'Source unchanged: ' + str(unchanged), '',
              'The JSON report retains source, wheel and dependency hashes. Logs and all generated artifacts stay in this ignored run directory.']
    (output / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Report: ' + str(output / 'REPORT.md'), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
