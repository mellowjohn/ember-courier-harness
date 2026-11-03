"""Imported snapshots enter normal scoped exact builds, never implicit acceptance."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import test_workspace_import as imports
from ember_harness import asset_2d, asset_pipeline, chat_build, project_plan, workspace
from ember_harness.local_ui import server
from tools.browser_check import synthetic_provider_guard


class WorkspaceAdoptionTests(unittest.TestCase):
    def setUp(self):
        quiet = redirect_stdout(io.StringIO()); quiet.__enter__(); self.addCleanup(quiet.__exit__, None, None, None)
        self.fixture = imports.WorkspaceImportTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.app = self.fixture.fixture.app
        self.root, self.folder = self.fixture.fixture.root, self.fixture.folder
        self.sid = self.folder.name
        guard = synthetic_provider_guard(); guard.__enter__(); self.addCleanup(guard.__exit__, None, None, None)

    def scope(self):
        document = project_plan.starter(self.folder)
        document['scope']['features'] = ['Import and play the original browser counter']
        ref = project_plan.prepare(self.root, self.folder, document, None)['request_ref']
        self.app.respond(ref, 'approve', 'SYNTHETIC approved project scope')
        return ref

    def copied(self):
        self.fixture.copy()
        return self.fixture.fixture.saved()['run_id']

    def promote(self, run_id, **body):
        return self.app.workspace_control(self.sid, 'promote_import', run_id=run_id,
            **(dict(expected_manifest=chat_build.context(self.root, self.folder)['manifest']) | body))['request_ref']

    def test_scoped_exact_adoption_idempotency_stale_base_and_separate_acceptance(self):
        run = self.copied()
        with self.assertRaisesRegex(ValueError, 'Approve a project plan'):
            self.promote(run)
        plan = self.scope()
        original_source = self.fixture.fixture.files()
        first = self.promote(run)
        self.assertEqual(self.promote(run), first)
        self.assertFalse(chat_build.context(self.root, self.folder)['files'])
        self.app.respond(first, 'decline', 'SYNTHETIC discarded import review')
        with self.assertRaisesRegex(ValueError, 'discarded|declined|decided'):
            self.promote(run)
        second = self.promote(run, operation_id='fresh-import-review-12345678')
        self.assertNotEqual(second, first)
        self.app.respond(second, 'approve', 'SYNTHETIC exact imported game')
        self.assertEqual({f['path']: f['content'] for f in chat_build.context(self.root, self.folder)['files']}, imports.PROJECT)
        self.assertIsNone(project_plan.status(self.root, self.folder)['tasks'][0]['acceptance'])
        self.app.plan_control(self.sid, 'accept', plan_ref=plan, task_id='task-1', build_ref=second)
        self.assertTrue(project_plan.status(self.root, self.folder)['tasks'][0]['acceptance'])
        revised = imports.PROJECT | {'style.css': 'body{background:#456;color:#fff}'}
        ref = chat_build.propose_build(self.root, self.folder, 'synthetic-later-revision', 'Change only the palette',
            dict(title='Later revision', summary='SYNTHETIC reviewed change', files=[dict(path=k, content=v) for k,v in revised.items()]),
            expected_before=chat_build.context(self.root, self.folder)['sha256'])
        self.app.respond(ref, 'approve', 'SYNTHETIC later current game')
        with self.assertRaisesRegex(ValueError, 'current game changed'):
            self.promote(run, expected_manifest={})
        third = self.promote(run)
        self.assertNotIn(third, (first, second))
        self.assertEqual(self.fixture.fixture.files(), original_source)
        self.assertEqual({f['path']:f['content'] for f in chat_build.context(self.root,self.folder)['files']}, revised)

    def test_copied_asset_keeps_individual_acceptance_in_exact_build_review(self):
        spec = asset_2d.effect_spec()
        package = asset_pipeline.package(asset_2d.render_effect(spec), spec)
        self.assertLess(len(package.encode()), workspace.MAX_READ)
        (self.fixture.source/'asset.js').write_bytes(package.encode())
        run = self.copied(); self.scope()
        ref = self.promote(run)
        h = chat_build.harness(self.folder)
        body = chat_build.list_requests(self.folder)[-1]['payload']['body']
        self.assertEqual(len(body['asset_actions']), 1)
        self.assertEqual(body['asset_actions'][0]['tool'], 'asset.accept')
        self.assertFalse(any(e['kind']=='decision' and e.get('action',{}).get('tool')=='asset.accept' and e.get('decision')=='allow'
                             for e in h._entries()))
        with self.assertRaisesRegex(ValueError, 'approval'):
            chat_build.resume(self.root, self.folder, ref)
        self.app.respond(ref, 'approve', 'SYNTHETIC individual asset acceptance and exact build')
        accepted = [e for e in h._entries() if e['kind']=='decision' and e.get('action',{}).get('tool')=='asset.accept' and e.get('decision')=='allow']
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]['reason'], 'one_time_approval_consumed')
        self.assertIsNone(project_plan.status(self.root,self.folder)['tasks'][0]['acceptance'])

    def test_http_private_session_binding_and_retained_copy_tamper(self):
        run = self.copied(); self.scope()
        http = server(self.app); thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
        self.addCleanup(thread.join, 5); self.addCleanup(http.server_close); self.addCleanup(http.shutdown)
        url = f'http://127.0.0.1:{http.server_port}/api/workspace'
        def call(auth=True, **body):
            headers = {'Content-Type':'application/json'} | ({'X-Ember-Token':self.app.token} if auth else {})
            payload = dict(session_id=self.sid, action='promote_import', run_id=run, expected_manifest={}) | body
            with urlopen(Request(url, json.dumps(payload).encode(), headers), timeout=30) as response:
                return json.load(response)
        for values, code in ((dict(auth=False),403),(dict(session_id='f'*24),400),(dict(expected_manifest={'index.html':'0'*64}),400)):
            with self.subTest(values=values), self.assertRaises(HTTPError) as denied:
                call(**values)
            self.assertEqual(denied.exception.code, code)
        ref = call()['request_ref']
        self.app.respond(ref, 'decline', 'SYNTHETIC discard exact proposal')
        target = Path(self.fixture.fixture.saved()['import_sandbox'])/'app.js'
        target.write_bytes(b'x'*len(imports.PROJECT['app.js'].encode()))
        with self.assertRaises(HTTPError) as denied:
            call(operation_id='new-after-tamper-12345678')
        self.assertEqual(denied.exception.code, 400)
        self.assertFalse(chat_build.context(self.root,self.folder)['files'])
