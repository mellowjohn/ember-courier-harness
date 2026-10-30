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
