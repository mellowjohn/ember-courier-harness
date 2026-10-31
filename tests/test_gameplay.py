"""Synthetic fixtures for owner-editable plans and host-bound browser results."""
from copy import deepcopy
import json
import math
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import test_chat_build as fixture
from ember_harness import chat_build, gameplay, polish
from ember_harness.core import digest
from ember_harness.local_ui import App, server
from ember_harness.recovery import atomic_json, exclusive, read_json


PLAN = dict(title='Counter controls', scenarios=[dict(name='Start and score', viewport='desktop', steps=[
    dict(action='click', selector='button'), dict(action='number_at_least', selector='#counter', value=1)])])


def result(plan, failed=False):
    return dict(plan_sha256=digest(plan), outcome='failed' if failed else 'passed', scenarios=[
        dict(name=s['name'], viewport=s['viewport'], outcome='failed' if failed else 'passed', errors=[], steps=[
            dict(index=i, status='failed' if failed and i == len(s['steps'])-1 else 'passed', observed='SYNTHETIC observation')
            for i in range(len(s['steps']))]) for s in plan['scenarios']])


class GameplayTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ChatBuildTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.folder, self.app, self.sid = self.fixture.root, self.fixture.folder, self.fixture.app, self.fixture.sid
        self.ref = self.fixture.propose_project()
        self.app.respond(self.ref, 'approve', 'SYNTHETIC TEST: initial game')

    def save(self, plan=None, revision=0):
        return self.app.save_gameplay(self.sid, PLAN if plan is None else plan, revision)

    def inspect(self, runtime, source, output, **kwargs):
        output.mkdir(parents=True, exist_ok=True)
        data = read_json(source)
        report = dict(complete=True, gameplay=result(data['gameplay_plan']))
        atomic_json(output/'report.json', report)
        return report

    def run_plan(self, report_id='gameplay-test-report-01', revision=1):
        with patch('ember_harness.polish_runtime.discover', return_value={}), patch('ember_harness.polish_runtime.inspect', side_effect=self.inspect):
            return self.app.run_gameplay(self.sid, revision, self.ref, report_id)

    def test_persistence_cas_isolation_and_empty_plan(self):
        saved = self.save()
        fresh = App(self.root); fresh.resume(self.sid)
        self.assertEqual(fresh.snapshot()['gameplay_plan'], saved)
        with self.assertRaisesRegex(ValueError, 'another window'):
            self.save(revision=0)
        with exclusive(self.folder/'chat.lock'):
            with self.assertRaisesRegex(ValueError, 'already active'):
                self.save(revision=1)
        fresh.start('Other game', chat_only=True)
        self.assertEqual(fresh.snapshot()['gameplay_plan']['revision'], 0)
        with self.assertRaisesRegex(ValueError, 'intended session'):
            fresh.save_gameplay(self.sid, PLAN, 1)
        self.save(dict(title='No automated coverage', scenarios=[]), revision=1)
        with self.assertRaisesRegex(ValueError, 'nonempty'):
            self.run_plan(revision=2)

    def test_rejects_executable_selectors_unsupported_steps_and_unbounded_plans(self):
        invalid = [dict(action='evaluate', script='approve()'), dict(action='click', selector='body >> text=Approve'),
                   dict(action='press', key='Control+L'), dict(action='wait', ms=True), dict(action='wait', ms=2001),
                   dict(action='number_at_least', selector='#score', value=math.nan), dict(action='tap', selector='canvas'),
                   dict(action='visible', selector='*'), dict(action='text', selector='#score', value='x'*201)]
        for step in invalid:
            plan = deepcopy(PLAN); plan['scenarios'][0]['steps'].insert(0, step)
            with self.subTest(step=step), self.assertRaises(ValueError):
                self.save(plan)
        plan = deepcopy(PLAN); plan['scenarios'][0]['steps'] = [dict(action='click', selector='button')]
        with self.assertRaisesRegex(ValueError, 'assertion'):
            self.save(plan)
        plan = deepcopy(PLAN); plan['scenarios'] *= 4
        for scenario in plan['scenarios']:
            scenario['steps'] = [dict(action='wait', ms=2000)]*4+[dict(action='visible', selector='button')]
        with self.assertRaisesRegex(ValueError, 'budget'):
            self.save(plan)
        self.assertEqual(gameplay.load(self.folder)['revision'], 0)

    def test_host_report_binding_idempotence_and_no_authority_changes(self):
        self.save(); before = chat_build.harness(self.folder)._entries()
        saved = self.run_plan()
        again = self.run_plan()
        self.assertEqual(saved, again)
        self.assertEqual(saved['plan_sha256'], digest(PLAN))
        self.assertEqual(saved['outcome'], 'passed')
        self.assertEqual(len(gameplay.context(self.root, self.folder)['reports']), 1)
        entries = chat_build.harness(self.folder)._entries()
        self.assertEqual(len([e for e in entries if e['kind']=='chat_gameplay_recorded']), 1)
        for kind in ('approval', 'owner_decision', 'decision', 'chat_build_completed'):
            self.assertEqual([e for e in entries if e['kind']==kind], [e for e in before if e['kind']==kind])
        self.assertEqual(len(self.app.snapshot()['build']['completed']), 1)

    def test_wrong_plan_missing_steps_and_forged_pass_fail_closed(self):
        for change in ('hash', 'missing', 'pass'):
            report = result(PLAN, failed=True)
            if change == 'hash': report['plan_sha256'] = '0'*64
            if change == 'missing': report['scenarios'][0]['steps'].pop()
            if change == 'pass': report['outcome'] = 'passed'
            with self.subTest(change=change), self.assertRaises(ValueError):
                gameplay.validate_result(PLAN, report)
        with self.assertRaises(ValueError):
            gameplay.validate_result(PLAN, None)

    def test_changed_plan_or_version_during_run_cannot_record_current_result(self):
        self.save()
        original = self.inspect
        def change(runtime, source, output, **kwargs):
            response = original(runtime, source, output, **kwargs)
            self.save({**PLAN, 'title': 'New plan'}, revision=1)
            return response
        with patch('ember_harness.polish_runtime.discover', return_value={}), patch('ember_harness.polish_runtime.inspect', side_effect=change):
            with self.assertRaisesRegex(ValueError, 'changed during'):
                self.app.run_gameplay(self.sid, 1, self.ref, 'gameplay-stale-plan-01')
        self.assertEqual(gameplay.reports(self.folder), [])
        self.run_plan(revision=2)
        self.save({**PLAN, 'title': 'Third plan'}, revision=2)
        self.assertEqual(gameplay.context(self.root, self.folder)['reports'], [])
        self.assertEqual(len(gameplay.reports(self.folder)), 1)

    def test_changed_project_or_stale_version_is_not_inspected(self):
        self.save()
        self.fixture.target.write_text('External change', encoding='utf-8')
        with patch('ember_harness.polish_runtime.inspect') as browser:
            with self.assertRaises(ValueError):
                self.run_plan()
            browser.assert_not_called()

    def test_http_token_origin_session_and_model_context(self):
        http=server(self.app); worker=threading.Thread(target=http.serve_forever,daemon=True);worker.start()
        self.addCleanup(worker.join);self.addCleanup(http.server_close);self.addCleanup(http.shutdown)
        url=f'http://127.0.0.1:{http.server_port}/api/gameplay-plan'
        body=json.dumps(dict(session_id=self.sid,plan=PLAN,revision=0)).encode()
        for headers in ({'Content-Type':'application/json'}, {'Content-Type':'application/json','X-Ember-Token':self.app.token,'Origin':'https://example.com'}):
            with self.assertRaises(HTTPError) as denied:
                urlopen(Request(url,data=b'',headers=headers),timeout=10)
            self.assertEqual(denied.exception.code,403)
        with urlopen(Request(url,data=body,headers={'Content-Type':'application/json','X-Ember-Token':self.app.token}),timeout=10) as response:
            self.assertEqual(json.load(response)['revision'],1)
        before=chat_build.harness(self.folder)._entries()
        with patch('ember_harness.session_chat.run_muse',return_value=dict(response='A plan is guidance, never approval.')) as muse:
            self.app.chat('Keep these gameplay checks', 'gameplay-context-test-01')
        supplied=json.loads(muse.call_args.args[2].split('\n',1)[1])
        self.assertEqual(supplied['gameplay']['saved_plan']['plan'],PLAN)
        self.assertEqual(chat_build.harness(self.folder)._entries(),before)

    def test_saved_plan_damage_is_rejected(self):
        self.save(); saved=read_json(self.folder/'gameplay-plan.json');saved['plan']['title']='Edited outside the host'
        atomic_json(self.folder/'gameplay-plan.json',saved)
        with self.assertRaisesRegex(ValueError,'damaged'):
            gameplay.load(self.folder)

    def test_failed_gameplay_cannot_replace_a_clean_best(self):
        def candidate(index, score, failed=False):
            return dict(index=index,critique=dict(core_preserved=True,prefer_candidate=True,scores=dict(visual=score)),
                        observations=dict(viewports=[],gameplay=result(PLAN,failed=failed)))
        self.assertEqual(polish.choose_best([candidate(0,4),candidate(1,8),candidate(2,10,True)])['index'],1)
