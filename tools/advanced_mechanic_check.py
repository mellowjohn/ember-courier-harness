"""Real-browser advanced recipe rehearsal; fixture owner choices, no live AI."""
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
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ember_harness import chat_build, gameplay, polish_runtime, project_plan, project_versions
from ember_harness.local_ui import App, server
from tools.browser_check import synthetic_provider_guard
from tools.release_check import source_manifest


def main():
    output = ROOT / '.harness/advanced-mechanic-checks' / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    before = source_manifest()
    runtime = polish_runtime.discover(ROOT, fingerprints=False)
    fixture = output / 'fixture'
    (fixture / 'examples').mkdir(parents=True); (fixture / 'examples/product_demo.py').touch()
    app = App(fixture); app.start('SYNTHETIC advanced Lantern Trail rehearsal', chat_only=True)
    folder = app.sessions_dir / app.session['id']
    document = project_plan.starter(folder)
    document['scope'].update(game_concept='Original Lantern Trail advanced reference platformer',
        core_loop='Move, jump, avoid a hazard and sentry, reach the light and restart.',
        features=['Tune camera deadzone and easing', 'Tune hit stop and invincibility',
                  'Tune enemy patrol, chase and attack', 'Reproduce a seeded reachable level'],
        out_of_scope=['Network', 'Generated artwork', 'Native engine changes', 'Publishing'],
        done_criteria=['Review each resolved recipe and exact source',
                       'Fixed-step observations, keyboard and touch checks pass',
                       'Johnathan plays the result and separately accepts the task'])
    with redirect_stdout(io.StringIO()):
        project_plan.prepare(fixture, folder, document, None)
    http = server(app); host = threading.Thread(target=http.serve_forever, daemon=True); host.start()
    error = None
    try:
        env = dict(os.environ, EMBER_PLAYWRIGHT_MODULE=runtime['module'],
            EMBER_BROWSER_EXECUTABLE=runtime['browser'],
            EMBER_BROWSER_URL=f'http://127.0.0.1:{http.server_port}/',
            EMBER_BROWSER_TOKEN=app.token, EMBER_BROWSER_OUTPUT=str(output))
        with synthetic_provider_guard(), patch('ember_harness.muse_chat.installed_binary', return_value=None), \
                patch('ember_harness.task_run.installed_binary', return_value=None), redirect_stdout(io.StringIO()):
            with (output / 'browser.log').open('w', encoding='utf-8') as log:
                result = subprocess.run([runtime['node'], str(ROOT / 'tools/advanced_mechanic_check.js')],
                    cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=900)
            if result.returncode:
                raise ValueError('Advanced recipe browser rehearsal failed; see browser.log')
        versions = project_versions.history(folder)
        if len(versions) != 8:
            raise ValueError('The legacy reference, reviewed upgrade, four recipes and two restores must retain eight versions')
        snapshots = [project_versions.snapshot(fixture, folder, row['request_ref']) for row in versions]
        if snapshots[0]['mechanics']['profile'] != 'ember-platformer-v1':
            raise ValueError('The original reference was not retained as an exact historical version')
        if any(row['mechanics']['profile'] != 'ember-platformer-v2' for row in snapshots[1:]):
            raise ValueError('A reviewed advanced version lost its canonical source profile')
        if snapshots[2]['files'] != snapshots[6]['files'] or snapshots[5]['files'] != snapshots[7]['files']:
            raise ValueError('Forward restoration did not preserve exact advanced source bytes')
        current = chat_build.context(fixture, folder)
        settings = current['mechanics']['settings']
        if settings['level_seed'] != 404 or settings['level_sections'] != 12 or settings['invincibility_ms'] != 750:
            raise ValueError('The reviewed seed, generator or protection settings were lost')
        comparisons = gameplay.proposal_reports(folder)
        if len(comparisons) != 8 or sum(row['outcome'] == 'passed' for row in comparisons) != 7:
            raise ValueError('All four recipes, the rejected ineffective candidate and both restores need matching evidence')
        rejected = [row for row in comparisons if row['outcome'] == 'checks_failed']
        if len(rejected) != 1:
            raise ValueError('The ineffective protection proposal must fail while retaining its exact review')
        request = next(row for row in chat_build.list_requests(folder) if row['ref'] == rejected[0]['request_ref'])
        if request['decision']['choice'] != 'decline':
            raise ValueError('The failed candidate was not separately discarded')
        if sum(any(value['change'] == 'fixed' for value in row['comparison']) for row in comparisons) < 4:
            raise ValueError('Each new recipe must retain a formerly failing required observation')
        camera = next(row for row in comparisons if row['request_ref'] == versions[2]['request_ref'])
        before_level = camera['mechanics']['before']['observations']['checks'][-1]['observed']
        after_level = camera['mechanics']['proposed']['observations']['checks'][-1]['observed']
        if before_level != after_level:
            raise ValueError('The camera comparison must preserve the identical generated route and seed')
        for source in folder.glob('proposal-checks/*/*/input.json'):
            observed = polish_runtime.verified_report(source, source.parent / 'output')
            if not observed.get('mechanics'):
                raise ValueError('A supported reference comparison omitted raw fixed-step observations')
        with zipfile.ZipFile(output / 'game.zip') as archive:
            if json.loads(archive.read('ember-build.json'))['mechanics'] != snapshots[5]['mechanics']:
                raise ValueError('Game export lost the reviewed recipe and seed metadata')
        with zipfile.ZipFile(output / 'handoff.zip') as archive:
            handoff = json.loads(archive.read('project-report.json'))
            if handoff['mechanics'] != current['mechanics'] or not handoff['project_plan']['tasks'][0]['accepted']:
                raise ValueError('Handoff lost the exact current recipes or separate fixture outcome acceptance')
        if (fixture / '.harness/muse-credits.json').exists():
            raise ValueError('The synthetic advanced rehearsal must not reserve or spend Muse credits')
    except Exception as failure:
        error = str(failure)
    finally:
        http.shutdown(); http.server_close(); host.join(timeout=5)
    unchanged = source_manifest() == before
    record = dict(passed=error is None and unchanged, error=error, source_unchanged=unchanged,
        source_manifest=before,
        basis='Real Chromium UI, keyboard/touch/pause/reduced-motion input and fixed-step observations. Owner choices are synthetic fixtures; no live Muse calls or credits.',
        checks='Approved complete scope → retained legacy reference → reviewed advanced upgrade → four independently tuned recipes with failing before observations → ineffective protection rejected → keyboard/touch/pause/blur/reduced-motion → stable seeded restart/reload → ZIP → checked forward restores → separate synthetic outcome acceptance → handoff',
        human_playtest='pending; synthetic owner choices do not establish Johnathan’s comfort, impact-feel or gameplay judgment')
    (output / 'report.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    (output / 'REPORT.md').write_text('# Advanced mechanic product rehearsal\n\n' +
        ('PASS' if record['passed'] else 'FAIL') + '\n\n' + record['basis'] + '\n\n' + record['checks'] +
        '\n\nSource unchanged: ' + str(unchanged) + ('\n\n' + error if error else '') + '\n', encoding='utf-8')
    print(output / 'REPORT.md')
    return 0 if record['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
