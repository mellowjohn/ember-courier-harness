"""Saved builds export reviewed bytes, never mutable project files or host secrets."""
from hashlib import sha256
import io
import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

import test_chat_build as build_fixture
from ember_harness import chat_build, project_versions
from ember_harness.local_ui import App, server
from ember_harness.recovery import exclusive


class ProjectVersionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = build_fixture.ChatBuildTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.app, self.root, self.folder = self.fixture.app, self.fixture.root, self.fixture.folder

    def complete(self, files=None, turn='a' * 24):
        ref = self.fixture.propose_project(files, turn)
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: approve saved version')
        return ref

    def unpack(self, ref):
        data, filename = self.app.export_version(ref)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return {name: archive.read(name) for name in archive.namelist()}, filename, data

    def test_export_only_completed_version_and_manifest_without_host_data(self):
        ref = self.fixture.propose_project()
        self.assertEqual(project_versions.history(self.folder), [])
        with self.assertRaisesRegex(ValueError, 'completed approved'):
            self.app.export_version(ref)
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: export fixture')
        files, filename, data = self.unpack(ref)
        self.assertEqual(filename, 'ember-game-v1.zip')
        self.assertEqual(set(files), set(build_fixture.PROJECT) | {'README.txt', 'ember-build.json'})
        for name, content in build_fixture.PROJECT.items():
            self.assertEqual(files[name], content.encode('utf-8'))
        metadata = json.loads(files['ember-build.json'])
        for name in build_fixture.PROJECT:
            self.assertEqual(metadata['manifest'][name], sha256(files[name]).hexdigest())
        self.assertNotIn(self.app.token, b''.join(files.values()).decode('utf-8'))
        self.assertNotIn(str(self.root), files['ember-build.json'].decode('utf-8'))
        self.assertEqual(self.unpack(ref)[2], data)
        self.assertTrue(self.app.snapshot()['build']['versions'][0]['latest'])

    def test_versions_reconstruct_unchanged_files_and_ignore_current_tampering(self):
        first = self.complete()
        revised = {**build_fixture.PROJECT, 'app.js': 'document.body.dataset.version="two";'}
        second = self.complete(revised, 'b' * 24)
        rows = project_versions.history(self.folder)
        self.assertEqual([row['number'] for row in rows], [1, 2])
        self.assertEqual([row['latest'] for row in rows], [False, True])
        self.fixture.target.write_bytes(b'External unapproved change')
        old = self.unpack(first)[0]
        new = self.unpack(second)[0]
        self.assertEqual(old['app.js'], build_fixture.PROJECT['app.js'].encode('utf-8'))
        self.assertEqual(new['app.js'], revised['app.js'].encode('utf-8'))
        self.assertEqual(old['style.css'], new['style.css'])
        self.assertEqual(self.fixture.target.read_bytes(), b'External unapproved change')
        preview = self.app.version_preview(first)
        self.assertIn('data:text/javascript;base64,', preview['html'])
        fresh = App(self.root)
        fresh.resume(self.fixture.sid)
        self.assertEqual(fresh.export_version(first)[0], self.unpack(first)[2])

    def test_tampered_evidence_and_review_packets_cannot_export(self):
        ref = self.complete()
        h = chat_build.harness(self.folder)
        evidence = next(e for e in h._entries() if e['kind'] == 'evidence' and e['status'] == 'complete')
        path = h.root / 'evidence' / (evidence['evidence_refs'][0] + '.json')
        original = path.read_bytes()
        proof = json.loads(original)
        proof['items'][0]['params']['sha256'] = '0' * 64
        path.write_text(json.dumps(proof), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            self.app.export_version(ref)
        path.write_bytes(original)
        review = h.root / 'owner-review' / ref / 'request.json'
        payload = json.loads(review.read_bytes())
        payload['body']['build']['title'] = 'Changed packet'
        review.write_text(json.dumps(payload), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'hash'):
            self.app.export_version(ref)

    def test_declined_and_unknown_versions_cannot_export(self):
        ref = self.fixture.propose_project()
        self.app.respond(ref, 'decline', 'SYNTHETIC TEST: decline')
        for value in (ref, '0' * 64, '../outside'):
            with self.subTest(ref=value), self.assertRaises(ValueError):
                self.app.export_version(value)

    def test_legacy_single_file_version_export(self):
        original = chat_build.OwnerReview._request
        def legacy(host, h, kind, body, **kwargs):
            for key in ('files', 'manifest', 'before_manifest'):
                body['build'].pop(key, None)
            return original(host, h, kind, body, **kwargs)
        with patch.object(chat_build.OwnerReview, '_request', legacy):
            ref = self.fixture.propose()
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: legacy export')
        files, _, _ = self.unpack(ref)
        self.assertEqual(files['index.html'], build_fixture.HTML.encode('utf-8'))

    def test_download_http_requires_private_authorization(self):
        ref = self.complete()
        http = server(self.app)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        try:
            url = 'http://127.0.0.1:' + str(http.server_port) + '/api/export-version?ref=' + ref
            with self.assertRaises(HTTPError) as denied:
                urlopen(url, timeout=5)
            self.assertEqual(denied.exception.code, 403)
            with urlopen(Request(url, headers={'X-Ember-Token': self.app.token}), timeout=5) as response:
                self.assertEqual(response.headers['Content-Type'], 'application/zip')
                self.assertIn('ember-game-v1.zip', response.headers['Content-Disposition'])
                self.assertIn('index.html', zipfile.ZipFile(io.BytesIO(response.read())).namelist())
        finally:
            http.shutdown()
            http.server_close()
            worker.join()

    def restore(self, source, current, request_id='restore-request-0001'):
        return self.app.restore_version(self.fixture.sid, source, current, request_id)['request_ref']

    def test_restore_is_reviewed_forward_revision_and_preserves_all_versions(self):
        first = self.complete()
        revised = {**build_fixture.PROJECT, 'app.js': 'document.body.dataset.version="two";'}
        second = self.complete(revised, 'b' * 24)
        before = {name: (self.fixture.target.parent / name).read_bytes() for name in revised}
        with patch('ember_harness.session_chat.run_muse') as muse:
            ref = self.restore(first, second)
            self.assertEqual(self.restore(first, second), ref)
            muse.assert_not_called()
        self.assertEqual(len(project_versions.history(self.folder)), 2)
        self.assertEqual(before, {name: (self.fixture.target.parent / name).read_bytes() for name in revised})
        request = self.app.snapshot()['build']['requests'][-1]
        self.assertIsNone(request['decision'])
        self.assertEqual(request['payload']['body']['build']['restore_from']['request_ref'], first)
        self.assertIn('current/app.js', request['payload']['body']['build']['diff'])
        with self.assertRaisesRegex(ValueError, 'approval'):
            self.app.resume_build(ref)
        fresh = App(self.root)
        fresh.resume(self.fixture.sid)
        fresh.respond(ref, 'approve', 'SYNTHETIC TEST: approve exact restore')
        self.assertEqual([r['number'] for r in project_versions.history(self.folder)], [1, 2, 3])
        self.assertEqual(project_versions.snapshot(self.root, self.folder, ref)['files'], build_fixture.PROJECT)
        self.assertEqual(project_versions.snapshot(self.root, self.folder, second)['files'], revised)
        self.assertTrue(fresh.verify()['passed'])
        # Replaying the same request never adds a version, even after completion.
        self.assertEqual(fresh.restore_version(self.fixture.sid, first, second, 'restore-request-0001')['request_ref'], ref)
        self.assertEqual(len(project_versions.history(self.folder)), 3)

    def test_restore_decline_pending_conflicts_and_stale_current(self):
        first = self.complete()
        second = self.complete({**build_fixture.PROJECT, 'app.js': '/* revision */'}, 'b' * 24)
        with self.assertRaisesRegex(ValueError, 'current build changed'):
            self.restore(first, first)
        ref = self.restore(first, second)
        with self.assertRaisesRegex(ValueError, 'pending build'):
            self.restore(first, second, 'restore-request-0002')
        with self.assertRaisesRegex(ValueError, 'different version'):
            self.restore(second, second)
        self.app.respond(ref, 'decline', 'SYNTHETIC TEST: decline restore')
        self.assertEqual((self.fixture.target.parent / 'app.js').read_text(), '/* revision */')
        self.assertEqual(len(project_versions.history(self.folder)), 2)

    def test_restore_rejects_deletion_tampering_and_session_switch(self):
        first = self.complete()
        second = self.complete({**build_fixture.PROJECT, 'extra.js': '/* newly added */'}, 'b' * 24)
        with self.assertRaisesRegex(ValueError, 'would delete extra.js'):
            self.restore(first, second)
        self.assertEqual(len(self.app.snapshot()['build']['requests']), 2)
        self.fixture.target.write_bytes(b'Unapproved corruption')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.restore(second, second)
        self.app.start('Another game', new_session=True, chat_only=True)
        with self.assertRaisesRegex(ValueError, 'intended session'):
            self.restore(first, second)

    def test_interrupted_restore_resumes_exact_writes_once(self):
        first = self.complete()
        revised = {**build_fixture.PROJECT, 'app.js': '/* version two */', 'style.css': 'body { color:red; }'}
        second = self.complete(revised, 'b' * 24)
        ref = self.restore(first, second)
        replace = chat_build.os.replace
        def interrupt(source, target):
            replace(source, target)
            if str(target).endswith('app.js'):
                raise OSError('SYNTHETIC restore interruption')
        with patch('ember_harness.chat_build.os.replace', side_effect=interrupt):
            with self.assertRaisesRegex(OSError, 'restore interruption'):
                self.app.respond(ref, 'approve', 'SYNTHETIC TEST: restore before interruption')
        fresh = App(self.root)
        self.assertIn(ref, fresh.resume(self.fixture.sid)['build']['resumable'])
        fresh.resume_build(ref)
        self.assertTrue(fresh.verify()['passed'])
        self.assertEqual(project_versions.snapshot(self.root, self.folder, ref)['files'], build_fixture.PROJECT)
        child = self.app.snapshot()['build']['requests'][-1]['payload']['body']['contracts'][1]['contract']['id']
        decisions = [e for e in chat_build.harness(self.folder)._entries()
                     if e['kind'] == 'decision' and e.get('action', {}).get('contract_id') == child]
        self.assertEqual(len(decisions), 2)

    def test_restore_changed_after_proposal_and_corrupt_source_fail_closed(self):
        first = self.complete()
        second = self.complete({**build_fixture.PROJECT, 'app.js': '/* version two */'}, 'b' * 24)
        ref = self.restore(first, second)
        (self.fixture.target.parent / 'app.js').write_text('/* external edit */')
        with self.assertRaisesRegex(ValueError, 'changed since'):
            self.app.respond(ref, 'approve', 'SYNTHETIC TEST: must not approve')
        self.assertIsNone(self.app.snapshot()['build']['requests'][-1]['decision'])
        packet = chat_build.harness(self.folder).root / 'owner-review' / first / 'request.json'
        packet.write_bytes(b'{}')
        with self.assertRaises(ValueError):
            self.restore(first, second, 'restore-request-0002')

    def test_restore_during_chat_and_identical_or_invalid_requests_do_not_propose(self):
        first = self.complete()
        with self.assertRaisesRegex(ValueError, 'identical'):
            self.restore(first, first)
        with self.assertRaisesRegex(ValueError, 'stable restore'):
            self.restore(first, first, '../invalid')
        with exclusive(self.folder / 'chat.lock'):
            with self.assertRaisesRegex(ValueError, 'already active'):
                self.restore(first, first, 'restore-request-0002')
        self.assertEqual(len(self.app.snapshot()['build']['requests']), 1)
