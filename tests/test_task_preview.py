"""Private, read-only access to verified task candidates and comparison captures."""
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import test_task_run as tasks
from ember_harness import chat_build, task_run
from ember_harness.local_ui import server


class TaskPreviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = tasks.TaskRunTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.folder, self.app = self.fixture.root, self.fixture.folder, self.fixture.app
        self.run_id = self.fixture.prepare()
        self.fixture.approve(self.run_id)
        result = self.fixture.run_worker(self.run_id)
        self.assertEqual(result['status'], 'ready_review', result.get('error'))
        self.before = chat_build.context(self.root, self.folder)['manifest']
        self.http = server(self.app)
        thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)

    def get(self, endpoint='task-preview', *, authenticated=True, **query):
        args = dict(session_id=self.folder.name, run_id=self.run_id, index=1) | query
        headers = {'X-Ember-Token': self.app.token} if authenticated else {}
        request = Request(f'http://127.0.0.1:{self.http.server_port}/api/{endpoint}?' + urlencode(args), headers=headers)
        with urlopen(request) as response:
            return response.read(), response.headers

    def test_private_preview_and_bound_before_after_images_do_not_apply_files(self):
        raw, headers = self.get()
        data = json.loads(raw)
        self.assertIn('data:text/css;base64', data['html'])
        self.assertEqual(headers['Cache-Control'], 'no-store')
        for stage in ('candidate', 'baseline'):
            image, headers = self.get('task-image', name='desktop.png', stage=stage)
            self.assertTrue(image.startswith(b'\x89PNG\r\n\x1a\n'))
            self.assertEqual(headers['Content-Type'], 'image/png')
        self.assertEqual(chat_build.context(self.root, self.folder)['manifest'], self.before)
        for endpoint in ('task-preview', 'task-image'):
            with self.assertRaises(HTTPError) as denied:
                self.get(endpoint, authenticated=False, name='desktop.png')
            self.assertEqual(denied.exception.code, 403)

    def test_wrong_session_and_unreviewed_paths_are_rejected(self):
        for query in (dict(session_id='f' * 24), dict(run_id='../other'),
                      dict(index=0), dict(index=-1), dict(index=999), dict(stage='../../'),
                      dict(name='../input.json')):
            with self.subTest(query=query), self.assertRaises(HTTPError) as denied:
                self.get('task-image', **(dict(name='desktop.png') | query))
            self.assertEqual(denied.exception.code, 400)

    def test_capture_and_candidate_changes_block_read_only_access(self):
        work = task_run.run_folder(self.folder, self.run_id)
        image = work / 'captures/0/output/desktop.png'
        original = image.read_bytes()
        image.write_bytes(b'changed screenshot')
        with self.assertRaises(HTTPError) as denied:
            self.get('task-image', name='desktop.png', stage='baseline')
        self.assertEqual(denied.exception.code, 400)
        image.write_bytes(original)
        candidate = work / 'candidates/1/style.css'
        candidate.write_text('body{background:red}', encoding='utf-8')
        with self.assertRaises(HTTPError) as denied:
            self.get()
        self.assertEqual(denied.exception.code, 400)
        self.assertEqual(chat_build.context(self.root, self.folder)['manifest'], self.before)
