"""Tile generation handoffs, static terrain contracts and exact offline exports."""
from contextlib import redirect_stdout
from copy import deepcopy
from io import BytesIO, StringIO
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from PIL import Image
from jsonschema import Draft202012Validator

from ember_harness import asset_2d, asset_library, chat_build, gameplay, muse_image, project_versions, sprite_project, task_artwork
from ember_harness.local_ui import App
from ember_harness.muse_chat import decode_structured, structured_schema
from test_muse_chat import wire_reply
from tools import asset_2d as cli
from tools.sprite_check import tile_fixture

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    spec, raw = tile_fixture()
    spec['production'] = dict(method='generated', tool='muse_image', prompt='SYNTHETIC request transport fixture', seed=None)
    return spec, raw


class TileTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=scratch); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'examples').mkdir(); (self.root / 'examples/product_demo.py').touch()
        self.spec, self.raw = fixture()

    def source(self):
        source = self.root / '.harness/asset-source/terrain'
        asset_2d.write_source(source, self.raw, self.spec, asset_2d.generation_request(self.spec))
        return source

    def test_generated_layout_reaches_both_image_tools_and_native_chat_transport(self):
        Draft202012Validator(asset_2d.GENERATION_SCHEMA).validate(self.spec)
        request = asset_2d.generation_request(self.spec)
        for prompt in [request['parameters']['prompt'], muse_image.parameters(request)['prompt']]:
            self.assertIn('"wall": {"frame": 1, "solid": true}', prompt)
            self.assertIn('not animation frames', prompt)
            self.assertIn('repeat seamlessly horizontally and vertically', prompt)
            self.assertNotIn('generous empty margins', prompt)
        self.assertFalse(request['parameters']['transparent_background'])
        wire = wire_reply(self.spec, asset_2d.GENERATION_SCHEMA)
        Draft202012Validator(structured_schema(asset_2d.GENERATION_SCHEMA)).validate(wire)
        self.assertEqual(decode_structured(wire, asset_2d.GENERATION_SCHEMA), self.spec)
        structured_schema(chat_build.CHAT_SCHEMA)  # Full entity response must fit the provider nesting limit.
        self.assertEqual(asset_2d.animations(self.spec)['default']['frames'], [0])
        content = asset_2d.package(self.raw, self.spec)
        self.assertEqual(asset_2d.unpack(content)[1]['tileset'], self.spec['tileset'])

    def test_blob_source_builds_and_checks_47_connected_cells(self):
        spec = asset_2d.tileset_spec('blob-test', ['ground'], style='Weathered mossy rock',
            edge_mode='blob', tile_size=(32, 24), solid=['ground'], view='side-view')
        request = asset_2d.generation_request(spec)
        self.assertEqual(muse_image.parameters(request)['size'], '32x24')
        self.assertEqual(spec['tileset']['tiles']['ground']['frame'], 46)
        stream = BytesIO()
        Image.new('RGB', (32, 24), '#596a47').save(stream, 'PNG')
        raw, preparation = asset_2d.prepare_generated_png(stream.getvalue(), spec)
        self.assertEqual(preparation['output_dimensions'], [256, 144])
        self.assertTrue(asset_2d.unpack(asset_2d.package(raw, spec))[2]['connected_edges_matched'])
        # Mask 1 joins to its north. Damage that boundary while preserving dimensions and occupancy.
        picture = Image.open(BytesIO(raw)).convert('RGBA')
        picture.putpixel((48, 0), (255, 0, 0, 255))
        stream = BytesIO()
        picture.save(stream, 'PNG')
        with self.assertRaisesRegex(ValueError, 'mismatched connected edge'):
            asset_2d.inspect_png(stream.getvalue(), spec)

    def test_single_tile_cli_and_unchanged_request_ingest(self):
        request_path = self.root / 'tile-request.json'
        with redirect_stdout(StringIO()):
            cli.main(['tile-request', '--id', 'grass-tile', '--tile', 'grass', '--tile-size', '16', '16',
                '--style', 'Original green meadow', '--output', str(request_path)])
        payload = json.loads(request_path.read_text())
        spec = payload['specification']
        self.assertEqual((spec['kind'], spec['grid'], spec['frames']), ('tile', [1, 1], 1))
        self.assertEqual(asset_2d.tiles(spec), {'grass': dict(frame=0, solid=False)})
        image_path = self.root / 'grass.png'
        with Image.open(BytesIO(self.raw)) as image:
            image.crop((0, 0, 16, 16)).save(image_path)
        output = self.root / '.harness/asset-source/grass'
        with redirect_stdout(StringIO()):
            cli.main(['ingest', '--request', str(request_path), '--image', str(image_path), '--output', str(output)])
        ref = asset_library.register(self.root, output)
        self.assertEqual(asset_library.summary(self.root, ref)['specification'], spec)
        payload['specification']['tileset']['tiles']['grass']['solid'] = True
        request_path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, 'request changed'):
            cli.main(['ingest', '--request', str(request_path), '--image', str(image_path), '--output', str(output / 'changed')])

    def test_side_view_handoff_has_connected_platform_guidance_in_both_adapters(self):
        spec=asset_2d.tileset_spec('jungle-platforms',['left','middle','right','fill'],
            style='Original side-view jungle ruins',view='side-view',seamless=False,solid=['left','middle','right','fill'])
        request=asset_2d.generation_request(spec)
        for prompt in (request['parameters']['prompt'],muse_image.parameters(request)['prompt']):
            self.assertIn('side-view orthographic platformer',prompt)
            self.assertIn('middle sections repeat horizontally',prompt)
            self.assertIn('Do not frame every cell',prompt)
            self.assertNotIn('Use a consistent top-down',prompt)
            self.assertNotIn('Opposite edges of every tile',prompt)
        wire=wire_reply(spec,asset_2d.GENERATION_SCHEMA)
        Draft202012Validator(structured_schema(asset_2d.GENERATION_SCHEMA)).validate(wire)
        self.assertEqual(decode_structured(wire,asset_2d.GENERATION_SCHEMA),spec)
        for view in ('isometric',None,[],{}):
            changed=deepcopy(spec);changed['tileset']['view']=view
            with self.subTest(view=view),self.assertRaises(ValueError):asset_2d.describe(changed)

    def test_autotile_preparation_matches_opposite_edges_per_material(self):
        spec = deepcopy(self.spec)
        spec['tileset'].update(edge_mode='autotile', view='side-view')
        spec['production']['prompt'] = 'Original mossy soil and stone materials'
        wire = wire_reply(spec, asset_2d.GENERATION_SCHEMA)
        Draft202012Validator(structured_schema(asset_2d.GENERATION_SCHEMA)).validate(wire)
        self.assertEqual(decode_structured(wire, asset_2d.GENERATION_SCHEMA), spec)
        request = asset_2d.generation_request(spec)
        self.assertIn('opaque material swatch', muse_image.parameters(request)['prompt'])

        def png(image):
            output = BytesIO()
            image.save(output, format='PNG')
            return output.getvalue()

        with Image.open(BytesIO(self.raw)) as original:
            picture = original.convert('RGBA')
        for index in range(4):
            x, y = index % 2 * 16, index // 2 * 16
            picture.paste((12, 30, 40, 255), (x, y, x+2, y+16))
            picture.paste((92, 150, 200, 255), (x, y, x+16, y+1))
        raw = png(picture)
        with self.assertRaisesRegex(ValueError, 'mismatched repeat edges'):
            asset_2d.package(raw, spec)
        prepared, report = asset_2d.prepare_generated_png(raw, spec)
        self.assertEqual(report['edge_mode'], 'autotile')
        restored, _, packaged_report = asset_2d.unpack(asset_2d.package(prepared, spec))
        self.assertEqual(restored, prepared)
        self.assertTrue(packaged_report['repeat_edges_matched'])
        with Image.open(BytesIO(prepared)) as output:
            for y in (0, 16):
                for x in (0, 16):
                    self.assertEqual(output.crop((x, y, x+1, y+16)).tobytes(), output.crop((x+15, y, x+16, y+16)).tobytes())
                    self.assertEqual(output.crop((x, y, x+16, y+1)).tobytes(), output.crop((x, y+15, x+16, y+16)).tobytes())
                    self.assertEqual(output.getpixel((x+7, y+7)), picture.getpixel((x+7, y+7)))
            self.assertNotEqual(output.getpixel((1, 7)), picture.getpixel((1, 7)))
        picture.putpixel((0, 0), (0, 0, 0, 0))
        with self.assertRaisesRegex(ValueError, 'opaque'):
            asset_2d.prepare_generated_png(png(picture), spec)

    def test_side_view_cli_and_legacy_requests_keep_explicit_projection(self):
        path=self.root/'platform-request.json'
        with redirect_stdout(StringIO()):
            cli.main(['tileset-request','--id','ruin-platform','--tile','left','--tile','middle','--tile','right',
                '--view','side-view','--no-seamless','--style','Original jungle platforms','--output',str(path)])
        spec=json.loads(path.read_text())['specification']
        self.assertEqual(spec['tileset']['view'],'side-view')
        self.assertFalse(spec['tileset']['seamless'])
        self.assertNotIn('view',self.spec['tileset'])
        legacy=asset_2d.generation_request(self.spec)
        self.assertIn('Use a consistent top-down',legacy['parameters']['prompt'])
        self.assertEqual(asset_2d.generation_request(deepcopy(self.spec)),legacy)

    def test_rejects_ambiguous_cells_animation_and_invalid_tile_contracts(self):
        mutations = []
        for value in [4, True, -1]:
            changed = deepcopy(self.spec); changed['tileset']['tiles']['wall']['frame'] = value; mutations.append(changed)
        changed = deepcopy(self.spec); changed['tileset']['tiles']['wall']['solid'] = 1; mutations.append(changed)
        changed = deepcopy(self.spec); del changed['tileset']['tiles']['wall']; mutations.append(changed)
        changed = deepcopy(self.spec); changed['tileset']['tiles']['alias'] = dict(frame=0, solid=True); mutations.append(changed)
        changed = deepcopy(self.spec); changed['tileset']['tiles']['wall']['frame'] = 0; mutations.append(changed)
        for change in [dict(kind='sprite'), dict(kind='tile'), dict(loop=True), dict(tileset=None),
                       dict(animations={'idle': dict(frames=[0], fps=1, loop=False)})]:
            mutations.append({**self.spec, **change})
        for changed in mutations:
            with self.subTest(spec=changed), self.assertRaises(ValueError): asset_2d.describe(changed)
        with self.assertRaises(ValueError): asset_2d.tileset_spec('terrain', ['grass', 'grass'], style='Original')
        with self.assertRaises(ValueError): asset_2d.tileset_spec('terrain', ['grass'], solid=['wall'], style='Original')
        legacy = {k: v for k, v in self.spec.items() if k != 'tileset'}
        asset_2d.describe(legacy)
        self.assertEqual(asset_2d.tiles(legacy)['tile-3']['frame'], 3)

    def test_mixed_opaque_terrain_and_transparent_overlay_cells(self):
        spec = deepcopy(self.spec); spec['require_alpha'] = True
        with Image.open(BytesIO(self.raw)) as picture:
            picture.putpixel((16, 0), (0, 0, 0, 0))
            out = BytesIO(); picture.save(out, format='PNG')
        self.assertTrue(asset_2d.inspect_png(out.getvalue(), spec)['transparency'])
        with self.assertRaises(ValueError): asset_2d.inspect_png(self.raw, spec)

    def test_workshop_review_and_zip_preserve_tiles_and_owner_acceptance(self):
        with redirect_stdout(StringIO()): prepared = asset_2d.prepare(self.root, self.source())
        app = App(self.root); app.resume(prepared['session_id']); folder = app.sessions_dir / app.session['id']
        request = prepared['request_ref']
        self.assertFalse(chat_build.context(self.root, folder)['files'])
        snapshot = chat_build.proposal_snapshot(self.root, folder, request)['files']
        self.assertIn('id="tile"', snapshot['index.html'])
        self.assertEqual(gameplay.load(folder)['plan'], asset_2d.plan(self.spec))
        with redirect_stdout(StringIO()): app.respond(request, 'approve', 'SYNTHETIC TEST: exact tile fixture acceptance')
        archive, _ = project_versions.export(self.root, folder, request)
        with zipfile.ZipFile(BytesIO(archive)) as zipped:
            self.assertEqual(zipped.read('terrain-check.png'), self.raw)
            self.assertEqual(json.loads(zipped.read('asset-spec.json'))['tileset'], self.spec['tileset'])
            self.assertIn(b'drawMap', zipped.read('sprite-player.js'))
        self.assertTrue(chat_build.verify(self.root, folder)['passed'])

    def test_entity_binding_and_reviewed_player_upgrade(self):
        entity = dict(id='terrain', role='tileset', purpose='Original terrain', activation='startup',
            required_clips=['default'], machine=None, generation=self.spec, asset_ref=None,
            binding=dict(file='app.js', replace=''))
        sprite_project.validate_plan(dict(version=1, entities=[entity]))
        changed = {**entity, 'required_clips': ['idle']}
        with self.assertRaises(ValueError): sprite_project.validate_entity_asset(changed, self.spec)
        source = self.source(); ref = asset_library.register(self.root, source)
        snapshot = dict(assets=[asset_library.summary(self.root, ref)])
        # A known tile selection supplies the current player; later code-only revisions retain it.
        basis = {'index.html':'<html><body><script src="app.js"></script></body></html>', 'app.js':'void 0;', 'sprite-player.js':'/* older saved player */'}
        build = dict(title='Terrain', summary='Tile integration', files=[dict(path=k,content=v) for k,v in basis.items()])
        selected = asset_library.build_from_reference(self.root, snapshot, ref, build, basis)
        files = {f['path']: f['content'] for f in selected['files']}
        self.assertEqual(files['sprite-player.js'], asset_2d.player_source())
        preserved = asset_library.preserve_files(dict(title='Retain',summary='Keep tiles',files=[dict(path='app.js',content='void 1;')]), files)
        self.assertEqual(next(f['content'] for f in preserved['files'] if f['path']=='asset.js'), files['asset.js'])

    def test_generated_entity_plan_transport_integration_and_exact_export(self):
        self.spec['tileset'].update(edge_mode='autotile', view='side-view')
        entity = dict(id='terrain', role='tileset', purpose='Terrain map', activation='startup',
            required_clips=['default'], machine=None, generation=self.spec, asset_ref=None,
            binding=dict(file='app.js', replace=''))
        obstacle = dict(entity, id='obstacles', role='prop', purpose='Individually placed obstacles')
        response = dict(intent='implement', expected_revision=0, plan=dict(version=1, entities=[entity, obstacle]))
        wire = wire_reply(response, sprite_project.RESPONSE_SCHEMA)
        Draft202012Validator(structured_schema(sprite_project.RESPONSE_SCHEMA)).validate(wire)
        self.assertEqual(decode_structured(wire, sprite_project.RESPONSE_SCHEMA), response)
        ref = asset_library.register(self.root, self.source())
        app = App(self.root); app.start('SYNTHETIC tile entity', chat_only=True)
        folder = app.sessions_dir / app.session['id']
        files = {'index.html':'<html><body><canvas id="map"></canvas><script src="app.js"></script></body></html>',
            'app.js':"""EmberSprites.createScene().then(scene => {
                const ctx = document.querySelector('canvas').getContext('2d');
                const terrain = scene.createEntity('terrain');
                terrain.drawMap(ctx, [['grass', 'grass', null, 'grass'], ['grass', 'wall', 'wall', 'grass']]);
                const obstacles = scene.createEntity('obstacles');
                obstacles.drawTile(ctx, 'wall', 64, 0);
            });"""}
        build = dict(title='Tile entity', summary='Synthetic terrain map', files=[dict(path=k,content=v) for k,v in files.items()])
        calls = []
        def generate(root, session, turn, request, **kwargs):
            calls.append(request)
            return dict(asset_ref=ref)  # Synthetic provider: no network, credentials or credit use.
        prepared, saved = sprite_project.prepare(self.root, folder, response, dict(assets=[]), build, {},
            'synthetic-tile-entity-12345678', generate=generate)
        self.assertEqual(len(calls), 1)
        self.assertEqual(saved['plan']['entities'][0]['asset_ref'], ref)
        self.assertEqual(saved['plan']['entities'][1]['asset_ref'], ref)
        self.assertEqual(saved['plan']['entities'][1]['role'], 'prop')
        with redirect_stdout(StringIO()):
            request = chat_build.propose_build(self.root, folder, 'tile-entity', 'Synthetic tile integration', prepared)
            app.respond(request, 'approve', 'SYNTHETIC TEST: accept exact terrain entity')
        archive, _ = project_versions.export(self.root, folder, request)
        with zipfile.ZipFile(BytesIO(archive)) as zipped:
            self.assertEqual(zipped.read('sprites/'+ref+'/terrain-check.png'), self.raw)
            exported = json.loads(zipped.read('sprites/'+ref+'/asset-spec.json'))
            self.assertEqual(exported['tileset'], self.spec['tileset'])

    def test_tile_task_detection_and_actual_javascript_runtime(self):
        frozen = dict(document=dict(scope=dict(asset_budget=dict(environment=1), out_of_scope=[])),
            tasks=[dict(id='terrain', title='Add terrain tiles')], selected_task='terrain')
        self.assertIsNotNone(task_artwork.policy(frozen, dict(files=[dict(path='app.js')])))
        node = shutil.which('node')
        if not node: self.skipTest('Optional Node runtime is unavailable')
        runtime = Path(asset_2d.__file__).with_name('asset_lab') / 'sprite-player.js'
        result = subprocess.run([node, str(ROOT / 'tests/tile_player_test.js'), str(runtime)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__': unittest.main()
