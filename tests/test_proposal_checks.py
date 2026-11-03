"""Synthetic captures exercise proposal comparisons without granting write authority."""
from copy import deepcopy
import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

import test_chat_build as build_fixture
import test_gameplay as gameplay_fixture
from ember_harness import chat_build, gameplay, polish_runtime
from ember_harness.local_ui import App, server
from ember_harness.recovery import atomic_json, read_json
from ember_harness.session_chat import transcript


class ProposalCheckTests(unittest.TestCase):
    def setUp(self):
        self.fixture=gameplay_fixture.GameplayTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root,self.folder,self.app,self.sid=self.fixture.root,self.fixture.folder,self.fixture.app,self.fixture.sid
        self.plan=deepcopy(gameplay_fixture.PLAN);self.fixture.save(self.plan)
        self.files={**build_fixture.PROJECT,'index.html':build_fixture.PROJECT['index.html'].replace('<body>','<body data-fixture="SYNTHETIC_BROKEN">')}
        self.ref=self.fixture.fixture.propose_project(self.files,'b'*24)

    def inspect(self,runtime,source,output,**kwargs):
        output.mkdir(parents=True,exist_ok=True)
        request=read_json(source);viewports=[]
        for name in ('desktop','mobile'):
            for suffix in ('','-before'):Image.new('RGB',(8,8),'gray').save(output/(name+suffix+'.png'))
            viewports.append(dict(name=name,screenshot=name+'.png',sha256=polish_runtime.file_digest(output/(name+'.png')),
                before_sha256=polish_runtime.file_digest(output/(name+'-before.png'))))
        observed=gameplay_fixture.result(request['gameplay_plan'],failed='SYNTHETIC_BROKEN' in request['html'])
        report=dict(complete=True,input_sha256=polish_runtime.file_digest(source),viewports=viewports,gameplay=observed,
                    basis='SYNTHETIC capture fixture, not Chromium evidence')
        from quality_fixture import aspect_captures
        aspect_captures(request, output, report)
        atomic_json(output/'report.json',report);return report

    def run_check(self,report_id='proposal-check-test-01'):
        with patch('ember_harness.polish_runtime.discover',return_value={}),patch('ember_harness.polish_runtime.inspect',side_effect=self.inspect):
            return self.app.check_proposal(self.sid,1,self.ref,report_id)

    def test_comparison_is_read_only_and_idempotent(self):
        h=chat_build.harness(self.folder);before=h._entries();files=chat_build.context(self.root,self.folder)
        with patch('ember_harness.session_chat.run_muse') as model:
            report=self.run_check();again=self.run_check();model.assert_not_called()
        self.assertEqual(report,again);self.assertEqual(report['outcome'],'regressions_observed')
        self.assertEqual(report['comparison'][0]['change'],'regression')
        self.assertEqual(chat_build.context(self.root,self.folder),files)
        self.assertEqual(len(h._entries()),len(before)+1)
        self.assertEqual(self.app.snapshot()['build']['proposal_check']['state'],'regressions_observed')
        self.assertIsNone(self.app.snapshot()['build']['requests'][-1]['decision'])
        self.assertEqual(len(self.app.snapshot()['build']['completed']),1)

    def test_first_build_has_no_synthetic_baseline(self):
        self.app.start('First build',new_session=True,chat_only=True)
        self.sid=self.app.session['id'];self.folder=self.app.sessions_dir/self.sid
        self.app.save_gameplay(self.sid,self.plan,0)
        self.ref=self.fixture.fixture.propose_project(build_fixture.PROJECT,'first-proposal-test-01')
        report=self.run_check()
        self.assertIsNone(report['before']);self.assertEqual(set(report['artifacts']),{'proposed'})
        self.assertEqual(report['comparison'][0]['change'],'new_coverage');self.assertEqual(report['outcome'],'passed')
        self.assertFalse(chat_build.project(self.root,self.folder).exists())

    def test_comparison_distinguishes_fixed_preserved_and_still_failing(self):
        passed=gameplay_fixture.result(self.plan);failed=gameplay_fixture.result(self.plan,True)
        for old,new,change in [(passed,passed,'preserved'),(passed,failed,'regression'),(failed,passed,'fixed'),(failed,failed,'still_failing')]:
            self.assertEqual(gameplay.compare(self.plan,old,new)[0]['change'],change)

    def test_stale_plan_and_decided_proposal_are_rejected_before_inspection(self):
        report=self.run_check()
        self.app.save_gameplay(self.sid,{**self.plan,'title':'Revised tests'},1)
        self.assertEqual(self.app.snapshot()['build']['proposal_check']['state'],'stale')
        with patch('ember_harness.polish_runtime.inspect') as browser:
            with self.assertRaisesRegex(ValueError,'current gameplay plan'):
                self.app.check_proposal(self.sid,1,self.ref,'proposal-stale-test-01')
            browser.assert_not_called()
        self.app.respond(self.ref,'decline','SYNTHETIC TEST: discard compared proposal')
        with self.assertRaisesRegex(ValueError,'pending proposal'):
            self.app.check_proposal(self.sid,2,self.ref,'proposal-decided-test-01')
        self.assertEqual(len(gameplay.proposal_reports(self.folder)),1)

    def test_changed_plan_during_capture_cannot_attach_a_report(self):
        original=self.inspect
        def changed(runtime,source,output,**kwargs):
            report=original(runtime,source,output,**kwargs)
            if output.parent.name=='proposed':self.app.save_gameplay(self.sid,{**self.plan,'title':'Changed during run'},1)
            return report
        with patch('ember_harness.polish_runtime.discover',return_value={}),patch('ember_harness.polish_runtime.inspect',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'changed during inspection'):
                self.app.check_proposal(self.sid,1,self.ref,'proposal-changing-plan-01')
        self.assertEqual(gameplay.proposal_reports(self.folder),[])
        self.assertIsNone(self.app.snapshot()['build']['requests'][-1]['decision'])

    def test_changed_current_files_and_tampered_packets_do_not_run(self):
        path=chat_build.project(self.root,self.folder)/'app.js';before=path.read_bytes();path.write_bytes(b'External change')
        with patch('ember_harness.polish_runtime.inspect') as browser:
            with self.assertRaises(ValueError):self.run_check()
            browser.assert_not_called()
        path.write_bytes(before)
        packet=chat_build.harness(self.folder).root/'owner-review'/self.ref/'request.json'
        raw=read_json(packet);raw['body']['build']['title']='Tampered packet';atomic_json(packet,raw)
        with self.assertRaisesRegex(ValueError,'hash|mismatch'):self.run_check()
        self.assertEqual(gameplay.proposal_reports(self.folder),[])

    def test_tampered_capture_stops_fix_before_discard_or_model_call(self):
        report=self.run_check()
        target=self.folder/'proposal-checks'/report['report_id']/'proposed/output/desktop.png';target.write_bytes(b'Changed image')
        self.assertEqual(self.app.snapshot()['build']['proposal_check']['state'],'stale')
        with patch('ember_harness.session_chat.run_muse') as model:
            with self.assertRaises(ValueError):
                self.app.request_changes(self.ref,'Fix the regression','fix-tampered-report-01',report['report_id'])
            model.assert_not_called()
        self.assertIsNone(self.app.snapshot()['build']['requests'][-1]['decision'])

    def test_fix_keeps_proposed_source_and_replays_same_context_after_restart(self):
        report=self.run_check();note='Fix the gameplay regression while preserving the proposal';turn='fix-proposal-report-01';prompts=[]
        def interrupted(*args,**kwargs):prompts.append(args[2]);raise ValueError('SYNTHETIC interrupted reply')
        with patch('ember_harness.session_chat.run_muse',side_effect=interrupted):
            with self.assertRaisesRegex(ValueError,'interrupted reply'):
                self.app.request_changes(self.ref,note,turn,report['report_id'])
        saved=transcript(self.folder)[-1]
        supplied=json.loads(prompts[0].split('\n',1)[1])
        self.assertEqual(supplied['proposal_context']['files'],self.files)
        self.assertEqual(supplied['proposal_context']['comparison'][0]['change'],'regression')
        self.assertNotIn(str(self.folder),json.dumps(supplied['proposal_context']))
        fresh=App(self.root);fresh.resume(self.sid)
        reply=dict(message='SYNTHETIC reviewed replacement',build=dict(title='Fixed proposal',summary='Preserve improvements and fix scoring',
            edits=[dict(path='index.html',before='SYNTHETIC_BROKEN',after='SYNTHETIC_FIXED')]))
        def finished(*args,**kwargs):prompts.append(args[2]);return dict(response=json.dumps(reply))
        with patch('ember_harness.session_chat.run_muse',side_effect=finished) as model:
            fresh.chat(saved['text'],turn)
            fresh.request_changes(self.ref,note,turn,report['report_id'])
            self.assertEqual(model.call_count,1)
        self.assertEqual(prompts[0],prompts[1])
        state=fresh.snapshot()['build'];self.assertEqual(len(state['completed']),1)
        self.assertEqual(state['requests'][-2]['decision']['choice'],'decline');self.assertIsNone(state['requests'][-1]['decision'])
        self.assertEqual(fresh.proposal_preview(self.sid,state['requests'][-1]['ref'])['manifest'],
                         {name:chat_build.sha256(content.replace('SYNTHETIC_BROKEN','SYNTHETIC_FIXED').encode()).hexdigest()
                          for name,content in self.files.items()})
        self.assertEqual(chat_build.context(self.root,self.folder)['files'],[dict(path=name,content=content) for name,content in sorted(build_fixture.PROJECT.items())])

    def test_http_authorization_and_session_binding(self):
        http=server(self.app);worker=threading.Thread(target=http.serve_forever,daemon=True);worker.start()
        self.addCleanup(worker.join);self.addCleanup(http.server_close);self.addCleanup(http.shutdown)
        url=f'http://127.0.0.1:{http.server_port}/api/proposal-check'
        for headers in ({'Content-Type':'application/json'},{'Content-Type':'application/json','X-Ember-Token':self.app.token,'Origin':'https://example.com'}):
            with self.assertRaises(HTTPError) as denied:urlopen(Request(url,data=b'{"request_ref":"denied"}',headers=headers),timeout=10)
            self.assertEqual(denied.exception.code,403)
        self.app.start('Other session',new_session=True,chat_only=True)
        body=json.dumps(dict(session_id=self.sid,revision=1,request_ref=self.ref,report_id='proposal-wrong-session-01')).encode()
        with self.assertRaises(HTTPError) as stale:
            urlopen(Request(url,data=body,headers={'Content-Type':'application/json','X-Ember-Token':self.app.token}),timeout=10)
        self.assertEqual(stale.exception.code,400)
