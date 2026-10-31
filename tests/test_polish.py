"""Synthetic owner/provider fixtures exercise bounded, isolated overnight work."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch, Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

import test_chat_build as fixture
from ember_harness import chat_build, polish, polish_runtime
from ember_harness.core import content_hash, digest, timestamp
from ember_harness.local_ui import App, server
from ember_harness.muse_chat import CreditLedger
from ember_harness.recovery import atomic_json, read_json


def critique(score=5, *, preferred=False, preserved=True):
    return dict(summary='SYNTHETIC visual assessment', scores=dict.fromkeys(('visual', 'feel', 'clarity', 'cohesion'), score),
                core_preserved=preserved, prefer_candidate=preferred, wins=['Clearer button feedback'],
                problems=[], next_changes=['Improve spacing and easing'])


class PolishTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ChatBuildTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.folder, self.app = self.fixture.root, self.fixture.folder, self.fixture.app
        self.base = self.fixture.propose_project()
        self.app.respond(self.base, 'approve', 'SYNTHETIC TEST: initial game')
        self.binary = self.root / 'fake-muse.exe'
        self.binary.write_bytes(b'SYNTHETIC executable identity; never executed')
        self.runtime = dict(node=str(self.binary), browser=str(self.binary), module=str(self.root), driver=str(polish_runtime.DRIVER),
                            hashes=dict(node=polish_runtime.file_digest(self.binary), browser=polish_runtime.file_digest(self.binary),
                                        driver=polish_runtime.file_digest(polish_runtime.DRIVER)), module_hash='unused fixture')
        self.binary_patch = patch('ember_harness.polish.installed_binary', return_value=self.binary)
        self.runtime_patch = patch('ember_harness.polish_runtime.discover', return_value=self.runtime)
        self.binary_patch.start(); self.runtime_patch.start()
        self.addCleanup(self.binary_patch.stop); self.addCleanup(self.runtime_patch.stop)
        self.calls = []

    def prepare(self, **kwargs):
        return polish.prepare(self.root, self.folder, 'Polish feedback, visual hierarchy and animation; preserve the counter', **kwargs)['id']

    def approve(self, run_id):
        with patch('ember_harness.polish.launch', return_value=dict(status='ready')):
            return polish.respond(self.root, self.folder, run_id, 'approve', 'SYNTHETIC TEST: reviewed bounded polish scope')

    def model(self, root, folder, prompt, request_id, **kwargs):
        self.calls.append((request_id, kwargs))
        if request_id.startswith('critique'):
            result = critique(5 if request_id.endswith('-0') else 8, preferred=not request_id.endswith('-0'))
        else:
            files = {**fixture.PROJECT, 'style.css': 'body {background:#e2f2d5;color:#18251a;padding:24px} button {padding:16px;transition:transform .15s}'}
            result = dict(title='Polished counter', summary='Clearer hierarchy and responsive button feedback',
                          files=[dict(path=name, content=value) for name, value in files.items()])
        return dict(response=json.dumps(result))

    def browser(self, runtime, source, output, *, check):
        check()
        output = Path(output); output.mkdir(parents=True, exist_ok=True)
        rows = []
        for name in ('desktop', 'mobile'):
            for suffix in ('', '-before'):
                Image.new('RGB', (40, 30), '#556644').save(output / (name + suffix + '.png'))
            rows.append(dict(name=name, loaded=True, steps=['SYNTHETIC browser fixture'], observations=[],
                before=dict(text='Start', overflow=False), after=dict(text='Started', overflow=False, canvas=0),
                screenshot=name+'.png', sha256=polish_runtime.file_digest(output/(name+'.png')),
                before_screenshot=name+'-before.png', before_sha256=polish_runtime.file_digest(output/(name+'-before.png'))))
        result = dict(complete=True, input_sha256=polish_runtime.file_digest(source), viewports=rows, basis='SYNTHETIC fixture, not real browser evidence')
        atomic_json(output/'report.json', result)
        return result

    def run_worker(self, run_id):
        with patch('ember_harness.polish.run_muse', side_effect=self.model), patch('ember_harness.polish_runtime.inspect', side_effect=self.browser):
            polish.Worker(self.root, self.folder, run_id).run()

    def test_scope_review_then_isolated_iterations_and_separate_promotion(self):
        run_id = self.prepare(rounds=1)
        self.assertEqual(polish.history(self.root, self.folder)[0]['status'], 'awaiting_approval')
        with self.assertRaisesRegex(ValueError, 'Approve the exact'):
            polish.launch(self.root, self.folder, run_id)
        work, h, packet, plan = polish.load(self.folder, run_id)
        destination = chat_build.project(self.root, self.folder)
        self.assertNotIn(destination.as_posix() + '/**', packet['body']['contracts'][1]['contract']['allowed_paths']['write'])
        self.approve(run_id)
        self.run_worker(run_id)
        row = polish.history(self.root, self.folder)[0]
        self.assertEqual(row['status'], 'ready_review', row.get('error'))
        self.assertEqual(row['best_index'], 1)
        self.assertEqual(len(row['candidates']), 2)
        atomic_json(work/'state.json',dict(status='running',phase='Stale final heartbeat',error=None))
        self.assertEqual(polish.history(self.root,self.folder)[0]['status'],'ready_review')
        self.assertEqual([call[0] for call in self.calls], ['critique-0', 'generate-1', 'critique-1'])
        self.assertEqual([len(call[1]['images']) for call in self.calls], [2, 2, 4])
        self.assertEqual((destination/'style.css').read_text(), fixture.PROJECT['style.css'])
        self.assertEqual(len(self.app.snapshot()['build']['completed']), 1)
        approvals = [e for e in h._entries() if e['kind'] == 'owner_decision']
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0]['actor_type'], 'human')
        self.assertIn('data:text/css;base64', polish.preview(self.folder, run_id, 1)['html'])
        ref = polish.promote(self.root, self.folder, run_id, 1)['request_ref']
        self.assertIsNone(self.app.snapshot()['build']['requests'][-1]['decision'])
        self.assertEqual((destination/'style.css').read_text(), fixture.PROJECT['style.css'])
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: final exact polish diff')
        self.assertIn('transition', (destination/'style.css').read_text())
        self.assertEqual(len(self.app.snapshot()['build']['completed']), 2)

    def test_draft_decline_validation_stale_source_and_current_write_denied(self):
        for changes in (dict(rounds=True), dict(hours=13), dict(credits=4), dict(goal='')):
            with self.assertRaises((ValueError, TypeError)):
                polish.prepare(self.root, self.folder, **({'goal':'polish'}|changes))
        run_id = self.prepare(rounds=1)
        with self.assertRaisesRegex(ValueError, 'existing polish'):
            self.prepare()
        self.approve(run_id)
        worker = polish.Worker(self.root, self.folder, run_id)
        with self.assertRaisesRegex(ValueError, 'denied'):
            worker.write('escape', chat_build.project(self.root, self.folder)/'app.js', 'unapproved')
        polish.stop(self.root, self.folder, run_id)
        another = self.prepare(rounds=1)
        polish.respond(self.root, self.folder, another, 'decline', 'SYNTHETIC TEST: discard')
        with self.assertRaisesRegex(ValueError, 'Approve the exact|finished'):
            polish.launch(self.root, self.folder, another)

    def test_checkpoints_resume_without_repeating_model_or_gated_writes(self):
        run_id = self.prepare(rounds=1); self.approve(run_id)
        original = polish.Worker.candidate
        def crash(worker, index, build, best=None):
            if index == 1:
                raise OSError('SYNTHETIC interruption after saved generation')
            return original(worker, index, build, best)
        with patch.object(polish.Worker, 'candidate', crash):
            self.run_worker(run_id)
        self.assertEqual(polish.history(self.root, self.folder)[0]['status'], 'interrupted')
        self.assertEqual([c[0] for c in self.calls], ['critique-0', 'generate-1'])
        fresh = App(self.root); fresh.resume(self.fixture.sid)
        self.run_worker(run_id)
        self.assertEqual([c[0] for c in self.calls], ['critique-0', 'generate-1', 'critique-1'])
        work, h, _, _ = polish.load(self.folder, run_id)
        decisions = [digest(e['action']) for e in h._entries() if e['kind'] == 'decision' and e.get('decision') == 'allow']
        self.assertEqual(len(decisions), len(set(decisions)))
        self.assertEqual(polish.history(self.root, self.folder)[0]['status'], 'ready_review')

    def test_saved_provider_reply_replays_after_browser_data_round_trips_through_audit(self):
        run_id=self.prepare(rounds=1);self.approve(run_id)
        captures={};original_task=polish.Worker.task
        def cached(root,folder,prompt,phase,**kwargs):
            if phase in captures:
                original_prompt,result=captures[phase]
                self.assertEqual(prompt,original_prompt,'A restored context must keep the original cache binding')
                return result
            result=self.model(root,folder,prompt,phase,**kwargs);captures[phase]=(prompt,result)
            return result
        def interrupted_task(worker,phase,action_id,tool,args,reads,writes,artifact,perform):
            if phase=='critique-0':
                original_perform=perform
                def fail_after_capture():
                    original_perform()
                    raise OSError('SYNTHETIC interruption after captured provider reply')
                perform=fail_after_capture
            return original_task(worker,phase,action_id,tool,args,reads,writes,artifact,perform)
        with patch('ember_harness.polish.run_muse',side_effect=cached),patch('ember_harness.polish_runtime.inspect',side_effect=self.browser):
            with patch.object(polish.Worker,'task',interrupted_task):
                polish.Worker(self.root,self.folder,run_id).run()
            self.assertEqual(polish.history(self.root,self.folder)[0]['status'],'interrupted')
            polish.Worker(self.root,self.folder,run_id).run()
        self.assertEqual(polish.history(self.root,self.folder)[0]['status'],'ready_review')
        self.assertEqual([call[0] for call in self.calls],['critique-0','generate-1','critique-1'])

    def test_expired_window_and_exhausted_budget_end_with_retained_work(self):
        run_id=self.prepare(rounds=1);self.approve(run_id)
        worker=polish.Worker(self.root,self.folder,run_id)
        end=timestamp(worker.contract['limits']['time_window']['not_after'])
        worker.h.clock=lambda:end+timedelta(seconds=1)
        with patch('ember_harness.polish.run_muse') as model:
            worker.run();model.assert_not_called()
        row=polish.history(self.root,self.folder)[0]
        self.assertEqual(row['status'],'ready_review');self.assertIn('time window',row['phase'])
        run_id=self.prepare(rounds=2);self.approve(run_id)
        def limited(root,folder,prompt,phase,**kwargs):
            if phase=='generate-1':raise ValueError('Polish run credit budget cannot cover another request')
            return self.model(root,folder,prompt,phase,**kwargs)
        with patch('ember_harness.polish.run_muse',side_effect=limited),patch('ember_harness.polish_runtime.inspect',side_effect=self.browser):
            polish.Worker(self.root,self.folder,run_id).run()
        row=polish.history(self.root,self.folder)[0]
        self.assertEqual(row['status'],'ready_review');self.assertIn('Credit limit',row['phase'])
        self.assertEqual(len(row['candidates']),1);self.assertEqual(row['best_index'],0)

    def test_launch_is_a_detached_fixed_worker_and_unlisted_candidate_paths_are_denied(self):
        run_id=self.prepare(rounds=1);self.approve(run_id)
        process=Mock(poll=Mock(return_value=0))
        with patch('ember_harness.polish.subprocess.Popen',return_value=process) as launch:
            polish.launch(self.root,self.folder,run_id)
        args=launch.call_args.args[0]
        self.assertEqual(args[1:4],['-m','ember_harness.polish','--worker'])
        self.assertEqual(args[-1],run_id)
        self.assertEqual(launch.call_args.kwargs['cwd'],self.root)
        worker=polish.Worker(self.root,self.folder,run_id)
        with self.assertRaisesRegex(ValueError,'denied'):
            worker.write('unlisted',worker.work/'candidates/1/extra.js','/* unlisted */')
        self.assertFalse((worker.work/'candidates/1/extra.js').exists())

    def test_resumption_cannot_reuse_a_permission_after_the_contract_is_narrowed(self):
        run_id=self.prepare(rounds=1);self.approve(run_id)
        worker=polish.Worker(self.root,self.folder,run_id)
        target=worker.work/'candidates/1/app.js';content='/* interrupted candidate */'
        def interrupted():raise OSError('SYNTHETIC interruption after gate, before writing')
        with self.assertRaisesRegex(OSError,'after gate'):
            worker.task('interrupted-write','candidate-write','fs.write',dict(path=target.as_posix(),content=content),
                        [],[target.as_posix()],target,interrupted)
        paths=worker.contract['allowed_actions'][0]['args_constraints']['path']['one_of']
        result=worker.h.amend(worker.contract['id'],dict(reason='Remove one candidate path',round=1,
            source=dict(kind='review',id='SYNTHETIC-narrowing'),changes=[dict(op='replace',
                pointer='/allowed_actions/0/args_constraints/path/one_of',value=[p for p in paths if p!=target.as_posix()])]),
            proposed_by='synthetic-planner')
        narrowed=result['contract']
        worker.h.approve(narrowed['id'],narrowed['version'],approver='johnathan',quote='SYNTHETIC TEST: approve narrowing',
            expected_hash=content_hash(narrowed),parent_id=worker.packet['body']['contracts'][0]['contract']['id'])
        with self.assertRaisesRegex(ValueError,'authority changed'):
            worker.write('interrupted-write',target,content)
        self.assertFalse(target.exists())

    def test_failed_or_lower_rated_candidates_do_not_replace_the_best(self):
        def item(index, score, errors=0, preserved=True, preferred=True):
            return dict(index=index, critique=critique(score, preferred=preferred, preserved=preserved),
                        observations=dict(viewports=[dict(observations=['error']*errors, after=dict(overflow=False))]))
        original = item(0, 5)
        self.assertEqual(polish.choose_best([original, item(1, 10, errors=1), item(2, 9, preserved=False), item(3, 4)])['index'], 0)
        self.assertEqual(polish.choose_best([original, item(1, 8), item(2, 6)])['index'], 1)

    def test_stopping_expiry_budget_and_changed_inputs_do_not_keep_generating(self):
        run_id = self.prepare(rounds=2); self.approve(run_id)
        worker = polish.Worker(self.root, self.folder, run_id)
        polish.stop(self.root, self.folder, run_id)
        with patch('ember_harness.polish.run_muse') as muse:
            worker.run(); muse.assert_not_called()
        self.assertEqual(polish.history(self.root, self.folder)[0]['status'], 'ready_review')
        run_id = self.prepare(rounds=1); self.approve(run_id)
        work, _, _, _ = polish.load(self.folder, run_id)
        (work/'baseline.json').write_bytes(b'changed')
        self.run_worker(run_id)
        self.assertEqual(polish.history(self.root, self.folder)[0]['status'], 'interrupted')
        self.assertEqual(self.calls, [])

    def test_tampered_candidate_or_screenshot_and_stale_promotion_fail_closed(self):
        run_id = self.prepare(rounds=1); self.approve(run_id); self.run_worker(run_id)
        work = polish.run_folder(self.folder, run_id)
        screenshot = work/'captures/1/output/desktop.png'; original = screenshot.read_bytes(); screenshot.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'screenshot'):
            polish.promote(self.root, self.folder, run_id, 1)
        screenshot.write_bytes(original)
        self.fixture.target.write_bytes(b'External edit')
        with self.assertRaises(ValueError):
            polish.promote(self.root, self.folder, run_id, 1)
        (work/'candidates/1/app.js').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'artifact changed'):
            polish.preview(self.folder, run_id, 1)

    def test_run_budget_is_atomic_shared_and_cannot_expand_on_resume(self):
        ledger = CreditLedger(self.root)
        budget = dict(id='a'*64, limit_micro_usd=10_000_000)
        ledger.reserve('one', budget=budget); ledger.reserve('two', budget=budget)
        with self.assertRaisesRegex(ValueError, 'Polish run credit'):
            ledger.reserve('three', budget=budget)
        with self.assertRaisesRegex(ValueError, 'cannot be changed'):
            ledger.reserve('widen', budget={**budget,'limit_micro_usd':15_000_000})
        ledger.reserve('ordinary-chat')
        self.assertEqual(ledger.summary()['reserved_usd'], 15)
        self.assertEqual(ledger.budget_summary('a'*64)['reserved_usd'], 10)
        ledger.settle('one', 100, 10)
        with self.assertRaisesRegex(ValueError, 'Polish run credit'):
            ledger.reserve('three', budget=budget)
        ledger.settle('two', 100, 10)
        ledger.reserve('three', budget=budget)
        self.assertLessEqual(ledger.budget_summary('a'*64)['reserved_usd']+ledger.budget_summary('a'*64)['estimated_spent_usd'], 10)

    def test_concurrent_reservations_and_uncertain_usage_keep_the_run_ceiling(self):
        ledger = CreditLedger(self.root)
        budget = dict(id='b'*64, limit_micro_usd=5_000_000)
        barrier = threading.Barrier(2); outcomes=[]
        def reserve(name):
            barrier.wait()
            try:
                CreditLedger(self.root).reserve(name,budget=budget);outcomes.append('reserved')
            except ValueError:outcomes.append('denied')
        threads=[threading.Thread(target=reserve,args=(name,)) for name in ('first','second')]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(sorted(outcomes),['denied','reserved'])
        self.assertEqual(ledger.budget_summary('b'*64)['reserved_usd'],5)
        with self.assertRaises(ValueError):CreditLedger(self.root).reserve('after-restart',budget=budget)
        data=ledger.read(); next(iter(data['requests'].values()))['charged_micro_usd']=0
        atomic_json(ledger.path,data)
        with self.assertRaisesRegex(ValueError,'uncertain'):ledger.read()

    def test_http_scope_and_artifacts_require_private_authorization_and_session(self):
        http = server(self.app); thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
        self.addCleanup(thread.join); self.addCleanup(http.server_close); self.addCleanup(http.shutdown)
        base = 'http://127.0.0.1:'+str(http.server_port)
        def call(body, token=True, origin=None):
            headers={'Content-Type':'application/json'}
            if token: headers['X-Ember-Token']=self.app.token
            if origin: headers['Origin']=origin
            with urlopen(Request(base+'/api/polish',data=json.dumps(body).encode(),headers=headers)) as response:
                return json.load(response)
        body=dict(session_id=self.fixture.sid, action='prepare', goal='polish', rounds=1, hours=1, credits=10)
        for kwargs in (dict(token=False),dict(origin='https://example.org')):
            with self.assertRaises(HTTPError) as error: call(body,**kwargs)
            self.assertEqual(error.exception.code,403)
        with self.assertRaises(HTTPError): call({**body,'session_id':'f'*24})
        run_id=call(body)['id']
        with self.assertRaises(HTTPError) as error:
            urlopen(base+'/api/polish-preview?session_id='+self.fixture.sid+'&run_id='+run_id+'&index=0')
        self.assertEqual(error.exception.code,403)


if __name__ == '__main__':
    unittest.main()
