"""Real intake/gate/evidence with explicitly synthetic model, browser and owner fixtures."""
from copy import deepcopy
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import test_task_run as tasks
import test_gameplay as checks
from ember_harness import chat_build, findings, gameplay, project_plan, task_run
from ember_harness.attempts import Attempts
from ember_harness.contract_lock import verify as contract_lock
from ember_harness.local_ui import App, server
from ember_harness.recovery import atomic_json, read_json


FIELDS = dict(summary='Counter loses a point', area='browser_game', symptom_tag='lost_point',
              steps=['Press Start', 'Inspect score'], expected='At least one point', actual='Zero points',
              frequency='always', impact='degraded')


class FindingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = tasks.TaskRunTests(); self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.root, self.folder, self.app = self.fixture.root, self.fixture.folder, self.fixture.app
        self.sid = self.folder.name
        self.report_id = 'finding-playtest-test-01'
        self.app.record_playtest(report_id=self.report_id, request_ref=self.fixture.fixture.base,
                                 outcome='problem', note='SYNTHETIC counter loses a point', observations=[])
        self.reproduces = True
        self.passes = True

    def submit(self, fields=None, **kwargs):
        ref = self.app.finding_control(self.sid, 'prepare', report_id=self.report_id,
                                       fields=FIELDS if fields is None else fields, **kwargs)['request_ref']
        result = self.app.respond(ref, 'approve', 'SYNTHETIC TEST: reviewed finding intake and QA')
        return findings.intake(self.folder).get(result['bug_id'])

    def prepare(self, bug):
        return self.app.task_control(self.sid, 'prepare-fix', bug_id=bug['id'], bug_hash=bug['record_hash'], scenario=0)['id']

    def browser(self, runtime, source, output, **kwargs):
        result = self.fixture.fixture.browser(runtime, source, output, **kwargs)
        baseline = Path(source).parent.name == '0'
        failed = self.reproduces if baseline else not self.passes
        result['gameplay'] = checks.result(read_json(source)['gameplay_plan'], failed=failed)
        atomic_json(Path(output) / 'report.json', result)
        return result

    def run_fix(self, run_id):
        self.fixture.approve(run_id)
        return self.fixture.run_worker(run_id, browser=self.browser)

    def apply(self, run_id):
        ref = task_run.promote(self.root, self.folder, run_id)['request_ref']
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: exact checked fix')
        return ref

    def test_reviewed_intake_persistence_idempotence_and_bound_host_evidence(self):
        with patch('ember_harness.task_run.run_muse') as model:
            bug = self.submit()
            self.assertEqual(bug['state'], 'triaged')
            self.assertTrue(bug['route']['code_fix_allowed'])
            self.assertEqual(self.submit()['id'], bug['id'])
            model.assert_not_called()
        fresh = App(self.root); fresh.resume(self.sid)
        row = fresh.snapshot()['findings'][0]
        self.assertEqual(row['bug']['record_hash'], bug['record_hash'])
        evidence = read_json(bug['evidence'][0]['path'])
        self.assertEqual(evidence['request_ref'], bug['build_id'])
        self.assertEqual(row['attempts']['attempts_started'], 0)
        with self.assertRaisesRegex(ValueError, 'details only'):
            self.submit(dict(FIELDS, evidence=[dict(path='C:/secret', sha256='f'*64)]))
        self.assertTrue(contract_lock(chat_build.harness(self.folder).root)['ok'])

    def test_description_creates_reviewed_finding_without_a_prior_problem_report(self):
        fields = {key: FIELDS[key] for key in ('summary', 'steps', 'expected', 'actual')}
        report_id = 'tester-description-report-01'
        body = dict(report_id=report_id, request_ref=self.fixture.fixture.base, fields=fields)
        with patch('ember_harness.task_run.run_muse') as model:
            result = self.app.finding_control(self.sid, 'describe', **body)
            self.assertEqual(self.app.finding_control(self.sid, 'describe', **body), result)
            self.assertEqual(findings.history(self.root, self.folder), [])
            report = next(r for r in self.app.snapshot()['build']['playtests'] if r['report_id'] == report_id)
            self.assertEqual(report['note'], fields['summary'])
            self.assertEqual(report['basis'], 'human_playtest')
            fresh = App(self.root); fresh.resume(self.sid)
            approved = fresh.respond(result['request_ref'], 'approve', 'SYNTHETIC TEST: reviewed tester description')
            bug = findings.intake(self.folder).get(approved['bug_id'])
            self.assertEqual(bug['state'], 'triaged')
            self.assertEqual(bug['steps'], fields['steps'])
            self.assertEqual(bug['area'], 'browser_game')
            self.assertEqual(bug['frequency'], 'once')
            self.assertEqual(bug['symptom_tag'], 'counter_loses_a_point')
            self.assertEqual(Attempts(chat_build.harness(self.folder)).status(bug['id'])['attempts_started'], 0)
            model.assert_not_called()
        self.assertTrue(contract_lock(chat_build.harness(self.folder).root)['ok'])

    def test_description_rejects_missing_details_and_injected_evidence_before_recording(self):
        before = self.app.snapshot()['build']['playtests']
        for fields in (dict(FIELDS, expected=' '), dict(FIELDS, steps=[]), dict(FIELDS, steps=[' '])):
            with self.assertRaisesRegex(ValueError, 'Describe the bug'):
                self.app.finding_control(self.sid, 'describe', report_id='tester-invalid-report-01',
                                        request_ref=self.fixture.fixture.base, fields=fields)
        with self.assertRaisesRegex(ValueError, 'details only'):
            self.app.finding_control(self.sid, 'describe', report_id='tester-invalid-report-01',
                request_ref=self.fixture.fixture.base, fields=dict(FIELDS, evidence=[]))
        with self.assertRaisesRegex(ValueError, 'stale'):
            self.app.finding_control(self.sid, 'describe', report_id='tester-invalid-report-01',
                                    request_ref='outdated-build', fields=FIELDS)
        with self.assertRaisesRegex(ValueError, 'Reopen'):
            self.app.finding_control('another-session', 'describe', report_id='tester-invalid-report-01',
                                    request_ref=self.fixture.fixture.base, fields=FIELDS)
        self.assertEqual(self.app.snapshot()['build']['playtests'], before)
        self.assertEqual(findings.requests(self.folder), [])

    def test_missing_repro_and_paused_routes_cannot_start_a_worker(self):
        missing = self.submit({k:v for k,v in FIELDS.items() if k != 'steps'})
        self.assertEqual(missing['state'], 'needs_repro')
        with self.assertRaisesRegex(ValueError, 'not ready'):
            self.prepare(missing)
        engine = self.submit(dict(FIELDS, summary='Engine symptom', area='engine'))
        self.assertFalse(engine['route']['code_fix_allowed'])
        with self.assertRaisesRegex(ValueError, 'not ready'):
            self.prepare(engine)

    def test_scoped_fix_baseline_independent_verification_exact_build_and_owner_close(self):
        bug = self.submit(); run_id = self.prepare(bug)
        state = self.run_fix(run_id)
        self.assertEqual(state['status'], 'ready_review', state.get('error'))
        self.assertEqual([c[0] for c in self.fixture.calls], ['generate-1', 'verify-1'])
        self.assertEqual(state['attempts']['attempts'][0]['status'], 'running')
        self.assertIn('lost_point', self.fixture.calls[0][1])
        with self.assertRaisesRegex(ValueError, 'apply the exact'):
            findings.prepare_close(self.root, self.folder, run_id)
        ref = self.apply(run_id)
        self.assertEqual(findings.intake(self.folder).get(bug['id'])['state'], 'triaged')
        review = self.app.finding_control(self.sid, 'close', run_id=run_id)['request_ref']
        result = self.app.respond(review, 'approve', 'SYNTHETIC TEST: explicit verified closure')
        self.assertEqual(result['status'], 'closed')
        self.assertEqual(self.app.respond(review, 'approve', 'SYNTHETIC TEST: explicit verified closure'), result)
        row = self.app.snapshot()['findings'][0]
        self.assertEqual(row['attempts']['status'], 'closed')
        self.assertEqual(row['closure']['build'], ref)
        self.assertEqual(set(row['closure']['checkpoints']), {'C0','C1','C2','C3'})
        self.assertIsNone(project_plan.status(self.root,self.folder)['tasks'][0]['acceptance'])
        lock = contract_lock(chat_build.harness(self.folder).root)
        self.assertTrue(lock['ok'], lock)
        self.assertTrue(self.app.verify()['finding_history']['ok'])

    def test_no_reproduction_calls_no_model_and_consumes_approved_attempt(self):
        bug=self.submit();run_id=self.prepare(bug);self.reproduces=False
        state=self.run_fix(run_id)
        self.assertEqual(state['status'],'stopped',state.get('error'))
        self.assertEqual(self.fixture.calls,[])
        ledger=Attempts(chat_build.harness(self.folder)).status(bug['id'])
        self.assertEqual(ledger['attempts'][0]['status'],'abandoned')
        self.assertEqual(ledger['attempts_started'],1)
        stopped=next(e for e in chat_build.harness(self.folder)._entries() if e.get('detail',{}).get('scope')=='browser_bug_abandoned')
        self.assertEqual(stopped['actor_type'],'host')

    def test_failed_browser_beats_positive_ai_three_attempts_and_one_extra(self):
        bug=self.submit();self.passes=False
        for number in range(1,4):
            run_id=self.prepare(bug);state=self.run_fix(run_id)
            self.assertEqual(state['status'],'awaiting_decision',state.get('error'))
            self.assertFalse(state['reports'][0]['qualified'])
            self.assertTrue(state['reports'][0]['verdict']['meets_task'])
            self.assertEqual(len(state['attempts']['attempts']),number)
        with self.assertRaisesRegex(ValueError,'awaiting_decision'):self.prepare(bug)
        self.app.task_control(self.sid,'escalate',run_id=run_id,choice='retry',state_hash=state['attempts']['state_hash'])
        extra=self.prepare(bug);self.passes=True;state=self.run_fix(extra)
        self.assertEqual(state['status'],'ready_review',state.get('error'))
        self.assertEqual(len(state['attempts']['attempts']),4)
        lock=contract_lock(chat_build.harness(self.folder).root)
        self.assertTrue(lock['ok'],lock)

    def test_critical_close_gate_requires_johnathans_action_even_under_approve_all(self):
        bug=self.submit(dict(FIELDS,impact='core_loop_broken'))
        self.assertEqual(bug['severity'],'S1')
        run_id=self.prepare(bug);self.run_fix(run_id);self.apply(run_id)
        _,h,packet,_=task_run.load(self.folder,run_id)
        verifier=packet['body']['contracts'][1]['contract']
        action=dict(agent=verifier['agent'],contract_id=verifier['id'],tool='triage.close',
                    args=dict(bug_id=bug['id'],severity='S1'),paths=dict(read=[],write=[]),spend=0)
        self.assertEqual(h.check(action)['decision'],'needs_approval')
        with self.assertRaisesRegex(ValueError,'Explicit owner'):findings.close(self.root,self.folder,run_id)
        ref=findings.prepare_close(self.root,self.folder,run_id)['request_ref']
        self.assertEqual(self.app.respond(ref,'approve','SYNTHETIC TEST: Johnathan explicitly closes S1')['status'],'closed')

    def test_reopening_preserves_attempts_and_requires_fresh_repro(self):
        bug=self.submit();run_id=self.prepare(bug);self.run_fix(run_id);self.apply(run_id)
        ref=findings.prepare_close(self.root,self.folder,run_id)['request_ref']
        self.app.respond(ref,'approve','SYNTHETIC TEST: closure')
        row=self.app.snapshot()['findings'][0]
        self.app.finding_control(self.sid,'reopen',bug_id=bug['id'],bug_hash=row['bug']['record_hash'],
            state_hash=row['attempts']['state_hash'],note='SYNTHETIC TEST: recurrence on the applied build')
        reopened=findings.intake(self.folder).get(bug['id'])
        self.assertEqual(reopened['state'],'reopened')
        self.assertEqual(Attempts(chat_build.harness(self.folder)).status(bug['id'])['attempts_started'],1)
        with self.assertRaises(ValueError):self.prepare(reopened)
        self.report_id='reopened-playtest-test-01'
        self.app.record_playtest(report_id=self.report_id,request_ref=chat_build.status(self.root,self.folder)['completed'][-1]['request_ref'],
            outcome='problem',note='SYNTHETIC recurring symptom',observations=[])
        updated=self.submit(bug_id=bug['id'],bug_hash=reopened['record_hash'])
        self.assertEqual(updated['state'],'triaged')
        new=self.prepare(updated);self.assertNotEqual(new,run_id)
        self.fixture.approve(new)
        def recurrence_model(*args,**kwargs):
            result=self.fixture.model(*args,**kwargs)
            if args[3].startswith('generate'):
                build=json.loads(result['response'])
                next(item for item in build['files'] if item['path']=='style.css')['content']+='\nbutton{padding:25px}'
                result=dict(response=json.dumps(build))
            return result
        state=self.fixture.run_worker(new,model=recurrence_model,browser=self.browser)
        self.assertEqual(state['status'],'ready_review',state.get('error'))

    def test_changed_baseline_capture_or_candidate_blocks_promotion_and_closure(self):
        bug=self.submit();run_id=self.prepare(bug);self.run_fix(run_id)
        work=task_run.run_folder(self.folder,run_id)
        for relative in ['captures/0/output/desktop.png','captures/1/output/report.json','candidates/1/style.css']:
            path=work/relative;raw=path.read_bytes();path.write_bytes(b'tampered')
            with self.assertRaises(ValueError):task_run.promote(self.root,self.folder,run_id)
            path.write_bytes(raw)
        self.apply(run_id)
        gameplay.save(self.folder,dict(checks.PLAN,title='Changed closure expectations'),1)
        with self.assertRaisesRegex(ValueError,'Gameplay plan changed'):findings.prepare_close(self.root,self.folder,run_id)

    def test_current_bug_hash_and_qa_mutations_during_run_are_enforced(self):
        bug=self.submit()
        with self.assertRaisesRegex(ValueError,'Finding changed'):self.prepare(dict(bug,record_hash='f'*64))
        run_id=self.prepare(bug);self.fixture.approve(run_id)
        with self.assertRaisesRegex(ValueError,'active fix'):
            self.app.finding_control(self.sid,'severity',bug_id=bug['id'],bug_hash=bug['record_hash'],
                severity='S3',demo_impact=False,note='SYNTHETIC stale classification')
        task_run.stop(self.root,self.folder,run_id)

    def test_http_session_binding_and_intake_review_authorization(self):
        with self.assertRaisesRegex(ValueError,'intended session'):
            self.app.finding_control('f'*24,'prepare',report_id=self.report_id,fields=FIELDS)
        http=server(self.app);self.addCleanup(http.server_close);self.addCleanup(http.shutdown)
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();self.addCleanup(thread.join,2)
        endpoint='http://127.0.0.1:'+str(http.server_address[1])+'/api/finding'
        data=json.dumps(dict(session_id=self.sid,action='describe',report_id='tester-http-description-01',
                             request_ref=self.fixture.fixture.base,fields=FIELDS)).encode()
        with self.assertRaises(HTTPError) as denied:urlopen(Request(endpoint,data,{'Content-Type':'application/json'}))
        self.assertEqual(denied.exception.code,403)
        with urlopen(Request(endpoint,data,{'Content-Type':'application/json','X-Ember-Token':self.app.token})) as response:
            result=json.load(response)
        self.assertIn('request_ref',result)
        self.assertEqual(findings.intake(self.folder).list(),[])

    def test_duplicate_confirmation_and_critical_severity_review_use_existing_qa(self):
        first=self.submit()
        second=self.submit(dict(FIELDS,summary='Counter still loses a point'))
        self.assertEqual(second['duplicate_candidates'][0]['bug_id'],first['id'])
        self.app.finding_control(self.sid,'duplicate',bug_id=second['id'],bug_hash=second['record_hash'],
            target_id=first['id'],target_hash=first['record_hash'],note='SYNTHETIC same reproduction and symptom')
        self.assertEqual(findings.intake(self.folder).get(second['id'])['duplicate_of'],first['id'])
        critical=self.submit(dict(FIELDS,summary='Browser game blocks demo',impact='blocks_demo'))
        self.assertTrue(critical['severity_review_required'])
        with self.assertRaisesRegex(ValueError,'not ready'):self.prepare(critical)
        self.app.finding_control(self.sid,'severity',bug_id=critical['id'],bug_hash=critical['record_hash'],
            severity='S0',demo_impact=True,note='SYNTHETIC QA confirms blocked demo')
        reviewed=findings.intake(self.folder).get(critical['id'])
        self.assertEqual(reviewed['state'],'triaged')
        self.assertEqual(reviewed['severity'],'S0')
        self.assertFalse(reviewed['severity_review_required'])

    def test_interrupted_verifier_reuses_baseline_coder_and_bug_allocation(self):
        bug=self.submit();run_id=self.prepare(bug);self.fixture.approve(run_id)
        def interrupt(*args,**kwargs):
            if args[3]=='verify-1':raise ValueError('SYNTHETIC provider interruption')
            return self.fixture.model(*args,**kwargs)
        state=self.fixture.run_worker(run_id,model=interrupt,browser=self.browser)
        self.assertEqual(state['status'],'interrupted')
        state=self.fixture.run_worker(run_id,browser=self.browser)
        self.assertEqual(state['status'],'ready_review',state.get('error'))
        self.assertEqual(len(state['attempts']['attempts']),1)
        self.assertEqual([c[0] for c in self.fixture.calls],['generate-1','verify-1'])

    def test_stale_playtest_and_tampered_retained_evidence_stop_before_worker(self):
        bug=self.submit()
        project_file=chat_build.project(self.root,self.folder)/'style.css'
        original_source=project_file.read_bytes();project_file.write_bytes(b'body{color:red}')
        with self.assertRaisesRegex(ValueError,'Project changed'):self.prepare(bug)
        project_file.write_bytes(original_source)
        evidence=Path(bug['evidence'][0]['path']);original=evidence.read_bytes();evidence.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'evidence copy'):self.prepare(bug)
        evidence.write_bytes(original)
        files={item['path']:item['content'] for item in chat_build.context(self.root,self.folder)['files']}
        files['style.css']+='\nbutton{border-radius:9px}'
        ref=self.fixture.fixture.fixture.propose_project(files,turn='new-finding-build-01')
        self.app.respond(ref,'approve','SYNTHETIC new build identity')
        with self.assertRaisesRegex(ValueError,'stale'):self.submit(dict(FIELDS,summary='Old report'))
        with self.assertRaisesRegex(ValueError,'stale'):self.prepare(bug)
        self.assertEqual(self.fixture.calls,[])

    def test_historical_closure_evidence_is_rechecked_after_project_advances(self):
        bug=self.submit();run_id=self.prepare(bug);self.run_fix(run_id);self.apply(run_id)
        ref=findings.prepare_close(self.root,self.folder,run_id)['request_ref']
        self.app.respond(ref,'approve','SYNTHETIC closure')
        path=task_run.run_folder(self.folder,run_id)/'captures/0/output/desktop.png'
        path.write_bytes(b'changed historical evidence')
        result=contract_lock(chat_build.harness(self.folder).root)
        self.assertFalse(result['ok'])
        self.assertTrue(any('browser finding history' in e for e in result['errors']))


if __name__=='__main__':
    unittest.main()
