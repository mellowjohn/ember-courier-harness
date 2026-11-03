"""Cross-workflow handoff checks; provider, owner and browser replies are fixtures."""
from copy import deepcopy
from hashlib import sha256
import io
import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

import test_project_plan as plans
import test_findings as bugs
import test_gameplay as checks
import test_task_run as tasks
from ember_harness import chat_build, gameplay, project_handoff, project_plan, task_run
from ember_harness.local_ui import server
from ember_harness.recovery import atomic_json


class ProjectHandoffTests(unittest.TestCase):
    def setUp(self):
        self.fixture = plans.ProjectPlanTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.folder, self.app = self.fixture.root, self.fixture.folder, self.fixture.app
        self.sid = self.folder.name
        self.plan_ref = self.fixture.approve()
        self.ref = self.fixture.apply_build()

    def download(self, ref=None):
        data, filename = self.app.export_handoff(self.sid, ref or self.ref)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            files = {name:archive.read(name) for name in archive.namelist()}
        return json.loads(files['project-report.json']), files, data, filename

    def test_current_report_zip_hash_and_read_only_export_without_private_history(self):
        before = chat_build.harness(self.folder)._entries()
        with patch('ember_harness.task_run.run_muse') as model:
            report, files, raw, filename = self.download()
            model.assert_not_called()
        self.assertEqual(filename, 'ember-project-v1-handoff.zip')
        self.assertEqual(set(files), {'game.zip','PROJECT_HANDOFF.md','project-report.json'})
        self.assertEqual(report['game_zip_sha256'], sha256(files['game.zip']).hexdigest())
        with zipfile.ZipFile(io.BytesIO(files['game.zip'])) as game:
            self.assertEqual(game.read('index.html').decode(), plans.HTML)
        self.assertEqual(report['project_plan']['approved']['ref'], self.plan_ref)
        self.assertTrue(report['build']['matches_current_plan'])
        self.assertFalse(report['project_plan']['tasks'][0]['accepted'])
        self.assertEqual(report['gameplay']['current_build_checks'], [])
        self.assertIn(b'not checked', files['PROJECT_HANDOFF.md'])
        self.assertNotIn(str(self.root), files['project-report.json'].decode())
        self.assertNotIn(self.app.token, files['project-report.json'].decode())
        self.assertNotIn('SYNTHETIC TEST: approve', files['project-report.json'].decode())
        self.assertEqual(before, chat_build.harness(self.folder)._entries())
        self.assertEqual(raw, self.download()[2])

    def test_acceptance_does_not_transfer_to_later_build_or_amended_scope(self):
        self.app.plan_control(self.sid,'accept',plan_ref=self.plan_ref,task_id='task-1',build_ref=self.ref)
        self.assertTrue(self.download()[0]['project_plan']['tasks'][0]['acceptance_applies_to_current_build'])
        self.app.plan_control(self.sid,'select',plan_ref=self.plan_ref,task_id='task-2')
        self.ref = self.fixture.apply_build(turn='handoff-new-version',html=plans.HTML.replace('Deliver','Send parcel'))
        report = self.download()[0]
        self.assertTrue(report['project_plan']['tasks'][0]['accepted'])
        self.assertFalse(report['project_plan']['tasks'][0]['acceptance_applies_to_current_build'])
        changed = deepcopy(self.fixture.document); changed['scope']['features'].append('Reset deliveries')
        amend = self.fixture.prepare(changed)
        self.app.plan_control(self.sid,'acknowledge',ref=amend)
        self.app.respond(amend,'approve','SYNTHETIC TEST: reviewed amendment')
        report = self.download()[0]
        self.assertEqual(report['project_plan']['approved']['version'],2)
        self.assertFalse(report['build']['matches_current_plan'])
        self.assertFalse(any(t['accepted'] for t in report['project_plan']['tasks']))
        self.assertEqual(len(report['project_plan']['acceptance_history']),1)

    def test_stale_version_wrong_session_and_unapproved_changes_reject(self):
        with self.assertRaisesRegex(ValueError,'intended session'):
            self.app.export_handoff('f'*24,self.ref)
        old = self.ref
        self.ref = self.fixture.apply_build(turn='handoff-new-version',html=plans.HTML.replace('Deliver','Send parcel'))
        with self.assertRaisesRegex(ValueError,'current build changed'):
            self.download(old)
        path = chat_build.project(self.root,self.folder)/'index.html'
        path.write_text('External edit',encoding='utf-8')
        with self.assertRaises(ValueError):self.download()

    def test_evidence_change_during_report_rejects_mixed_snapshot(self):
        original = project_handoff.current_checks
        def race(*args):
            h = chat_build.harness(self.folder)
            with h._lock():h._append('synthetic_handoff_race',note='SYNTHETIC test event')
            return original(*args)
        with patch('ember_harness.project_handoff.current_checks',side_effect=race):
            with self.assertRaisesRegex(ValueError,'evidence changed during'):self.download()

    def test_current_gameplay_capture_is_rechecked_and_stale_plan_is_excluded(self):
        saved = gameplay.save(self.folder,checks.PLAN,0)
        observed = dict(complete=True,gameplay=checks.result(checks.PLAN))
        def inspect(runtime, source, output, **kwargs):
            output.mkdir(parents=True,exist_ok=True);atomic_json(output/'report.json',observed)
            return observed
        with patch('ember_harness.polish_runtime.discover',return_value={}),patch('ember_harness.polish_runtime.inspect',side_effect=inspect):
            gameplay.run_current(self.root,self.folder,1,self.ref,'handoff-gameplay-01')
        with patch('ember_harness.polish_runtime.verified_report',return_value=observed) as verify:
            self.assertEqual(self.download()[0]['gameplay']['current_build_checks'][0]['outcome'],'passed')
            verify.assert_called_once()
        capture=self.folder/'gameplay-runs/handoff-gameplay-01/output/report.json'
        capture.write_text('{}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'evidence changed'):self.download()
        gameplay.save(self.folder,{**checks.PLAN,'title':'Changed expectations'},saved['revision'])
        self.assertEqual(self.download()[0]['gameplay']['current_build_checks'],[])

    def test_http_token_and_session_binding(self):
        http=server(self.app);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        self.addCleanup(thread.join,2);self.addCleanup(http.server_close);self.addCleanup(http.shutdown)
        url=f'http://127.0.0.1:{http.server_port}/api/export-handoff?session_id={self.sid}&ref={self.ref}'
        with self.assertRaises(HTTPError) as denied:urlopen(url)
        self.assertEqual(denied.exception.code,403)
        with urlopen(Request(url,headers={'X-Ember-Token':self.app.token})) as response:
            self.assertEqual(response.headers['Content-Type'],'application/zip')
            self.assertTrue(zipfile.is_zipfile(io.BytesIO(response.read())))
        with self.assertRaises(HTTPError) as stale:
            urlopen(Request(url.replace(self.sid,'f'*24),headers={'X-Ember-Token':self.app.token}))
        self.assertEqual(stale.exception.code,400)


class FindingHandoffTests(unittest.TestCase):
    def test_closure_and_ai_judgment_stay_separate_from_task_acceptance(self):
        fixture=bugs.FindingTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        bug=fixture.submit();run=fixture.prepare(bug);fixture.run_fix(run);ref=fixture.apply(run)
        close=fixture.app.finding_control(fixture.sid,'close',run_id=run)['request_ref']
        fixture.app.respond(close,'approve','SYNTHETIC TEST: explicit closure')
        data,_=fixture.app.export_handoff(fixture.sid,ref)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:report=json.loads(archive.read('project-report.json'))
        self.assertTrue(report['findings'][0]['closure_applies_to_current_build'])
        self.assertFalse(report['project_plan']['tasks'][0]['accepted'])
        self.assertEqual(report['task_runs'][0]['attempts'][0]['browser_outcome'],'passed')
        self.assertIn('ai_judgment',report['task_runs'][0]['attempts'][0])
        self.assertNotEqual(report['task_runs'][0]['author'],report['task_runs'][0]['reviewer'])
        work=fixture.folder/'task-runs'/run
        (work/'captures/1/output/desktop.png').write_bytes(b'tamper')
        with self.assertRaises(ValueError):fixture.app.export_handoff(fixture.sid,ref)


class TaskQualityHandoffTests(unittest.TestCase):
    def test_frozen_coverage_and_comparison_survive_handoff_without_human_acceptance(self):
        fixture = tasks.TaskRunTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        run = fixture.prepare(); fixture.approve(run)
        state = fixture.run_worker(run)
        self.assertEqual(state['status'], 'ready_review', state.get('error'))
        ref = task_run.promote(fixture.root, fixture.folder, run)['request_ref']
        fixture.app.respond(ref, 'approve', 'SYNTHETIC exact task candidate')
        raw, _ = fixture.app.export_handoff(fixture.sid, ref)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            text = archive.read('project-report.json').decode()
            report = json.loads(text)
        task = report['task_runs'][0]
        self.assertEqual(task['coverage_review'], state['coverage_review'])
        self.assertEqual(task['quality_criteria'], state['quality'])
        self.assertEqual(task['attempts'][0]['comparison'], state['reports'][0]['comparison'])
        self.assertEqual(task['attempts'][0]['quality_review'], state['reports'][0]['quality'])
        self.assertFalse(report['project_plan']['tasks'][0]['accepted'])
        self.assertNotIn(str(fixture.root), text)
        self.assertNotIn(fixture.app.token, text)
        work = task_run.run_folder(fixture.folder, run)
        (work / 'captures/0/output/mobile.png').write_bytes(b'changed baseline capture')
        with self.assertRaises(ValueError):
            fixture.app.export_handoff(fixture.sid, ref)


if __name__=='__main__':unittest.main()
