"""Persistent scopes bind exact builds and human task outcomes, not model claims."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from unittest.mock import patch

from ember_harness import chat_build, project_plan, project_versions, session_chat
from ember_harness.core import content_hash, subset
from ember_harness.local_ui import App
from ember_harness.recovery import exclusive

ROOT = Path(__file__).resolve().parents[1]
HTML = '<html><body><h1>Courier project</h1><button>Deliver</button></body></html>'


class ProjectPlanTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=scratch); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); (self.root / 'examples').mkdir()
        (self.root / 'examples/product_demo.py').touch()
        self.app = App(self.root); self.app.start('SYNTHETIC planned project', chat_only=True)
        self.sid = self.app.session['id']; self.folder = self.app.sessions_dir / self.sid
        self.document = project_plan.starter(self.folder)
        self.document['scope'].update(game_concept='Original parcel courier', core_loop='Pick up, deliver, restart',
            features=['Core delivery loop', 'Keyboard and touch controls'], out_of_scope=['Combat', 'Multiplayer'],
            done_criteria=['Deliver a parcel and restart', 'Human playtest and accepted assets'])

    def prepare(self, document=None):
        saved = project_plan.status(self.root, self.folder)
        with redirect_stdout(io.StringIO()):
            return self.app.plan_control(self.sid, 'prepare', document=document or self.document, expected_ref=saved['latest_ref'])['request_ref']

    def approve(self):
        ref = self.prepare()
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: approve full project scope')
        return ref

    def propose_build(self, turn='project-build-0001', html=HTML, binding=None):
        with redirect_stdout(io.StringIO()):
            return chat_build.propose_build(self.root, self.folder, turn, 'SYNTHETIC selected task',
                dict(title='Courier task', summary='Implement the selected task', files=[dict(path='index.html', content=html)]),
                expected_before=chat_build.context(self.root, self.folder)['sha256'],
                **(dict(project_scope=binding) if binding is not None else {}))

    def apply_build(self, **kw):
        ref = self.propose_build(**kw)
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: approve exact task build')
        return ref

    def test_plan_review_approval_restart_and_task_list_without_project_writes(self):
        self.assertFalse(project_plan.status(self.root, self.folder)['managed'])
        ref = self.prepare(); pending = project_plan.status(self.root, self.folder)
        self.assertEqual(pending['pending']['ref'], ref); self.assertIsNone(pending['approved'])
        self.assertFalse(chat_build.list_requests(self.folder)); self.assertFalse(chat_build.project(self.root, self.folder).exists())
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: approve scope, not files')
        saved = project_plan.status(self.root, self.folder)
        self.assertTrue(saved['active']); self.assertEqual(saved['selected_task'], 'task-1')
        self.assertEqual([t['title'] for t in saved['tasks']], self.document['scope']['features'])
        self.assertFalse(chat_build.project(self.root, self.folder).exists())
        fresh = App(self.root); state = fresh.resume(self.sid)
        self.assertEqual(state['project_plan'], saved)
        self.assertEqual(state['build']['requests'], [])
        self.assertEqual(state['requests'][0]['origin'], 'project_plan')

    def test_builds_share_the_approved_root_inherit_art_and_export_verified_versions(self):
        plan_ref = self.approve(); first = self.apply_build()
        second = self.apply_build(turn='project-build-0002', html=HTML.replace('Deliver', 'Deliver now'))
        state = project_plan.status(self.root, self.folder); h = chat_build.harness(self.folder)
        root = h._load(h._active(h._entries())[state['approved']['contract_id']])
        for row in chat_build.list_requests(self.folder):
            body = row['payload']['body']; child = body['contracts'][-1]['contract']
            self.assertEqual(len(body['contracts']), 1)
            self.assertEqual(body['contracts'][0]['parent_id'], root['id'])
            self.assertEqual(body['build']['project_scope']['ref'], plan_ref)
            self.assertEqual(child['art_direction'], root['art_direction']); self.assertTrue(subset(child, root))
        roots = [e for e in h._entries() if e['kind'] == 'approval' and e.get('role') == 'scope']
        self.assertEqual(len(roots), 1)
        self.assertEqual(state['tasks'][0]['state'], 'applied_needs_review')
        self.assertEqual(project_versions.snapshot(self.root, self.folder, first)['files']['index.html'], HTML)
        self.assertIn(b'index.html', project_versions.export(self.root, self.folder, second)[0])
        self.assertTrue(chat_build.verify(self.root, self.folder)['passed'])

    def test_task_acceptance_requires_latest_applied_exact_outcome_and_is_not_auto_completion(self):
        plan_ref = self.approve()
        with self.assertRaises(ValueError):
            self.app.plan_control(self.sid, 'accept', plan_ref=plan_ref, task_id='task-1', build_ref='f'*64)
        first = self.apply_build()
        self.assertIsNone(project_plan.status(self.root, self.folder)['tasks'][0]['acceptance'])
        self.app.plan_control(self.sid, 'accept', plan_ref=plan_ref, task_id='task-1', build_ref=first)
        saved = project_plan.status(self.root, self.folder)
        self.assertEqual(saved['tasks'][0]['state'], 'human_accepted')
        self.assertEqual(saved['tasks'][1]['state'], 'planned')
        self.app.plan_control(self.sid, 'select', plan_ref=plan_ref, task_id='task-2')
        second = self.apply_build(turn='task-two-build-0001', html=HTML.replace('Deliver', 'Deliver with arrows'))
        self.assertEqual(chat_build.list_requests(self.folder)[-1]['payload']['body']['build']['project_scope']['task_id'], 'task-2')
        with self.assertRaisesRegex(ValueError, 'latest completed'):
            self.app.plan_control(self.sid, 'accept', plan_ref=plan_ref, task_id='task-1', build_ref=first)
        target = chat_build.project(self.root, self.folder)/'index.html'; target.write_text(HTML.replace('Courier project','Externally edited'))
        with self.assertRaisesRegex(ValueError, 'Project files changed'):
            self.app.plan_control(self.sid, 'accept', plan_ref=plan_ref, task_id='task-2', build_ref=second)

    def test_plan_amendment_needs_separate_ack_and_stales_old_bindings(self):
        first = self.approve(); frozen = project_plan.context(self.root, self.folder)['binding']
        changed = deepcopy(self.document); changed['scope']['features'].append('Delivery streak')
        ref = self.prepare(changed)
        with self.assertRaisesRegex(ValueError, 'widening_ack'):
            self.app.respond(ref, 'approve', 'SYNTHETIC TEST: must require separate acknowledgement')
        self.assertEqual(project_plan.status(self.root, self.folder)['approved']['ref'], first)
        self.app.plan_control(self.sid, 'acknowledge', ref=ref)
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: accept reviewed amendment')
        saved = project_plan.status(self.root, self.folder)
        self.assertEqual(saved['approved']['version'], 2); self.assertEqual(len(saved['tasks']), 3)
        with self.assertRaisesRegex(ValueError, 'scope changed'): self.propose_build(binding=frozen)
        self.assertFalse(chat_build.list_requests(self.folder))

    def test_pending_scope_and_revocation_cannot_fall_back_to_per_build_roots(self):
        ref = self.prepare()
        with self.assertRaises(ValueError): self.propose_build()
        self.app.respond(ref, 'decline', 'SYNTHETIC TEST: decline scope')
        with self.assertRaises(ValueError): self.propose_build()
        plan_ref = self.approve(); saved = project_plan.status(self.root, self.folder)
        chat_build.harness(self.folder).revoke(saved['approved']['contract_id'], approver='johnathan', reason='SYNTHETIC TEST: revoked scope')
        with self.assertRaisesRegex(ValueError, 'inactive'): self.propose_build()
        with self.assertRaisesRegex(ValueError, 'revoked'): self.prepare()
        self.assertFalse(chat_build.project(self.root, self.folder).exists())

    def test_amended_or_revoked_scope_preserves_read_only_build_verification(self):
        from ember_harness import gameplay
        import test_gameplay as checks
        self.approve();ref=self.apply_build()
        frozen=project_plan.context(self.root,self.folder)['binding']
        changed=deepcopy(self.document);changed['scope']['features'].append('Two parcels per dispatch')
        amendment=self.prepare(changed)
        self.app.plan_control(self.sid,'acknowledge',ref=amendment)
        self.app.respond(amendment,'approve','SYNTHETIC TEST: reviewed successor scope')
        h=chat_build.harness(self.folder);before=h._entries()
        self.assertTrue(chat_build.verify(self.root,self.folder)['passed'])
        self.assertEqual(before,h._entries())
        self.assertEqual(project_versions.snapshot(self.root,self.folder,ref)['files']['index.html'],HTML)
        with self.assertRaisesRegex(ValueError,'scope changed'):self.propose_build(binding=frozen)
        gameplay.save(self.folder,checks.PLAN,0)
        with patch('ember_harness.polish_runtime.discover',return_value={}),patch('ember_harness.gameplay._capture',return_value=dict(gameplay=checks.result(checks.PLAN))):
            # Use a saved output just as the host capture adapter normally does.
            from ember_harness.recovery import atomic_json
            output=self.folder/'gameplay-runs/amended-build-check-01/output';output.mkdir(parents=True)
            atomic_json(output/'report.json',dict(gameplay=checks.result(checks.PLAN)))
            report=gameplay.run_current(self.root,self.folder,1,ref,'amended-build-check-01')
        self.assertEqual(report['outcome'],'passed')
        active=project_plan.status(self.root,self.folder)['approved']['contract_id']
        h.revoke(active,approver='johnathan',reason='SYNTHETIC TEST: stop future work')
        self.assertTrue(chat_build.verify(self.root,self.folder)['passed'])
        with self.assertRaisesRegex(ValueError,'inactive'):self.propose_build()
        target=chat_build.project(self.root,self.folder)/'index.html';target.write_text('External tamper',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'changed'):chat_build.verify(self.root,self.folder)

    def test_acceptance_prepares_next_review_once_and_survives_reload(self):
        plan_ref = self.approve(); first = self.apply_build()
        def prepare(root, folder):
            saved = project_plan.status(root, folder)
            self.assertEqual(saved['selected_task'], 'task-2')
            self.assertEqual(saved['tasks'][0]['state'], 'human_accepted')
            self.assertIsNone(saved['tasks'][1]['acceptance'])
            return dict(id='a'*24, request_ref='b'*64)
        with patch('ember_harness.task_run.prepare', side_effect=prepare) as preparation, patch('ember_harness.task_run.launch') as launch:
            result = self.app.plan_control(self.sid, 'accept', plan_ref=plan_ref, task_id='task-1', build_ref=first)
            self.app.plan_control(self.sid, 'accept', plan_ref=plan_ref, task_id='task-1', build_ref=first)
            self.assertEqual(preparation.call_count, 1)
            launch.assert_not_called()
        self.assertEqual(result['continuation']['status'], 'awaiting_approval')
        saved = App(self.root).resume(self.sid)['project_plan']
        self.assertEqual(saved['selected_task'], 'task-2')
        self.assertEqual(saved['continuation']['run_id'], 'a'*24)

    def test_next_preparation_failure_keeps_acceptance_and_explains_the_blocker(self):
        plan_ref = self.approve(); first = self.apply_build()
        with patch('ember_harness.task_run.prepare', side_effect=ValueError('SYNTHETIC missing gameplay checks')):
            result = self.app.plan_control(self.sid, 'accept', plan_ref=plan_ref, task_id='task-1', build_ref=first)
        self.assertEqual(result['status'], 'human_accepted')
        saved = project_plan.status(self.root,self.folder)
        self.assertEqual(saved['selected_task'], 'task-2')
        self.assertEqual(saved['tasks'][0]['state'], 'human_accepted')
        self.assertEqual(saved['continuation']['status'], 'blocked')
        self.assertIn('missing gameplay checks', saved['continuation']['reason'])

    def test_plan_changes_are_blocked_by_pending_builds_and_active_chat(self):
        self.approve(); build = self.propose_build()
        with self.assertRaisesRegex(ValueError, 'pending build'): self.prepare()
        self.app.respond(build, 'decline', 'SYNTHETIC TEST: decline task proposal')
        with exclusive(self.folder/'chat.lock'), self.assertRaises(ValueError): self.prepare()

    def test_stale_window_invalid_design_and_wrong_session_do_not_change_plan(self):
        ref = self.prepare()
        for document in ({**self.document, 'approved_by':'johnathan'}, {**self.document, 'scope':{**self.document['scope'], 'asset_budget':{'a':-1}}}):
            with self.assertRaises(Exception): self.prepare(document)
        with self.assertRaisesRegex(ValueError, 'another window'):
            self.app.plan_control(self.sid, 'prepare', document=self.document, expected_ref=None)
        with self.assertRaisesRegex(ValueError, 'intended session'):
            self.app.plan_control('f'*24, 'select', plan_ref=ref, task_id='task-1')
        self.assertEqual(len(project_plan.requests(self.folder)), 1)

    def test_chat_receives_frozen_project_task_and_cannot_claim_completion(self):
        plan_ref = self.approve()
        def model(root, folder, prompt, turn, **kw):
            data = json.loads(prompt.split('\n',1)[1]); saved = data['project_plan']
            self.assertEqual(saved['binding']['ref'], plan_ref)
            self.assertEqual(saved['selected_task'], 'task-1')
            self.assertEqual(saved['document']['scope']['out_of_scope'], ['Combat','Multiplayer'])
            return dict(response=json.dumps(dict(message='SYNTHETIC proposal; not tested', build=dict(title='Task one', summary='Courier', files=[dict(path='index.html',content=HTML)]))))
        with patch('ember_harness.session_chat.run_muse', side_effect=model), redirect_stdout(io.StringIO()):
            self.app.chat('Work on the active task', 'planned-chat-turn-0001')
        self.assertEqual(project_plan.status(self.root,self.folder)['tasks'][0]['state'], 'awaiting_review')
        self.assertEqual(session_chat.transcript(self.folder)[0]['project_plan_snapshot']['binding']['ref'], plan_ref)
        self.assertFalse(chat_build.project(self.root,self.folder).exists())

    def test_chat_prepares_plan_and_amendment_without_approving_or_writing_game(self):
        result = dict(message='Review this project plan.', build=None, plan=self.document,
                      brief_updates=dict(goal=self.document['scope']['game_concept']))
        with patch('ember_harness.session_chat.run_muse', return_value=dict(response=json.dumps(result))), redirect_stdout(io.StringIO()):
            self.app.chat('Prepare this project plan for review', 'plan-from-chat-0001')
            self.app.chat('Prepare this project plan for review', 'plan-from-chat-0001')
        saved = project_plan.status(self.root, self.folder)
        ref = saved['pending']['ref']
        self.assertEqual(session_chat.transcript(self.folder)[-1]['plan_ref'], ref)
        self.assertFalse(saved['active'])
        self.assertEqual(len(project_plan.requests(self.folder)), 1)
        self.assertFalse(chat_build.project(self.root, self.folder).exists())
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: review conversational plan')
        changed = deepcopy(self.document)
        changed['scope']['features'].append('Parcel delivery streak')
        result.update(plan=changed, brief_updates=None)
        with patch('ember_harness.session_chat.run_muse', return_value=dict(response=json.dumps(result))), redirect_stdout(io.StringIO()):
            self.app.chat('Add a delivery streak to the plan', 'plan-from-chat-0002')
        state = App(self.root).resume(self.sid)['project_plan']
        self.assertEqual(state['approved']['document'], self.document)
        self.assertEqual(state['pending']['payload']['body']['project_plan']['document'], changed)
        self.assertFalse(state['pending']['widening_acknowledged'])
        self.assertEqual(state['approved']['version'], 1)
        self.assertFalse(chat_build.project(self.root, self.folder).exists())

    def test_chat_discussion_and_renewal_available_when_scope_expired(self):
        self.approve()
        h = chat_build.harness(self.folder)
        h.clock = lambda: datetime.now(timezone.utc) + timedelta(days=2)
        result = dict(message='We can renew this plan for your review.', build=None, plan=self.document)
        with patch('ember_harness.project_plan.authority', return_value=h), \
                patch('ember_harness.session_chat.run_muse', return_value=dict(response=json.dumps(result))), redirect_stdout(io.StringIO()):
            self.app.chat('Renew my project plan', 'plan-expired-chat-0001')
        self.assertIsNotNone(project_plan.status(self.root, self.folder)['pending'])
        self.assertEqual(chat_build.list_requests(self.folder), [])

    def test_chat_plan_and_brief_recover_together_without_duplicate_reviews(self):
        result = dict(message='Review your project plan.', build=None, plan=self.document,
                      brief_updates=dict(goal='Original parcel courier'))
        from ember_harness.recovery import atomic_json as write
        def interrupted(path, data):
            if Path(path).name == 'chat.json' and any(m['role'] == 'assistant' for m in data):
                raise KeyboardInterrupt('SYNTHETIC process death after preparing plan')
            return write(path, data)
        with patch('ember_harness.session_chat.run_muse', return_value=dict(response=json.dumps(result))), redirect_stdout(io.StringIO()):
            with patch('ember_harness.session_chat.atomic_json', side_effect=interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    self.app.chat('Prepare the project plan', 'plan-chat-recovery-0001')
            self.assertEqual(len(project_plan.requests(self.folder)), 1)
            self.app.chat('Prepare the project plan', 'plan-chat-recovery-0001')
        saved = self.app.snapshot()
        self.assertEqual(saved['project_brief']['revision'], 1)
        self.assertEqual(len(project_plan.requests(self.folder)), 1)
        self.assertEqual(saved['messages'][-1]['plan_ref'], saved['project_plan']['pending']['ref'])

    def test_chat_cannot_combine_plan_proposal_with_build_or_replace_pending_review(self):
        result = dict(message='Proposed', plan=self.document,
            build=dict(title='Premature implementation', summary='Must be rejected',
                       files=[dict(path='index.html', content=HTML)]))
        with patch('ember_harness.session_chat.run_muse', return_value=dict(response=json.dumps(result))):
            with self.assertRaisesRegex(ValueError, 'Review the project plan'):
                self.app.chat('Prepare plan and build', 'plan-combined-chat-0001')
        self.assertEqual(project_plan.requests(self.folder), [])
        self.assertEqual(chat_build.list_requests(self.folder), [])
        ref = self.prepare()
        result['build'] = None
        with patch('ember_harness.session_chat.run_muse', return_value=dict(response=json.dumps(result))):
            with self.assertRaisesRegex(ValueError, 'pending project plan'):
                self.app.chat('Prepare another plan', 'plan-pending-chat-0001')
        self.assertEqual(project_plan.status(self.root, self.folder)['pending']['ref'], ref)

    def test_retry_against_a_changed_scope_stops_before_another_model_call(self):
        self.approve()
        with patch('ember_harness.session_chat.run_muse', side_effect=ValueError('SYNTHETIC interruption')):
            with self.assertRaises(ValueError): self.app.chat('Build the task', 'planned-retry-0001')
        changed=deepcopy(self.document); changed['scope']['core_loop']='Pick up, deliver, count and restart'
        ref=self.prepare(changed); self.app.plan_control(self.sid,'acknowledge',ref=ref)
        self.app.respond(ref,'approve','SYNTHETIC TEST: amend scope between requests')
        with patch('ember_harness.session_chat.run_muse') as model:
            with self.assertRaisesRegex(ValueError,'scope changed'): self.app.chat('Build the task','planned-retry-0001')
            model.assert_not_called()

    def test_expired_scope_and_changed_approved_bytes_stop_before_any_new_build(self):
        self.approve(); saved=project_plan.status(self.root,self.folder)
        h=chat_build.harness(self.folder); h.clock=lambda: datetime.now(timezone.utc)+timedelta(days=2)
        with patch('ember_harness.project_plan.authority',return_value=h):
            with self.assertRaisesRegex(ValueError,'expired'):self.propose_build()
        path=h._path(saved['approved']['contract_id'],saved['approved']['version'])
        data=json.loads(path.read_text());data['art_direction']['style']='Tampered style';path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'scope changed'):self.propose_build()
        self.assertFalse(chat_build.list_requests(self.folder))

    def test_retry_preserves_selected_task_even_if_selection_changes(self):
        plan_ref=self.approve()
        with patch('ember_harness.session_chat.run_muse',side_effect=ValueError('SYNTHETIC interrupted reply')):
            with self.assertRaises(ValueError):self.app.chat('Implement selected task','task-context-retry-0001')
        self.app.plan_control(self.sid,'select',plan_ref=plan_ref,task_id='task-2')
        def reply(root,folder,prompt,turn,**kw):
            self.assertEqual(json.loads(prompt.split('\n',1)[1])['project_plan']['selected_task'],'task-1')
            return dict(response=json.dumps(dict(message='SYNTHETIC saved task',build=dict(title='Original task',summary='Original selected task',files=[dict(path='index.html',content=HTML)]))))
        with patch('ember_harness.session_chat.run_muse',side_effect=reply),redirect_stdout(io.StringIO()):
            self.app.chat('Implement selected task','task-context-retry-0001')
        self.assertEqual(chat_build.list_requests(self.folder)[0]['payload']['body']['build']['project_scope']['task_id'],'task-1')

    def test_plan_http_routes_require_host_authorization_and_keep_pending_bytes(self):
        from ember_harness.local_ui import server
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        import threading
        http=server(self.app);worker=threading.Thread(target=http.serve_forever,daemon=True);worker.start()
        self.addCleanup(worker.join);self.addCleanup(http.server_close);self.addCleanup(http.shutdown)
        base=f'http://127.0.0.1:{http.server_port}'
        body=dict(session_id=self.sid,action='prepare',document=self.document,expected_ref=None)
        def post(token=True,origin=None):
            headers={'Content-Type':'application/json'}
            if token:headers['X-Ember-Token']=self.app.token
            if origin:headers['Origin']=origin
            with urlopen(Request(base+'/api/project-plan',data=json.dumps(body).encode(),headers=headers)) as response:return json.load(response)
        for kwargs in (dict(token=False),dict(origin='https://example.org')):
            with self.assertRaises(HTTPError) as denied:post(**kwargs)
            self.assertEqual(denied.exception.code,403)
        with redirect_stdout(io.StringIO()):result=post()
        self.assertEqual(result['status'],'awaiting_review')
        self.assertFalse(chat_build.project(self.root,self.folder).exists())

    def test_asset_changes_and_restores_use_the_persistent_scope_and_individual_receipts(self):
        from test_asset_pipeline import glb,SPEC
        from ember_harness import asset_pipeline,asset_workshop
        self.approve()
        package=asset_pipeline.package(glb(),SPEC)
        files=asset_workshop.assemble(package,'/* SYNTHETIC runtime, not executed */')
        with redirect_stdout(io.StringIO()):
            first=chat_build.propose_build(self.root,self.folder,'planned-asset-0001','SYNTHETIC asset task',
                dict(title='Planned prop',summary='Review exact asset',files=[dict(path=k,content=v) for k,v in files.items()]))
        self.app.respond(first,'approve','SYNTHETIC TEST: accept asset within project scope')
        original=project_plan.status(self.root,self.folder)['approved']['document']['art_direction']
        self.assertEqual(chat_build.list_requests(self.folder)[-1]['payload']['body']['contracts'][0]['contract']['art_direction'],original)
        files['style.css']+='\n/* SYNTHETIC revision */'
        with redirect_stdout(io.StringIO()):
            second=chat_build.propose_build(self.root,self.folder,'planned-asset-0002','SYNTHETIC code revision',
                dict(title='Scene revision',summary='Keep asset',files=[dict(path=k,content=v) for k,v in files.items()]),expected_before=chat_build.context(self.root,self.folder)['sha256'])
        self.app.respond(second,'approve','SYNTHETIC TEST: accept scene revision')
        with redirect_stdout(io.StringIO()):restore=project_versions.propose_restore(self.root,self.folder,first,second,'planned-restore-0001')
        self.app.respond(restore,'approve','SYNTHETIC TEST: restore planned asset scene')
        receipts=[e for e in chat_build.harness(self.folder)._entries() if e['kind']=='decision' and e.get('decision')=='allow' and e.get('action',{}).get('tool')=='asset.accept']
        self.assertEqual(len(receipts),1)
        self.assertEqual(project_versions.snapshot(self.root,self.folder,restore)['files']['asset.js'],package)


if __name__ == '__main__': unittest.main()
