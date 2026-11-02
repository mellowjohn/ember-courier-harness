"""Human-selected folders preserve exact review, persistence and existing projects."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ember_harness import chat_build, project_brief, gameplay, project_locations, project_versions
from ember_harness.local_ui import App, server
from ember_harness.recovery import exclusive

ROOT = Path(__file__).resolve().parents[1]
HTML = '<html><body><h1>Original saved game</h1></body></html>'


class ProjectLocationTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=scratch); self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / 'harness'; (self.root / 'examples').mkdir(parents=True)
        (self.root / 'examples/product_demo.py').touch()
        self.parent = self.base / 'My Game Projects'; self.parent.mkdir()
        (self.parent / 'existing.txt').write_text('Keep this unrelated file')
        self.app = App(self.root)

    def start(self):
        self.app.start('My original game', chat_only=True, project_parent=str(self.parent))
        return self.app.sessions_dir / self.app.session['id']

    def propose(self, folder):
        with redirect_stdout(io.StringIO()):
            return chat_build.propose_build(self.root, folder, 'location-test-build-0001', 'SYNTHETIC fixture',
                dict(title='Original game', summary='Original test fixture', files=[dict(path='index.html', content=HTML)]))

    def test_selected_folder_is_persistent_exact_review_target_and_remembered_default(self):
        folder = self.start(); target = chat_build.project(self.root, folder)
        self.assertEqual(target.parent, self.parent)
        self.assertFalse(target.exists())
        ref = self.propose(folder)
        row = chat_build.list_requests(folder)[0]['payload']['body']['build']['files'][0]
        self.assertEqual(row['path'], (target / 'index.html').as_posix())
        self.assertFalse(target.exists())
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: accept selected folder build')
        self.assertEqual((target / 'index.html').read_text(), HTML)
        self.assertEqual(chat_build.context(self.root, folder)['directory'], str(target))
        sid = folder.name; fresh = App(self.root)
        self.assertEqual(fresh.resume(sid)['build']['project'], str(target))
        self.assertEqual(fresh.history()[0]['project'], str(target))
        fresh.start('Another game', chat_only=True, new_session=True)
        other = chat_build.project(self.root, fresh.sessions_dir / fresh.session['id'])
        self.assertEqual(other.parent, self.parent); self.assertNotEqual(other, target)
        self.assertEqual((self.parent / 'existing.txt').read_text(), 'Keep this unrelated file')

    def test_invalid_folder_does_not_create_session_or_mutate_existing_one(self):
        self.start(); original = dict(self.app.session)
        bad_file = self.base / 'not-a-folder'; bad_file.touch()
        for value in ('relative/path', str(bad_file), str(self.base / 'missing'), '', '\n'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.app.start('Invalid target', chat_only=True, new_session=True, project_parent=value)
            self.assertEqual(self.app.session, original)
            self.assertEqual(len(self.app.history()), 1)

    def test_legacy_session_keeps_original_internal_location(self):
        sid = 'a' * 24; folder = self.app.sessions_dir / sid; folder.mkdir(parents=True)
        self.assertEqual(chat_build.project(self.root, folder), self.root / '.harness/projects' / sid)
        self.assertFalse((folder / 'project-location.json').exists())

    def test_changed_binding_cannot_redirect_pending_approved_writes(self):
        folder = self.start(); ref = self.propose(folder)
        binding = folder / 'project-location.json'; data = json.loads(binding.read_text())
        other = self.base / 'other'; other.mkdir()
        data.update(parent=str(other), path=str(other / ('redirect-' + folder.name)))
        binding.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'Reviewed project path changed'):
            self.app.respond(ref, 'approve', 'SYNTHETIC TEST: stale target must fail')
        self.assertEqual(list(other.iterdir()), [])
        self.assertIsNone(chat_build.list_requests(folder)[0]['decision'])

    def test_destination_interference_is_not_overwritten(self):
        folder = self.start(); ref = self.propose(folder); target = chat_build.project(self.root, folder)
        target.mkdir(); (target / 'index.html').write_text('Unreviewed external file')
        with self.assertRaisesRegex(ValueError, 'Project changed'):
            self.app.respond(ref, 'approve', 'SYNTHETIC TEST: must preserve existing file')
        self.assertEqual((target / 'index.html').read_text(), 'Unreviewed external file')

    def test_external_destination_stages_atomic_writes_on_target_volume(self):
        folder = self.start(); ref = self.propose(folder); target = chat_build.project(self.root, folder)
        replace = chat_build.os.replace
        def volume_checked(source, destination):
            if Path(destination) == target / 'index.html':
                # Model EXDEV for a temp file on the harness volume instead of the selected one.
                if Path(source).parent != self.parent:
                    raise OSError('Cross-device replacement')
            return replace(source, destination)
        with patch('ember_harness.chat_build.os.replace', side_effect=volume_checked):
            self.app.respond(ref, 'approve', 'SYNTHETIC TEST: save to another project volume')
        self.assertEqual((target / 'index.html').read_text(), HTML)
        self.assertFalse(list(self.parent.glob('.ember-output-*')))

    def test_save_as_keeps_source_and_copies_approved_bytes_guidance_and_checks_after_review(self):
        source = self.start(); ref = self.propose(source)
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: approve source game')
        project_brief.save(source, dict(goal='Original goal', controls='', visual_direction='', constraints=''), 0)
        gameplay.save(source, dict(title='Keep heading', scenarios=[dict(name='Heading', viewport='desktop',
            steps=[dict(action='text', selector='h1', value='Original saved game')])]), 0)
        target_parent = self.base / 'Saved copies'; target_parent.mkdir()
        with redirect_stdout(io.StringIO()):
            result = self.app.copy_project(source.name, ref, 'My saved copy', str(target_parent))
        target_folder = self.app.sessions_dir / result['session_id']; target = Path(result['project'])
        self.assertFalse(target.exists()); self.assertNotEqual(target_folder, source)
        self.assertEqual(project_brief.load(target_folder)['fields']['goal'], 'Original goal')
        self.assertEqual(gameplay.load(target_folder)['plan'], gameplay.load(source)['plan'])
        self.assertEqual((chat_build.project(self.root, source) / 'index.html').read_text(), HTML)
        self.app.respond(result['request_ref'], 'approve', 'SYNTHETIC TEST: approve save as copy')
        self.assertEqual((target / 'index.html').read_text(), HTML)
        self.assertEqual(project_versions.snapshot(self.root, target_folder, result['request_ref'])['files']['index.html'], HTML)
        self.assertEqual(App(self.root).resume(target_folder.name)['build']['project'], str(target))

    def test_copy_rejects_stale_session_version_and_active_request(self):
        source = self.start(); ref = self.propose(source)
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: source build')
        for sid, current in (('b' * 24, ref), (source.name, 'a' * 64)):
            with self.assertRaises(ValueError): self.app.copy_project(sid, current, 'Copy', str(self.parent))
        with exclusive(source / 'chat.lock'), self.assertRaises(ValueError):
            self.app.copy_project(source.name, ref, 'Copy', str(self.parent))
        self.assertEqual(len(self.app.history()), 1)

    def test_picker_cancel_and_http_authorization(self):
        self.start(); settings = project_locations.settings_path(self.root).read_bytes()
        http = server(self.app); thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
        self.addCleanup(thread.join); self.addCleanup(http.server_close); self.addCleanup(http.shutdown)
        base = f'http://127.0.0.1:{http.server_port}'
        def post(path, body, authorized=True):
            return urlopen(Request(base + path, data=json.dumps(body).encode(), headers={
                'Content-Type': 'application/json', **({'X-Ember-Token': self.app.token} if authorized else {})}), timeout=10)
        with patch('ember_harness.project_locations.pick', return_value=None) as picker:
            with self.assertRaises(HTTPError): post('/api/project-folder-picker', {}, False)
            picker.assert_not_called()
            with post('/api/project-folder-picker', {'parent': str(self.base / 'missing')}) as response:
                self.assertIsNone(json.load(response)['path'])
            picker.assert_called_once()
        self.assertEqual(project_locations.settings_path(self.root).read_bytes(), settings)
        with self.assertRaises(HTTPError): post('/api/project-copy', {}, False)


if __name__ == '__main__': unittest.main()
