"""Rehearse reference recipes through the real UI; synthetic owner choices, no AI."""
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
from ember_harness import chat_build, gameplay, mechanic_recipes, polish_runtime, project_plan, project_versions
from ember_harness.local_ui import App, server
from tools.browser_check import synthetic_provider_guard
from tools.release_check import source_manifest


def main():
    output = ROOT / '.harness/mechanic-checks' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    runtime = polish_runtime.discover(ROOT, fingerprints=False)
    before = source_manifest()
    fixture = output / 'fixture'; (fixture / 'examples').mkdir(parents=True); (fixture / 'examples/product_demo.py').touch()
    app = App(fixture); app.start('SYNTHETIC Lantern Trail recipe rehearsal', chat_only=True)
    folder = app.sessions_dir / app.session['id']
    document = project_plan.starter(folder)
    document['scope'].update(game_concept='Original Lantern Trail reference platformer',
        core_loop='Move, jump across a gap, reach the lantern and restart.', features=['Tune movement and jumping'],
        out_of_scope=['Network', 'Generated artwork', 'Engine changes', 'Publishing'],
        done_criteria=['Review resolved recipe values and exact changes', 'Simulation, keyboard and touch checks pass',
                       'Johnathan plays the compared builds and separately accepts the task'])
    with redirect_stdout(io.StringIO()):
        project_plan.prepare(fixture, folder, document, None)
    http = server(app); host = threading.Thread(target=http.serve_forever, daemon=True); host.start()
    error = None
    try:
        env = dict(os.environ, EMBER_PLAYWRIGHT_MODULE=runtime['module'], EMBER_BROWSER_EXECUTABLE=runtime['browser'],
            EMBER_BROWSER_URL=f'http://127.0.0.1:{http.server_port}/', EMBER_BROWSER_TOKEN=app.token,
            EMBER_BROWSER_OUTPUT=str(output))
        with synthetic_provider_guard(), patch('ember_harness.muse_chat.installed_binary', return_value=None), \
                patch('ember_harness.task_run.installed_binary', return_value=None), redirect_stdout(io.StringIO()):
            with (output / 'browser.log').open('w', encoding='utf-8') as log:
                result = subprocess.run([runtime['node'], str(ROOT / 'tools/mechanic_check.js')], cwd=ROOT,
                    env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
            if result.returncode:
                raise ValueError('Mechanic browser rehearsal failed; see browser.log')
        versions = project_versions.history(folder)
        if len(versions) != 5:
            raise ValueError('Reference, both recipes and forward restores must retain five versions')
        snapshots = [project_versions.snapshot(fixture, folder, row['request_ref']) for row in versions]
        if snapshots[0]['mechanics']['recipes'] or snapshots[1]['mechanics']['settings']['coyote_ms'] != 0:
            raise ValueError('Baseline or movement-only version invented jump assistance')
        if snapshots[2]['files'] != snapshots[4]['files'] or snapshots[1]['files'] != snapshots[3]['files']:
            raise ValueError('Forward restore did not preserve the exact reviewed recipe versions')
        current = chat_build.context(fixture, folder)
        if current['mechanics']['settings']['max_speed'] != 300 or current['mechanics']['settings']['coyote_ms'] != 100:
            raise ValueError('Reviewed movement/jump settings were lost')
        plan = project_plan.status(fixture, folder)
        if plan['tasks'][0]['state'] != 'human_accepted' or plan['tasks'][0]['build_ref'] != versions[-1]['request_ref']:
            raise ValueError('Final exact build application did not retain separate fixture owner acceptance')
        comparisons = gameplay.proposal_reports(folder)
        if (len(comparisons) != 5 or sum(row['outcome'] == 'passed' for row in comparisons) != 4 or
                sum(row['outcome'] == 'checks_failed' for row in comparisons) != 1):
            raise ValueError('Recipe and restore comparisons did not pass required checks')
        if not any(row['change'] == 'fixed' for report in comparisons for row in report['comparison']):
            raise ValueError('The formerly missed jump was not checked against its failing baseline')
        rejected = next(row for row in comparisons if row['outcome'] == 'checks_failed')
        retained = next(row for row in chat_build.list_requests(folder) if row['ref'] == rejected['request_ref'])
        if not retained['decision'] or retained['decision']['choice'] != 'decline':
            raise ValueError('The failed candidate must remain a separately discarded review')
        body = retained['payload']['body']
        config = next(action['args_constraints']['content']['equals']
            for action in body['contracts'][-1]['contract']['allowed_actions']
            if action['tool'] == 'fs.write' and action['args_constraints']['path']['equals'].endswith('/mechanic-config.js'))
        rejected_files = dict(snapshots[1]['files']); rejected_files['mechanic-config.js'] = config
        if mechanic_recipes.inspect(rejected_files)['settings']['coyote_ms'] != 0:
            raise ValueError('The rejected zero-window candidate source was not retained exactly')
        raw_reports = []
        for source in folder.glob('proposal-checks/*/*/input.json'):
            observed = polish_runtime.verified_report(source, source.parent / 'output')
            if not observed.get('mechanics'):
                raise ValueError('A reference comparison omitted deterministic mechanic observations')
            raw_reports.append(observed['mechanics'])
        with zipfile.ZipFile(output / 'game.zip') as archive:
            metadata = json.loads(archive.read('ember-build.json'))
            if metadata['mechanics'] != snapshots[2]['mechanics']:
                raise ValueError('Game ZIP lost reviewed recipe metadata')
        with zipfile.ZipFile(output / 'handoff.zip') as archive:
            handoff = json.loads(archive.read('project-report.json'))
            if handoff['mechanics'] != current['mechanics'] or not handoff['project_plan']['tasks'][0]['accepted']:
                raise ValueError('Final handoff lost the exact recipe or separate fixture acceptance')
        if (fixture / '.harness/muse-credits.json').exists():
            raise ValueError('The recipe rehearsal must not reserve or spend Muse credits')
    except Exception as failure:
        error = str(failure)
    finally:
        http.shutdown(); http.server_close(); host.join(timeout=5)
    unchanged = source_manifest() == before
    report = dict(passed=error is None and unchanged, error=error, source_unchanged=unchanged, source_manifest=before,
        basis='Real Chromium UI, keyboard/touch, fixed-step observations and exact source evidence; owner choices are synthetic fixtures. No live Muse calls or credits.',
        checks='Approve scope → review/apply reference → save bounded checks → tune/reload/apply movement → record failing coyote baseline → reject and retain ineffective zero-window proposal → tune/reload/compare/apply jump assistance → keyboard/touch → ZIP → checked forward restores → separately accept final task → handoff',
        human_playtest='pending; synthetic fixture acceptance does not establish Johnathan’s gameplay judgment')
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (output / 'REPORT.md').write_text('# Mechanic recipe product rehearsal\n\n' + ('PASS' if report['passed'] else 'FAIL') +
        '\n\n' + report['basis'] + '\n\n' + report['checks'] + '\n\nSource unchanged: ' + str(unchanged) +
        ('\n\n' + error if error else '') + '\n', encoding='utf-8')
    print(output / 'REPORT.md')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
