"""Real offline browser sprite integration rehearsal; synthetic art, model replies and owner decisions."""
from contextlib import redirect_stdout
import argparse
from datetime import datetime, timezone
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import uuid
import zipfile

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ember_harness import asset_2d, asset_library, chat_build, gameplay, polish_runtime, project_versions
from ember_harness.local_ui import App


def fixture():
    """Small asymmetric original fixture with visibly different occupied frames."""
    spec = dict(profile='sprite-atlas-v1', id='sprite-check', display_name='Sprite integration check',
        art_direction='Synthetic original character for integration checks; not generated production art.', kind='sprite',
        frame_size=[32, 48], grid=[4, 3], frames=12, fps=10, loop=True, pivot=[.5, 1],
        blend='source-over', sampling='nearest', require_alpha=True, default_animation='idle', animations=dict(
            idle=dict(frames=[0, 1], fps=4, loop=True), walk=dict(frames=[2, 4, 3, 5], fps=10, loop=True),
            attack=dict(frames=[6, 7, 8], fps=4, loop=False, next='idle'),
            death=dict(frames=[9, 10, 11], fps=8, loop=False)),
        production=dict(method='scripted', tool='sprite-check-fixture-v1', prompt='Original asymmetric fixture', seed=1))
    image = Image.new('RGBA', (128, 144))
    for index in range(12):
        x, y = index % 4 * 32, index // 4 * 48
        frame = Image.new('RGBA', (32, 48)); draw = ImageDraw.Draw(frame)
        draw.rectangle((8, 8, 22, 39), fill=(40 + index * 15, 100, 160, 255))
        draw.rectangle((21, 14, 28, 20), fill=(255, 210, 20, 255))
        draw.rectangle((8 + index % 2 * 3, 40, 12 + index % 2 * 3, 47), fill='white')
        draw.rectangle((18 - index % 2 * 3, 40, 22 - index % 2 * 3, 47), fill='white')
        image.paste(frame, (x, y))
    stream = BytesIO(); image.save(stream, format='PNG')
    return spec, stream.getvalue()


def tile_fixture():
    """Original colored terrain cells for offline tile rendering checks."""
    spec = asset_2d.tileset_spec('terrain-check', ['grass', 'wall', 'water', 'path'],
        style='Synthetic original top-down tile fixture; not generated production artwork.',
        tile_size=(16, 16), columns=2, solid=['wall', 'water'])
    spec['production'] = dict(method='scripted', tool='tile-check-fixture-v1',
        prompt='Original colored terrain fixture for offline checks', seed=1)
    picture = Image.new('RGBA', (32, 32)); draw = ImageDraw.Draw(picture)
    for i, color in enumerate(['#308040', '#806050', '#3050b0', '#c0a060']):
        x, y = i % 2 * 16, i // 2 * 16
        draw.rectangle((x, y, x+15, y+15), fill=color)
        draw.rectangle((x+5, y+5, x+9, y+9), fill='#f0d080')
    stream = BytesIO(); picture.save(stream, format='PNG')
    return spec, stream.getvalue()


def html(files):
    parser = chat_build.ResourcePreview(files); parser.feed(files['index.html']); parser.close()
    return ''.join(parser.output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tiles', action='store_true', help='Rehearse the static tile workshop and tilemap APIs')
    args = parser.parse_args(argv)
    runtime = polish_runtime.discover(ROOT, fingerprints=False)
    output = ROOT / ('.harness/tile-checks' if args.tiles else '.harness/sprite-checks') / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])
    output.mkdir(parents=True)
    isolated = output / 'fixture'; (isolated / 'examples').mkdir(parents=True); (isolated / 'examples/product_demo.py').touch()
    spec, raw = tile_fixture() if args.tiles else fixture()
    source = isolated / '.harness/asset-source/character'; asset_2d.write_source(source, raw, spec)
    ref = asset_library.register(isolated, source)
    app = App(isolated); app.start('SYNTHETIC sprite rehearsal', chat_only=True)
    folder = app.sessions_dir / app.session['id']
    response = dict(message='Review the actual sprite and state transitions.', build=None, asset=dict(ref=ref, intent='use'))
    with redirect_stdout(StringIO()), patch('ember_harness.session_chat.run_muse', return_value=dict(response=json.dumps(response))):
        app.chat('Inspect the terrain tiles and repeated edges' if args.tiles else 'Try this character with idle, walk and attack', 'synthetic-sprite-check-12345678')
    request = chat_build.list_requests(folder)[-1]['ref']
    preview = chat_build.proposal_preview(isolated, folder, request)['html']
    assert not chat_build.context(isolated, folder)['manifest'], 'Preview must not apply the game'
    assert gameplay.load(folder)['plan'] == asset_2d.plan(spec)
    with redirect_stdout(StringIO()): app.respond(request, 'approve', 'SYNTHETIC TEST: exact fixture sprite acceptance')
    archive, _ = project_versions.export(isolated, folder, request)
    (output / 'sprite-game.zip').write_bytes(archive)
    with zipfile.ZipFile(BytesIO(archive)) as zipped:
        assert zipped.read(spec['id'] + '.png') == raw
        assert json.loads(zipped.read('asset-spec.json')) == spec
        files = {name: zipped.read(name).decode('utf-8') for name in ('index.html', 'app.js', 'asset.js', 'sprite-player.js')}
    assert chat_build.verify(isolated, folder)['passed']
    source_input = output / 'input.json'
    source_input.write_text(json.dumps(dict(preview=preview, exported=html(files), variant='tiles' if args.tiles else 'sprites')), encoding='utf-8')
    env = dict(os.environ, EMBER_PLAYWRIGHT_MODULE=runtime['module'], EMBER_BROWSER_EXECUTABLE=runtime['browser'])
    with (output / 'browser.log').open('wb') as log:
        process = subprocess.run([runtime['node'], str(ROOT / 'tools/sprite_check.js'), str(source_input), str(output)],
            env=env, stdout=log, stderr=log, timeout=90)
    if process.returncode:
        print(str(output / 'browser.log')); return 1
    report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
    report.update(basis='Synthetic original fixture artwork, model replies and owner decisions; real PNG decoding, canvas pixels and desktop/mobile controls in sandboxed preview and ZIP game. No live model calls.',
        exact_png_export=True, exact_spec_export=True, unapplied_preview=True, asset_acceptance_separate=True)
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(str(output / 'report.json'))
    return 0


if __name__ == '__main__': raise SystemExit(main())
