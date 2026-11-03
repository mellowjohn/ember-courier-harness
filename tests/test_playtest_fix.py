"""Notes-only fixes use real scope/review boundaries and synthetic model replies."""
import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import test_chat_build as builds
import test_project_plan as plans
from ember_harness import chat_build, gameplay, playtests, session_chat
from ember_harness.local_ui import App, server


class PlaytestFixTests(unittest.TestCase):
    def setUp(self):
        self.fixture = builds.ChatBuildTests(); self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.root, self.folder, self.app = self.fixture.root, self.fixture.folder, self.fixture.app
        self.sid = self.folder.name
        self.base = self.fixture.propose_project()
        self.app.respond(self.base, 'approve', 'SYNTHETIC TEST: initial game')
        self.body = dict(session_id=self.sid, report_id='notes-only-report-0001', request_ref=self.base,
                         note='The counter freezes after I press Start twice.', observations=[])
        self.calls = []

    def model(self, root, folder, prompt, request_id, **kwargs):
        self.calls.append((prompt, request_id, kwargs))
        kwargs['progress']('muse_working')
        data = json.loads(prompt.split('\n', 1)[1])
        if kwargs['output_schema'] == session_chat.DIAGNOSIS_SCHEMA:
            return dict(response=json.dumps(dict(summary='Inspect the counter handler.', cause='Likely counter state handling.',
                files=['app.js'], plan='Preserve the controls and repair only the counter handler.')))
        self.assertEqual(data['investigation']['files'], ['app.js'])
        self.assertEqual(data['playtest_fix']['note'], self.body['note'])
        before = next(row['content'] for row in data['project']['files'] if row['path'] == 'app.js')
        return dict(response=json.dumps(dict(message='Review this proposed counter fix. Gameplay has not been tested.',
            build=dict(title='Notes-only counter fix', summary='A targeted proposed repair',
                       edits=[dict(path='app.js', before=before, after=before+'\n// SYNTHETIC repair')]))))

    def test_notes_investigation_proposal_progress_and_exact_approval_without_forms(self):
        with patch('ember_harness.session_chat.run_muse', side_effect=self.model), \
                patch('ember_harness.findings.prepare') as intake, patch('ember_harness.task_run.prepare') as task:
            result = self.app.fix_playtest(**self.body)
            self.assertEqual(self.app.fix_playtest(self.sid, self.body['report_id']), result)
            intake.assert_not_called(); task.assert_not_called()
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(all(call[2]['execution']['reasoning_effort'] == 'high' for call in self.calls))
        self.assertEqual([call[2]['execution']['timeout_seconds'] for call in self.calls], [900, 900])
        self.assertEqual(self.calls[0][2]['budget'], self.calls[1][2]['budget'])
        self.assertEqual(self.calls[0][2]['budget']['limit_micro_usd'], 10_000_000)
        self.assertEqual(len(self.calls[0][2]['budget']['id']), 64)
        self.assertEqual(gameplay.load(self.folder)['plan']['scenarios'], [])
        activity = self.app.snapshot()['chat_activity']
        self.assertEqual(activity['kind'], 'playtest_fix')
        self.assertEqual(activity['diagnosis']['files'], ['app.js'])
        phases = [e['phase'] for e in activity['events']]
        self.assertLess(phases.index('investigating'), phases.index('fixing'))
        self.assertEqual(activity['phase'], 'awaiting_review')
        self.assertIn('app.js',activity['read_files'])
        self.assertEqual(activity['proposed_files'],['app.js'])
        self.assertEqual((self.fixture.target.parent/'app.js').read_text(), builds.PROJECT['app.js'])
        proposal = result['messages'][-1]['proposal_ref']
        self.app.respond(proposal, 'approve', 'SYNTHETIC TEST: apply exact repair')
        self.assertIn('SYNTHETIC repair', (self.fixture.target.parent/'app.js').read_text())

    def test_failed_generation_resumes_saved_diagnosis_after_restart(self):
        def interrupted(*args, **kwargs):
            if kwargs['output_schema'] != session_chat.DIAGNOSIS_SCHEMA:
                raise ValueError('SYNTHETIC interrupted generation')
            return self.model(*args, **kwargs)
        with patch('ember_harness.session_chat.run_muse', side_effect=interrupted):
            with self.assertRaisesRegex(ValueError, 'interrupted generation'):
                self.app.fix_playtest(**self.body)
        fresh = App(self.root); fresh.resume(self.sid)
        self.assertEqual(fresh.snapshot()['chat_activity']['state'], 'failed')
        with patch('ember_harness.session_chat.run_muse', side_effect=self.model):
            fresh.fix_playtest(self.sid, self.body['report_id'])
        self.assertEqual(len(self.calls), 2)  # A second diagnosis was not purchased.
        self.assertEqual(fresh.snapshot()['chat_activity']['phase'], 'awaiting_review')

    def test_stale_notes_wrong_session_and_pending_changes_do_not_call_the_model(self):
        with patch('ember_harness.session_chat.run_muse') as model:
            with self.assertRaisesRegex(ValueError, 'intended session'):
                self.app.fix_playtest(**dict(self.body, session_id='other'))
            with self.assertRaisesRegex(ValueError, 'stale'):
                self.app.fix_playtest(**dict(self.body, request_ref='old-build'))
            with self.assertRaisesRegex(ValueError, 'Describe the problem'):
                self.app.fix_playtest(**dict(self.body, note=' '))
            pending = self.fixture.propose_project(dict(builds.PROJECT, **{'style.css':'body{color:red}'}), turn='pending-playtest-0001')
            with self.assertRaisesRegex(ValueError, 'pending changes'):
                self.app.fix_playtest(**self.body)
            model.assert_not_called()
        self.assertEqual(len(playtests.reports(self.folder)), 1)  # Notes remain available after a blocked attempt.

    def test_a_scoped_project_can_fix_notes_without_saving_reproduction_fields(self):
        fixture = plans.ProjectPlanTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        fixture.approve(); ref = fixture.apply_build()
        calls = []
        def model(root, folder, prompt, request_id, **kwargs):
            calls.append(kwargs['output_schema'])
            data = json.loads(prompt.split('\n', 1)[1])
            if kwargs['output_schema'] == session_chat.DIAGNOSIS_SCHEMA:
                return dict(response=json.dumps(dict(summary='Read the button markup.', cause='The label is unclear.',
                                                     files=['index.html'], plan='Clarify the delivery label.')))
            self.assertTrue(data['project_plan']['active'])
            self.assertTrue(data['playtest_fix'])
            return dict(response=json.dumps(dict(message='Review the clarified delivery control.', build=dict(
                title='Clear delivery button', summary='Fix the reported label',
                edits=[dict(path='index.html', before='>Deliver<', after='>Deliver parcel<')]))))
        with patch('ember_harness.session_chat.run_muse', side_effect=model):
            fixture.app.fix_playtest(fixture.sid, 'scoped-notes-report-01', request_ref=ref,
                                    note='The delivery button label is confusing.', observations=[])
        self.assertEqual(len(calls), 2)
        self.assertEqual(gameplay.load(fixture.folder)['plan']['scenarios'], [])
        proposal = chat_build.list_requests(fixture.folder)[-1]['payload']['body']
        self.assertEqual(len(proposal['contracts']), 1)
        self.assertTrue(proposal['build']['project_scope'])

    def test_switching_sessions_during_investigation_does_not_redirect_the_fix(self):
        entered, release = threading.Event(), threading.Event(); errors = []
        def slow(*args, **kwargs):
            if kwargs['output_schema'] == session_chat.DIAGNOSIS_SCHEMA:
                entered.set()
                if not release.wait(8): raise ValueError('SYNTHETIC test timeout')
            return self.model(*args, **kwargs)
        def request():
            try: self.app.fix_playtest(**self.body)
            except Exception as error: errors.append(error)
        with patch('ember_harness.session_chat.run_muse', side_effect=slow):
            worker = threading.Thread(target=request); worker.start()
            try:
                self.assertTrue(entered.wait(8))
                self.assertEqual(self.app.snapshot()['chat_activity']['phase'], 'investigating')
                self.app.start('Other project', new_session=True, chat_only=True)
                other = self.app.session['id']
            finally:
                release.set(); worker.join(12)
        self.assertFalse(worker.is_alive()); self.assertEqual(errors, [])
        self.assertEqual(self.app.session['id'], other)
        self.assertEqual(self.app.snapshot()['messages'], [])
        self.assertEqual(session_chat.activity(self.folder)['phase'], 'awaiting_review')

    def test_http_fix_requires_authorization_before_recording_notes_or_calling_muse(self):
        http=server(self.app); worker=threading.Thread(target=http.serve_forever,daemon=True);worker.start()
        try:
            url='http://127.0.0.1:'+str(http.server_port)+'/api/playtest-fix'
            payload=json.dumps(self.body).encode()
            with patch('ember_harness.session_chat.run_muse',side_effect=self.model):
                with self.assertRaises(HTTPError) as denied:
                    urlopen(Request(url,payload,{'Content-Type':'application/json'}))
                self.assertEqual(denied.exception.code,403)
                self.assertEqual(playtests.reports(self.folder),[]); self.assertEqual(self.calls,[])
                with urlopen(Request(url,payload,{'Content-Type':'application/json','X-Ember-Token':self.app.token})) as reply:
                    self.assertEqual(json.load(reply)['report_id'],self.body['report_id'])
        finally:
            http.shutdown();http.server_close();worker.join()


if __name__ == '__main__': unittest.main()
