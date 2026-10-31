"""Run the offline release checks and retain logs tied to the tested source bytes."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
import argparse

ROOT = Path(__file__).resolve().parents[1]
DEMOS = ('contract', 'amendment', 'staged_fix', 'round', 'attempt', 'intake',
         'reconciliation', 'reopening', 'muse_review', 'scope', 'asset', 'product')


def source_manifest():
    paths = [ROOT / 'pyproject.toml', ROOT / 'AGENTS.md', ROOT / '.agents/skills/repo-hygiene/SKILL.md']
    for folder in ('ember_harness', 'examples', 'tests', 'tools'):
        paths.extend(p for p in (ROOT / folder).rglob('*')
                     if p.suffix in ('.py', '.json', '.html', '.js') and '__pycache__' not in p.parts)
    return {p.relative_to(ROOT).as_posix(): sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def run_check(name, args, output, timeout=1200, *, require_tests=False, cwd=None):
    env = dict(os.environ)
    env.pop('PYTHONOPTIMIZE', None)  # Demo assertions are acceptance checks.
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    start = time.monotonic()
    log = output / (name + '.log')
    with log.open('w', encoding='utf-8') as stream:
        try:
            result = subprocess.run(args, cwd=ROOT if cwd is None else cwd, env=env, stdout=stream,
                                    stderr=subprocess.STDOUT, text=True, timeout=timeout)
            code, reason = result.returncode, None
        except subprocess.TimeoutExpired:
            code, reason = None, 'timeout'
        except OSError as error:
            code, reason = None, str(error)
    transcript = log.read_text(encoding='utf-8', errors='replace')
    if require_tests and not re.search(r'Ran [1-9]\d* tests? in ', transcript):
        reason = reason or 'No completed nonempty test suite found'
    return dict(name=name, passed=code == 0 and reason is None, returncode=code,
                reason=reason, seconds=round(time.monotonic() - start, 2),
                command=args, log=log.as_posix(),
                log_sha256=sha256(log.read_bytes()).hexdigest())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-agent-binary')
    parser.add_argument('--local-agent-model', default='qwen2.5-coder:7b')
    options = parser.parse_args(argv)
    output = ROOT / '.harness' / 'release-checks' / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    before = source_manifest()
    checks = [('tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'])]
    checks += [(name, [sys.executable, str(ROOT / 'examples' / (name + '_demo.py'))])
               for name in DEMOS]
    checks[-1][1].append('--fixture-approvals')
    if options.local_agent_binary:
        checks[-1][1].extend(['--local-agent-binary', options.local_agent_binary, '--local-agent-model', options.local_agent_model])
    rows = []
    for name, args in checks:
        print('Running ' + name, flush=True)
        rows.append(run_check(name, args, output, require_tests=name == 'tests'))
        print(('PASS ' if rows[-1]['passed'] else 'FAIL ') + name, flush=True)
        # Persist partial results if the run is interrupted later.
        (output / 'progress.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    after = source_manifest()
    passed = all(row['passed'] for row in rows) and before == after
    report = dict(passed=passed, completed_at=datetime.now(timezone.utc).isoformat(),
                  coverage='Fixture owner approvals and deterministic review. Includes manual PNG ingest and the integrated workflow. '
                           + ('Product fix uses real local model inference; ' if options.local_agent_binary else 'No model inference; ')
                           + 'no engine, broader asset production pipeline or submission validation.',
                  python=sys.version, source_unchanged=before == after,
                  source_manifest=before, checks=rows)
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    lines = ['# Offline release check', '', '**' + ('PASS' if passed else 'FAIL') + '**', '',
             report['coverage'], '', '| Check | Result | Seconds | Log |', '|---|---|---:|---|']
    lines += [f"| {r['name']} | {'PASS' if r['passed'] else 'FAIL'} | {r['seconds']} | [log](<{r['log']}>) |" for r in rows]
    lines += ['', 'Source unchanged during run: ' + str(before == after), '',
              'The JSON report records source and log hashes. This is local evidence, not an external attestation.']
    (output / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Report: ' + str(output / 'REPORT.md'), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
