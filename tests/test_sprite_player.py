"""Named animation contracts and actual chat/retention boundaries; no live model calls."""
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator

from ember_harness import asset_2d, asset_library, asset_workshop, chat_build, gameplay, muse_image, task_run
from ember_harness.local_ui import App
from ember_harness.muse_chat import decode_structured, structured_schema
from test_muse_chat import wire_reply

ROOT = Path(__file__).resolve().parents[1]


def named_spec():
    spec = asset_2d.effect_spec()
    spec.update(animations=dict(
        idle=dict(frames=[0, 1], fps=6, loop=True),
        walk=dict(frames=[2, 3, 4, 5], fps=10, loop=True),
        attack=dict(frames=[6, 7, 8], fps=12, loop=False, next='idle'),
        death=dict(frames=[9, 10, 11], fps=8, loop=False)), default_animation='idle')
    return spec


class SpritePlayerTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'examples').mkdir(); (self.root / 'examples/product_demo.py').touch()
        self.spec = named_spec(); self.raw = asset_2d.render_effect(self.spec)

    def source(self):
        source = self.root / '.harness/asset-source/named'
        asset_2d.write_source(source, self.raw, self.spec)
        return source

    def test_optional_animation_schema_and_legacy_packages(self):
        generated = deepcopy(self.spec)
        generated['production'] = dict(method='generated', tool='muse_image', prompt='Original animated courier', seed=None)
        Draft202012Validator(asset_2d.GENERATION_SCHEMA).validate(generated)
        request = asset_2d.generation_request(generated)
        self.assertIn('"attack"', request['parameters']['prompt'])
        self.assertIn('"attack"', muse_image.parameters(request)['prompt'])
        package = asset_2d.package(self.raw, self.spec)
        self.assertEqual(asset_2d.unpack(package)[1], self.spec)
        legacy = asset_2d.effect_spec()
        self.assertNotIn('animations', asset_2d.unpack(asset_2d.package(self.raw, legacy))[1])
        self.assertEqual(asset_2d.animations(legacy)['default']['frames'], list(range(12)))
        for change in [dict(animations={}), dict(animations=None), dict(default_animation='missing'),
                       dict(animations={'attack': dict(frames=[12], fps=12, loop=False)}),
                       dict(animations={'attack': dict(frames=[True], fps=12, loop=False)}),
                       dict(animations={'attack': dict(frames=[0], fps=12, loop=False, next='missing')}),
                       dict(animations={'idle': dict(frames=[0], fps=12, loop=True, next='idle')}),
                       dict(animations={'idle': dict(frames=[0], fps=0, loop=True)}),
                       dict(animations={'idle': dict(frames=[0], fps=12, loop=True, injected='x')}),
                       dict(animations={'bad name': dict(frames=[0], fps=12, loop=True)})]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                asset_2d.describe({**self.spec, **change})
        with self.assertRaises(ValueError): asset_2d.describe({**legacy, 'default_animation': 'default'})

    def test_shared_runtime_and_browser_time_contract(self):
        node = shutil.which('node')
        if not node: self.skipTest('Optional Node runtime is unavailable')
        runtime = Path(asset_2d.__file__).with_name('asset_lab') / 'sprite-player.js'
        result = subprocess.run([node, str(ROOT / 'tests/sprite_player_test.js'), str(runtime)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_named_clips_survive_native_model_schema_transport(self):
        spec = deepcopy(self.spec)
        spec['production'] = dict(method='generated', tool='muse_image', prompt='Original character actions', seed=None)
        wire = wire_reply(spec,asset_2d.GENERATION_SCHEMA)
        Draft202012Validator(structured_schema(asset_2d.GENERATION_SCHEMA)).validate(wire)
        decoded = decode_structured(wire, asset_2d.GENERATION_SCHEMA)
        asset_2d.describe(decoded)
        self.assertEqual(decoded['animations']['attack'], spec['animations']['attack'])
        self.assertEqual(decoded['animations']['idle']['frames'], [0, 1])
        self.assertEqual(decoded['default_animation'], 'idle')
        legacy = {k:v for k,v in spec.items() if k not in ('animations', 'default_animation')}
        old_wire = {**legacy, 'animations': None, 'default_animation': None}
        self.assertEqual(decode_structured(old_wire, asset_2d.GENERATION_SCHEMA), legacy)
        wire['animations'].append(wire['animations'][0])
        with self.assertRaisesRegex(ValueError, 'duplicate map key'):
            decode_structured(wire, asset_2d.GENERATION_SCHEMA)

    def test_chat_bundles_player_in_existing_game_and_retains_it_on_revision(self):
        source = self.source(); ref = asset_library.register(self.root, source)
        app = App(self.root); app.start('SYNTHETIC named sprite game', chat_only=True)
        folder = app.sessions_dir / app.session['id']
        html = '<html><body><p id="score">Score: 7</p><canvas id="game"></canvas><script src="game.js"></script></body></html>'
        before = dict(title='Existing game', summary='Isolated fixture', files=[dict(path='index.html', content=html),
            dict(path='game.js', content='globalThis.score=7;')])
        with redirect_stdout(StringIO()):
            initial = chat_build.propose_build(self.root, folder, 'initial', 'Synthetic existing game', before)
            app.respond(initial, 'approve', 'SYNTHETIC TEST: existing fixture')
        build = dict(title='Use actual sprite', summary='Keep score and use the recorded PNG', edits=[dict(path='index.html',
            before='<script src="game.js">', after='<script src="asset.js"></script><script src="game.js">')])
        response = dict(message='Review the sprite integration.', build=build, asset=dict(ref=ref, intent='use'))
        with patch('ember_harness.session_chat.run_muse', return_value=dict(response=json.dumps(response))) as muse, redirect_stdout(StringIO()):
            app.chat('Use this sprite in my existing game', 'named-sprite-chat-12345678')
        request = chat_build.list_requests(folder)[-1]['ref']
        files = chat_build.proposal_snapshot(self.root, folder, request)['files']
        self.assertIn('sprite-player.js', files)
        self.assertIn('Score: 7', files['index.html'])
        self.assertLess(files['index.html'].index('sprite-player.js'), files['index.html'].index('game.js'))
        self.assertIn('EmberSprites.load', muse.call_args.args[2])
        self.assertEqual(files['game.js'], 'globalThis.score=7;')
        self.assertEqual(gameplay.load(folder)['revision'], 0, 'Custom games must not receive workshop selectors')
        with redirect_stdout(StringIO()): app.respond(request, 'approve', 'SYNTHETIC TEST: exact sprite acceptance')
        revised = asset_library.preserve_files(dict(title='Revision', summary='Keep runtime', files=[
            dict(path='index.html', content=files['index.html']), dict(path='game.js', content=files['game.js'])]), files)
        self.assertEqual(next(f['content'] for f in revised['files'] if f['path']=='sprite-player.js'), files['sprite-player.js'])
        redacted = asset_library.prompt_project(dict(files=revised['files']))
        self.assertNotIn('content', next(f for f in redacted['files'] if f['path']=='sprite-player.js'))
        model = task_run.model_context(files, files)
        self.assertNotIn('sprite-player.js', model['files']); self.assertIn('sprite-player.js', model['immutable_files'])
        self.assertIn('EmberSprites.load', model['sprite_player_api'])
        with self.assertRaises(ValueError):
            asset_library.preserve_files(dict(title='Bad', summary='Bad', files=[dict(path='sprite-player.js',content='changed')]), files)
        with self.assertRaises(ValueError):
            chat_build.materialize_build(dict(title='Bad', summary='Bad', edits=[dict(path='sprite-player.js',
                before='EmberSprites', after='Changed')]), files)

    def test_workshop_seeds_sprite_checks_and_injection_ignores_comments(self):
        with redirect_stdout(StringIO()): prepared = asset_2d.prepare(self.root, self.source())
        folder = App(self.root).sessions_dir / prepared['session_id']
        plan = gameplay.load(folder)['plan']
        gameplay.validate(plan)
        self.assertEqual(plan, asset_2d.plan(self.spec))
        self.assertNotIn('#lid-state', json.dumps(plan))
        before = '<html><body><!-- <script src="sprite-player.js"></script> --><script src="asset.js"></script></body></html>'
        files = asset_2d.attach_player({'index.html':before}, {})
        self.assertIn('--><script src="sprite-player.js"></script><script src="asset.js">', files['index.html'])
        self.assertEqual(asset_2d.attach_player(files, files), files)
        late = '<html><body><script src="game.js"></script><script defer src="sprite-player.js"></script></body></html>'
        normalized = asset_2d.attach_player({'index.html': late}, {})['index.html']
        self.assertEqual(normalized.count('src="sprite-player.js"'), 1)
        self.assertLess(normalized.index('sprite-player.js'), normalized.index('game.js'))
        self.assertNotIn('defer', normalized)
        missing = asset_2d.attach_player({'index.html': late, 'asset.js': 'fixture bytes'}, {})['index.html']
        self.assertLess(missing.index('asset.js'), missing.index('sprite-player.js'))
        self.assertLess(missing.index('sprite-player.js'), missing.index('game.js'))
        with self.assertRaises(ValueError): asset_2d.attach_player({'index.html':before,'sprite-player.js':'spoofed'}, {})


if __name__ == '__main__': unittest.main()
