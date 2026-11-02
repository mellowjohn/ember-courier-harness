"""Offline 2D handoffs, real PNGs and synthetic owner decisions in isolated sessions."""
from contextlib import redirect_stdout
from copy import deepcopy
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image

from ember_harness import asset_2d as sprites, asset_library, asset_pipeline, asset_workshop, chat_build, project_versions
from ember_harness.local_ui import App
from tools import asset_2d as cli

ROOT = Path(__file__).resolve().parents[1]


class SpriteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = sprites.effect_spec()
        cls.raw = sprites.render_effect(cls.spec)

    def setUp(self):
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'examples').mkdir(); (self.root / 'examples/product_demo.py').touch()

    def source(self, spec=None, name='atlas'):
        return cli.write_source(self.root / '.harness/asset-source' / name, self.raw, spec or self.spec)['source']

    def app(self):
        app = App(self.root); app.start('SYNTHETIC 2D fixture', chat_only=True)
        return app, app.sessions_dir / app.session['id']

    def propose(self, folder, files, turn='sprite'):
        with redirect_stdout(StringIO()):
            return chat_build.propose_build(self.root, folder, turn, 'Synthetic atlas fixture',
                dict(title='Sprite fixture', summary='Review exact PNG', files=[dict(path=k, content=v) for k,v in files.items()]),
                expected_before=chat_build.context(self.root, folder)['sha256'])

    def test_seeded_script_and_canonical_package(self):
        self.assertEqual(self.raw, sprites.render_effect(self.spec))
        different = sprites.effect_spec(seed=123)
        self.assertNotEqual(self.raw, sprites.render_effect(different))
        content = asset_pipeline.package(self.raw, self.spec)
        raw, spec, report = asset_pipeline.unpack(content)
        self.assertEqual(raw, self.raw); self.assertEqual(spec, self.spec)
        self.assertEqual(report['dimensions_px'], [384, 288]); self.assertEqual(len(report['frames']), 12)
        self.assertTrue(report['transparency'])
        with self.assertRaises(ValueError): asset_pipeline.unpack(content.replace('"fps":24', '"fps":25').replace('"frames":12', '"frames":11'))
        with self.assertRaises(ValueError): asset_pipeline.unpack(content + 'alert(1)')
        with self.assertRaises(ValueError): sprites.unpack(content.replace('"bytes":', '"extra":0,"bytes":'))

    def test_bad_dimensions_empty_frames_opaque_pixels_and_budgets(self):
        def png(image):
            out = BytesIO(); image.save(out, format='PNG'); return out.getvalue()
        for raw in [b'bad image', png(Image.new('RGBA', (10, 10))),
                    png(Image.new('RGBA', (384, 288))), png(Image.new('RGB', (384, 288), 'orange')),
                    b'x'*(sprites.MAX_PNG+1)]:
            with self.subTest(raw_size=len(raw)), self.assertRaises((ValueError, OSError)):
                sprites.inspect_png(raw, self.spec)
        # Transparent unused cells must not disguise fully opaque used frames.
        image = Image.new('RGBA', (384, 288)); image.paste('orange', (0, 0, 96, 96))
        spec = {**self.spec, 'frames': 1}
        with self.assertRaisesRegex(ValueError, 'frame.*transparency'):
            sprites.inspect_png(png(image), spec)
        for change in [dict(frames=65), dict(grid=[1000, 1]), dict(frame_size=[2049, 1]),
                       dict(fps=True), dict(pivot=[float('nan'), 0]), dict(loop='true'),
                       dict(id='../escape'), dict(production={})]:
            with self.subTest(change=change), self.assertRaises(ValueError): sprites.describe({**self.spec, **change})
        with self.assertRaises(ValueError): sprites.render_effect({**self.spec, 'production': {**self.spec['production'], 'tool': 'arbitrary.py'}})
        with self.assertRaisesRegex(ValueError, 'frame sizes'):
            sprites.render_effect({**self.spec, 'frame_size': [512, 512], 'grid': [1, 1], 'frames': 1})

    def test_generated_request_import_and_provenance(self):
        spec = deepcopy(self.spec)
        spec['production'] = dict(method='generated', tool='image_gen', prompt='Original amber impact atlas', seed=None)
        request = sprites.generation_request(spec)
        self.assertTrue(request['parameters']['transparent_background'])
        self.assertIn('384x288', request['parameters']['prompt'])
        request_path = self.root / 'request.json'; request_path.write_text(json.dumps(request))
        image_path = self.root / 'returned.png'; image_path.write_bytes(self.raw)
        destination = self.root / '.harness/asset-source/generated'
        with redirect_stdout(StringIO()):
            cli.main(['ingest', '--request', str(request_path), '--image', str(image_path), '--output', str(destination)])
        ref = asset_library.register(self.root, destination)
        record, _, _ = asset_library.load(self.root, ref)
        self.assertIn('generation', record['sources'])
        self.assertEqual(asset_library.summary(self.root, ref)['frames'], 12)
        # Changes to the tool request cannot be silently paired with the old pixels.
        request['parameters']['prompt'] += ' edited'; request_path.write_text(json.dumps(request))
        with self.assertRaisesRegex(ValueError, 'request changed'):
            cli.main(['ingest', '--request', str(request_path), '--image', str(image_path), '--output', str(self.root / 'bad')])
        self.assertFalse((self.root / 'bad').exists())
        request = sprites.generation_request(spec)
        request['version'] = True  # Python equality must not hide a changed JSON type.
        request_path.write_text(json.dumps(request))
        with self.assertRaisesRegex(ValueError, 'request changed'):
            cli.main(['ingest', '--request', str(request_path), '--image', str(image_path), '--output', str(self.root / 'bad')])
        with self.assertRaises(FileExistsError): cli.write_source(destination, self.raw, spec)

    def test_chat_saves_request_when_image_credits_unverified_without_fake_pixels_or_game_writes(self):
        app, folder = self.app()
        spec = deepcopy(self.spec)
        spec['production'] = dict(method='generated', tool='image_gen', prompt='Original impact artwork', seed=None)
        response = dict(message='Muse Image will generate artwork for review.', build=None, image_request=spec)
        with patch('ember_harness.session_chat.run_muse', return_value=dict(response=json.dumps(response))) as muse:
            app.chat('Generate a transparent impact atlas for my game', 'image-request-chat-12345678')
            prompt = muse.call_args.args[2]
            self.assertIn('return image_request', prompt)
            self.assertIn('Do not substitute primitive canvas shapes', prompt)
            request = sprites.generation_request(spec)
            saved = json.loads((folder / 'image-requests/image-request-chat-12345678.json').read_bytes())
            self.assertEqual(saved, request)
            self.assertEqual(app.snapshot()['messages'][-1]['image_request'], request)
            app.chat('Generate a transparent impact atlas for my game', 'image-request-chat-12345678')
            self.assertEqual(muse.call_count, 1)
        fresh = App(self.root); fresh.resume(app.session['id'])
        self.assertEqual(fresh.snapshot()['messages'][-1]['image_request'], request)
        self.assertFalse(chat_build.list_requests(folder))
        self.assertFalse(chat_build.context(self.root, folder)['manifest'])
        self.assertFalse(list((folder / 'image-requests').glob('*.png')))
        self.assertEqual(fresh.snapshot()['messages'][-1]['image_generation']['status'], 'blocked')

    def test_chat_rejects_invalid_generation_layout_or_conflicting_asset_selection(self):
        app, folder = self.app()
        spec = deepcopy(self.spec)
        spec['production'] = dict(method='generated', tool='image_gen', prompt='Original artwork', seed=None)
        for index, (image_spec, selected) in enumerate([
            ({**spec, 'frame_size': [2048, 2048]}, None),
            (spec, dict(ref='a'*64, intent='use'))]):
            response = dict(message='Request', build=None, asset=selected, image_request=image_spec)
            with patch('ember_harness.session_chat.run_muse', return_value=dict(response=json.dumps(response))):
                with self.assertRaises(ValueError):
                    app.chat('Generate artwork', 'bad-image-request-12345678-' + str(index))
        self.assertFalse((folder / 'image-requests').exists())
        self.assertFalse(chat_build.list_requests(folder))

    def test_review_accept_export_restore_and_source_update(self):
        source = Path(self.source()); app, folder = self.app()
        ref = asset_library.register(self.root, source)
        context = asset_library.context(self.root, folder, refresh=True)
        build = asset_library.build_from_reference(self.root, context, ref, None, {})
        files = {item['path']: item['content'] for item in build['files']}
        with redirect_stdout(StringIO()):
            first = chat_build.propose_build(self.root, folder, 'sprite', 'Synthetic atlas fixture',
                build, asset_source=asset_library.provenance(self.root, ref))
        packet = chat_build.list_requests(folder)[-1]['payload']['body']
        self.assertEqual(len(packet['asset_actions']), 1)
        self.assertEqual(packet['build']['asset']['report']['profile'], sprites.PROFILE)
        self.assertIn('data:text/javascript;base64,', chat_build.proposal_preview(self.root, folder, first)['html'])
        self.assertFalse(chat_build.project(self.root, folder).exists())
        with self.assertRaises(ValueError): chat_build.resume(self.root, folder, first)
        app.respond(first, 'approve', 'SYNTHETIC TEST: Accept exact PNG and play')
        self.assertTrue(chat_build.verify(self.root, folder)['passed'])
        entries = chat_build.harness(folder)._entries()
        accepted = [e for e in entries if e['kind']=='decision' and e.get('action', {}).get('tool')=='asset.accept' and e['decision']=='allow']
        self.assertEqual(len(accepted), 1); self.assertEqual(accepted[0]['reason'], 'one_time_approval_consumed')
        data, _ = project_versions.export(self.root, folder, first)
        with zipfile.ZipFile(BytesIO(data)) as archive:
            self.assertEqual(archive.read('ember-impact.png'), self.raw)
            self.assertNotIn('ember-impact.glb', archive.namelist())
        # Ordinary source revisions retain the exact atlas without new acceptance.
        revised = {**files, 'index.html': files['index.html'].replace('<h1 ', '<h1 data-revised="yes" ')}
        second = self.propose(folder, revised, 'source-revision')
        self.assertNotIn('asset_actions', chat_build.list_requests(folder)[-1]['payload']['body'])
        app.respond(second, 'approve', 'SYNTHETIC TEST: code revision')
        restored = project_versions.propose_restore(self.root, folder, first, second, 'sprite-restore-1234567890')
        app.respond(restored, 'approve', 'SYNTHETIC TEST: restore reviewed bytes')
        self.assertEqual(project_versions.snapshot(self.root, folder, restored)['files'], files)
        # An edited PNG gets a separate proposal and exact asset acceptance.
        new_spec = sprites.effect_spec(seed=99)
        new_raw = sprites.render_effect(new_spec)
        (source / 'ember-impact.png').write_bytes(new_raw)
        (source / 'asset-spec.json').write_text(json.dumps(new_spec))
        with redirect_stdout(StringIO()):
            updated = asset_workshop.review_updated_export(self.root, folder, ref, restored)
        pending = chat_build.list_requests(folder)[-1]['payload']['body']
        self.assertEqual([f['name'] for f in pending['build']['files']], ['asset.js'])
        self.assertEqual(len(pending['asset_actions']), 1)
        self.assertEqual(project_versions.snapshot(self.root, folder, restored)['files'], files)
        app.respond(updated['request_ref'], 'approve', 'SYNTHETIC TEST: accept updated PNG')
        current = {f['path']: f['content'] for f in chat_build.context(self.root, folder)['files']}
        self.assertEqual(asset_pipeline.unpack(current['asset.js'])[0], new_raw)

    def test_chat_retains_pixels_and_receives_rendering_metadata(self):
        source = self.source(); app, folder = self.app()
        asset_ref = asset_library.register(self.root, source)
        response = dict(message='Review the existing atlas.', asset=dict(ref=asset_ref, intent='use'), build=None)
        with patch('ember_harness.session_chat.run_muse', return_value=dict(response=json.dumps(response))):
            app.chat('Preview my impact effect', 'sprite-chat-first-12345678')
        first = chat_build.list_requests(folder)[-1]['ref']
        app.respond(first, 'approve', 'SYNTHETIC TEST: accept atlas')
        content = chat_build.context(self.root, folder)
        redacted = asset_library.prompt_project(content)
        asset = next(f for f in redacted['files'] if f['path']=='asset.js')
        self.assertNotIn('content', asset); self.assertEqual(asset['asset']['specification'], self.spec)
        response = dict(message='Existing effect is retained.', build=None)
        with patch('ember_harness.session_chat.run_muse', return_value=dict(response=json.dumps(response))) as muse:
            app.chat('How do I trigger this on a hit?', 'sprite-chat-next-123456789')
        self.assertIn('png_base64', str(muse.call_args))
        self.assertNotIn(b64_marker(self.raw), str(muse.call_args))
        basis = {f['path']: f['content'] for f in content['files']}
        retained = asset_library.preserve_files(dict(title='Code', summary='Code only', files=[dict(path='index.html', content=basis['index.html'])]), basis)
        self.assertEqual(next(f['content'] for f in retained['files'] if f['path']=='asset.js'), basis['asset.js'])


def b64_marker(raw):
    from base64 import b64encode
    return b64encode(raw).decode('ascii')[:200]


if __name__ == '__main__': unittest.main()
