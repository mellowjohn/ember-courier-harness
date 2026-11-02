"""Bounded PNG atlases, image-tool handoffs and reproducible scripted VFX.

No network calls or arbitrary source execution. Tool requests are data for an
authorized host; imported pixels still require the ordinary asset acceptance.
"""
from base64 import b64decode, b64encode
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import math
import random
import re
import warnings

from PIL import Image, ImageDraw, ImageFilter

from .core import canonical, digest

PROFILE = 'sprite-atlas-v1'
MAX_PNG = 360_000
PREFIX = 'globalThis.EMBER_ASSET = Object.freeze('
SUFFIX = ');\n'
PLAYER_INSTRUCTION = (
    'For PNG atlases the host supplies and retains sprite-player.js, loaded before scene code. '
    'Use const atlas = await EmberSprites.load(EMBER_ASSET) inside async startup, catching load failures visibly; '
    'const actor = atlas.createPlayer() or atlas.createPlayer("idle"); wait for load before rendering. '
    'Call actor.update(deltaSeconds) once per game tick; it returns animation names completed during that tick. '
    'actor.play(name) preserves progress when already playing that name; actor.play(name,{restart:true}) replays an action. '
    'actor.draw(ctx,x,y,{scale:1,flipX:false}) handles source cells, pivot, sampling and blend and restores canvas state. '
    'actor.animation, frame, clipFrame and completed expose playback state; seek(index) selects a clip-local frame. '
    'Use declared spec.animations names only; legacy atlases have one "default" animation. '
    'Each named clip has zero-based frames:[indices], fps, loop and optional next (another clip or null). '
    'Nonlooping clips hold their final frame unless next is set; spec.default_animation selects startup. '
    'Bind idle/walk to movement, block unwanted attack restarts, and use next:"idle" for an attack return. '
    'Use pivot [0.5,1] for grounded characters and flipX for a shared facing direction. '
    'Keep world movement, collision, damage and effect lifetime in gameplay code. '
    'Preserve existing game mechanics and replace the intended artwork at its existing draw site. '
    'Verify actual PNG loading, correct clips on input, completion, alignment and facing at gameplay scale. '
    'For tile or tileset artwork declare tileset:{seamless:true|false,tiles:{name:{frame:0,solid:false}}}; '
    'frames counts occupied cells, not animation steps; omit animations, use loop:false and pivot:[0,0]. '
    'Use kind tile with grid:[1,1] and frames:1 for an individual tile. '
    'atlas.drawTile(ctx,"grass",x,y,{scale:2}) draws a static tile at its top-left corner. '
    'atlas.drawMap(ctx,rows,x,y,{scale:2}) draws a rectangular array of tile names or zero-based cell indices; null is empty. '
    'atlas.tiles exposes named frame/solid metadata; atlas.solidAt(rows,column,row) queries declared collision hints. '
    'Tilemaps have at most 256 rows/columns and 16384 cells. Gameplay owns collision response. '
    'For side-view platformers declare tileset.view:"side-view"; use seamless:false for sets with exposed caps and surface trim. '
    'Plan compatible left cap, repeating middle, right cap, interior fill and underside pieces rather than a fully outlined block repeated everywhere. '
    'Use the same terrain layout and tile dimensions for drawing and collision; align the walkable surface with the collider. '
    'Clip partial tiles to existing platform bounds when preserving non-grid geometry; do not stretch a 22px platform to a full 48px art cell. '
    'Keep decorative layers separate from solid terrain. Verify several joined tiles and exposed ends in the actual game, not just each atlas cell. '
    'For entity plans use role tileset, required_clips:["default"], machine:null; scene.createEntity(id) exposes the same tile APIs. '
)

# Chat prepares the same specification consumed by the existing CLI importer.
GENERATION_SCHEMA = dict(type='object', additionalProperties=False, properties={
    'profile': {'enum': [PROFILE]},
    'id': dict(type='string', pattern='^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$', maxLength=64),
    'display_name': dict(type='string', minLength=1, maxLength=80),
    'art_direction': dict(type='string', minLength=1, maxLength=2000),
    'kind': {'enum': ['sprite', 'tile', 'tileset', 'background', 'vfx']},
    'frame_size': dict(type='array', minItems=2, maxItems=2, items=dict(type='integer', minimum=1, maximum=2048)),
    'grid': dict(type='array', minItems=2, maxItems=2, items=dict(type='integer', minimum=1, maximum=64)),
    'frames': dict(type='integer', minimum=1, maximum=64),
    'fps': dict(type='integer', minimum=1, maximum=60),
    'loop': dict(type='boolean'),
    'pivot': dict(type='array', minItems=2, maxItems=2, items=dict(type='number', minimum=0, maximum=1)),
    'blend': {'enum': ['source-over', 'lighter']},
    'sampling': {'enum': ['nearest', 'smooth']},
    'require_alpha': dict(type='boolean'),
    'production': dict(type='object', additionalProperties=False,
        required=['method', 'tool', 'prompt', 'seed'], properties=dict(
            method={'enum': ['generated']}, tool={'enum': ['image_gen', 'muse_image']},
            prompt=dict(type='string', minLength=1, maxLength=4000), seed=dict(type='null'))),
})
GENERATION_SCHEMA['required'] = list(GENERATION_SCHEMA['properties'])
# Optional so previously reviewed packages and saved requests retain their hashes.
GENERATION_SCHEMA['properties'].update(
    animations=dict(type='object', minProperties=1, maxProperties=32,
        propertyNames=dict(pattern='^[a-z][a-z0-9_-]{0,31}$'), additionalProperties=dict(
            type='object', additionalProperties=False, required=['frames', 'fps', 'loop'], properties=dict(
                frames=dict(type='array', minItems=1, maxItems=64, items=dict(type='integer', minimum=0, maximum=63)),
                fps=dict(type='integer', minimum=1, maximum=60), loop=dict(type='boolean'),
                next=dict(type=['string', 'null'], pattern='^[a-z][a-z0-9_-]{0,31}$')))),
    default_animation=dict(type='string', pattern='^[a-z][a-z0-9_-]{0,31}$'),
    tileset=dict(type='object', additionalProperties=False, required=['seamless', 'tiles'], properties=dict(
        seamless=dict(type='boolean'), view=dict(enum=['top-down', 'side-view']), tiles=dict(type='object', minProperties=1, maxProperties=64,
            propertyNames=dict(pattern='^[a-z][a-z0-9_-]{0,31}$'), additionalProperties=dict(
                type='object', additionalProperties=False, required=['frame', 'solid'], properties=dict(
                    frame=dict(type='integer', minimum=0, maximum=63), solid=dict(type='boolean')))))))


def animations(spec):
    """Normalize legacy single sequences without altering their reviewed specification."""
    if spec['kind'] in ('tile', 'tileset') and 'animations' not in spec:
        return {'default': dict(frames=[0], fps=spec['fps'], loop=False)}
    return spec.get('animations', {'default': dict(frames=list(range(spec['frames'])), fps=spec['fps'], loop=spec['loop'])})


def tiles(spec):
    """Named static cells; legacy tilesets receive stable row-major names."""
    if spec['kind'] not in ('tile', 'tileset'):
        return {}
    return spec.get('tileset', {}).get('tiles', {
        'tile-' + str(i): dict(frame=i, solid=False) for i in range(spec['frames'])})


def tile_prompt(spec):
    # Leave historical requests reconstructible; richer layout is opt-in metadata.
    if 'tileset' not in spec and spec['kind'] != 'tile':
        return ''
    layout = spec.get('tileset', {})
    if layout.get('view') == 'side-view':
        return ('\nStatic tile layout (zero-based row-major cell indices): ' + json.dumps(tiles(spec), sort_keys=True) +
            '. These cells are different terrain tiles, not animation frames. '
            'Use a side-view orthographic platformer cross-section, never an overhead view or perspective. '
            'Keep a consistent texel scale, palette, lighting and walkable surface height. '
            'Fill each cell edge-to-edge with no gutters, padding, gaps, labels or atlas borders. ' +
            ('These are seamless fill textures: opposite edges must repeat horizontally and vertically without outlines or surface trim. '
             if layout.get('seamless') else
             'Follow each named tile role: left and right caps only at exposed ends, middle sections repeat horizontally, '
             'interior fill continues beneath the surface, and underside trim appears only on exposed bottoms. '
             'Do not frame every cell or repeat end caps, grass trim or corner decorations at internal joins. '
             'Matching neighbor edges must meet at the same height and share their edge colors. '))
    return ('\nStatic tile layout (zero-based row-major cell indices): ' + json.dumps(tiles(spec), sort_keys=True) +
        '. These cells are different terrain tiles, not animation frames. Fill each cell edge-to-edge; '
        'no gutters, padding, margins, gaps, perspective or shadows outside tile boundaries. '
        'Use a consistent top-down orthographic view, texel scale, palette and lighting. ' +
        ('Opposite edges of every tile must repeat seamlessly horizontally and vertically; avoid edge seams. '
         if spec.get('tileset', {}).get('seamless') else
         'Keep neighboring tile edges compatible with their declared terrain purpose. '))


def tileset_spec(name, names, *, style, tile_size=(32, 32), columns=4,
                 solid=(), seamless=True, tool='muse_image', view=None):
    """Prepare a static single tile or named tileset for the existing image handoff."""
    if (not isinstance(names, (list, tuple)) or not 1 <= len(names) <= 64 or
            any(not isinstance(n, str) for n in names) or len(set(names)) != len(names)):
        raise ValueError('Use one to 64 unique tile names')
    if type(columns) is not int or not 1 <= columns <= 64:
        raise ValueError('Use one to 64 columns')
    if not set(solid) <= set(names):
        raise ValueError('Solid tiles must name declared tiles')
    columns = min(columns, len(names))
    spec = dict(profile=PROFILE, id=name, display_name=name.replace('-', ' ').title(),
        art_direction=style, kind='tile' if len(names) == 1 else 'tileset',
        frame_size=list(tile_size), grid=[columns, math.ceil(len(names) / columns)],
        frames=len(names), fps=1, loop=False, pivot=[0, 0], blend='source-over',
        sampling='nearest', require_alpha=False,
        tileset=dict(seamless=seamless, tiles={n: dict(frame=i, solid=n in solid) for i, n in enumerate(names)}),
        production=dict(method='generated', tool=tool,
            prompt='Original game terrain tiles: ' + ', '.join(names) + '.', seed=None))
    if view is not None:
        spec['tileset']['view'] = view
    describe(spec)
    return spec


def animation_prompt(spec):
    if 'animations' not in spec:
        return ''
    return '\nAnimation layout (zero-based row-major cell indices): ' + json.dumps(spec['animations'], sort_keys=True) + '. Draw the named action in each assigned cell; keep the same character, scale and foot/pivot alignment across all actions. '


def describe(spec):
    fields = {'profile', 'id', 'display_name', 'art_direction', 'kind', 'frame_size',
              'grid', 'frames', 'fps', 'loop', 'pivot', 'blend', 'sampling',
              'require_alpha', 'production'}
    if (not isinstance(spec, dict) or not fields <= set(spec) or
            set(spec) - fields - {'animations', 'default_animation', 'tileset'} or spec['profile'] != PROFILE):
        raise ValueError('A complete sprite-atlas-v1 specification is required')
    for field, limit in [('display_name', 80), ('art_direction', 2000)]:
        if not isinstance(spec[field], str) or not 1 <= len(spec[field].strip()) <= limit:
            raise ValueError('Invalid ' + field)
    if not isinstance(spec['id'], str) or not re.fullmatch('[a-z][a-z0-9]*(?:-[a-z0-9]+)*', spec['id']) or len(spec['id']) > 64:
        raise ValueError('Use a bounded lowercase asset slug')
    if spec['kind'] not in ('sprite', 'tile', 'tileset', 'background', 'vfx'):
        raise ValueError('Unsupported 2D asset kind')
    for field, maximum in [('frame_size', 2048), ('grid', 64)]:
        value = spec[field]
        if not isinstance(value, list) or len(value) != 2 or any(type(n) is not int or not 1 <= n <= maximum for n in value):
            raise ValueError('Invalid ' + field)
    width, height = [a*b for a, b in zip(spec['frame_size'], spec['grid'])]
    if width > 2048 or height > 2048 or width*height > 4_194_304:
        raise ValueError('Atlas exceeds the 2048 pixel side limit')
    if type(spec['frames']) is not int or not 1 <= spec['frames'] <= min(64, math.prod(spec['grid'])):
        raise ValueError('Invalid frame count')
    if spec['kind'] == 'tile' and (spec['grid'] != [1, 1] or spec['frames'] != 1):
        raise ValueError('An individual tile requires one cell')
    if type(spec['fps']) is not int or not 1 <= spec['fps'] <= 60:
        raise ValueError('Invalid animation frame rate')
    if any(type(spec[f]) is not bool for f in ('loop', 'require_alpha')):
        raise ValueError('Use explicit loop and alpha flags')
    pivot = spec['pivot']
    if not isinstance(pivot, list) or len(pivot) != 2 or any(type(n) not in (float, int) or not 0 <= n <= 1 for n in pivot):
        raise ValueError('Use a normalized two-coordinate pivot')
    if spec['blend'] not in ('source-over', 'lighter') or spec['sampling'] not in ('nearest', 'smooth'):
        raise ValueError('Invalid blend or sampling mode')
    if 'tileset' in spec:
        layout = spec['tileset']
        if spec['kind'] not in ('tile', 'tileset'):
            raise ValueError('Tile metadata requires tile or tileset artwork')
        if (not isinstance(layout, dict) or not {'seamless', 'tiles'} <= set(layout) or
                set(layout) - {'seamless', 'tiles', 'view'} or
                ('view' in layout and layout['view'] not in ('top-down', 'side-view')) or
                type(layout['seamless']) is not bool or not isinstance(layout['tiles'], dict) or
                not 1 <= len(layout['tiles']) <= 64):
            raise ValueError('Declare seamless and one to 64 named tiles')
        for name, tile in layout['tiles'].items():
            if (not isinstance(name, str) or not re.fullmatch('[a-z][a-z0-9_-]{0,31}', name) or
                    not isinstance(tile, dict) or set(tile) != {'frame', 'solid'} or
                    type(tile['frame']) is not int or not 0 <= tile['frame'] < spec['frames'] or
                    type(tile['solid']) is not bool):
                raise ValueError('Each named tile requires a declared cell and boolean solid hint')
        if (len(layout['tiles']) != spec['frames'] or
                {tile['frame'] for tile in layout['tiles'].values()} != set(range(spec['frames']))):
            raise ValueError('Name every declared tile cell exactly once')
    if ('tileset' in spec or spec['kind'] == 'tile') and (
            spec['loop'] or 'animations' in spec or 'default_animation' in spec):
        raise ValueError('Tiles are static cells, not animation clips')
    clips = animations(spec)
    if not isinstance(clips, dict) or not 1 <= len(clips) <= 32:
        raise ValueError('Use between one and 32 named animations')
    for name, clip in clips.items():
        if not isinstance(name, str) or not re.fullmatch('[a-z][a-z0-9_-]{0,31}', name):
            raise ValueError('Invalid animation name')
        if (not isinstance(clip, dict) or not {'frames', 'fps', 'loop'} <= set(clip) or
                set(clip) - {'frames', 'fps', 'loop', 'next'}):
            raise ValueError('Each animation requires frames, fps and loop')
        indices = clip['frames']
        if (not isinstance(indices, list) or not 1 <= len(indices) <= 64 or
                any(type(n) is not int or not 0 <= n < spec['frames'] for n in indices)):
            raise ValueError('Animation frames must reference declared atlas cells')
        if type(clip['fps']) is not int or not 1 <= clip['fps'] <= 60 or type(clip['loop']) is not bool:
            raise ValueError('Invalid animation timing')
        next_clip = clip.get('next')
        if next_clip is not None and (not isinstance(next_clip, str) or next_clip not in clips or clip['loop']):
            raise ValueError('Only a nonlooping animation may transition to another named animation')
    if 'default_animation' in spec and ('animations' not in spec or
            not isinstance(spec['default_animation'], str) or spec['default_animation'] not in clips):
        raise ValueError('Default animation must name a declared animation')
    production = spec['production']
    if not isinstance(production, dict) or set(production) != {'method', 'tool', 'prompt', 'seed'}:
        raise ValueError('Record the production method, tool, prompt and seed')
    if production['method'] not in ('generated', 'scripted') or not isinstance(production['tool'], str) or not re.fullmatch('[A-Za-z0-9_.:-]{1,100}', production['tool']):
        raise ValueError('Invalid production method or tool')
    if not isinstance(production['prompt'], str) or not 1 <= len(production['prompt'].strip()) <= 4000:
        raise ValueError('Record a bounded production prompt')
    if production['seed'] is not None and (type(production['seed']) is not int or not 0 <= production['seed'] <= 2**32-1):
        raise ValueError('Use a 32-bit seed or null for an unseeded image tool')
    return dict(id=spec['id'], display_name=spec['display_name'], profile=PROFILE,
                dimensions_px=[width, height], art_direction=spec['art_direction'])


def generation_request(spec):
    """Tool-ready parameters; this does not invoke a provider or authorize spending."""
    info = describe(spec)
    if spec['production']['method'] != 'generated':
        raise ValueError('Choose generated production for an image-tool request')
    prompt = (spec['production']['prompt'] + '\nArt direction: ' + spec['art_direction'] +
        '\nOriginal game art. No text, logos, labels, watermarks, borders or contact-sheet decoration. '
        f"Export one PNG atlas exactly {info['dimensions_px'][0]}x{info['dimensions_px'][1]} pixels; "
        f"{spec['grid'][0]} columns, {spec['grid'][1]} rows of {spec['frame_size'][0]}x{spec['frame_size'][1]} cells. "
        f"First {spec['frames']} cells in row-major order. Consistent scale, silhouette, lighting and pivot "
        f"{spec['pivot']}. Keep every sprite within its cell. " +
        ('True transparent background, no painted checkerboard. ' if spec['require_alpha'] else '') +
        ('Show a coherent anticipation, impact and dissipation sequence. No heat distortion.' if spec['kind'] == 'vfx' else '') +
        animation_prompt(spec) + tile_prompt(spec))
    body = dict(version=1, specification=spec, tool=spec['production']['tool'],
                parameters=dict(prompt=prompt, transparent_background=spec['require_alpha']),
                basis='Prepared handoff only. Provider execution, cost authorization and visual acceptance are separate.')
    return {**body, 'request_sha256': digest(body)}


def inspect_png(raw, spec):
    info = describe(spec)
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_PNG:
        raise ValueError('PNG exceeds the 360000 byte package budget')
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(BytesIO(raw)) as image:
            if image.format != 'PNG' or list(image.size) != info['dimensions_px'] or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('Use a single PNG with the exact declared atlas dimensions')
            image.verify()
        with Image.open(BytesIO(raw)) as image:
            image.load()
            rgba = image.convert('RGBA')
    alpha = rgba.getchannel('A')
    extrema = alpha.getextrema()
    if spec['require_alpha'] and not (extrema[0] < 255 and extrema[1] > 0):
        raise ValueError('The atlas requires actual transparent and visible pixels')
    fw, fh = spec['frame_size']
    frames = []
    for index in range(spec['frames']):
        x, y = index % spec['grid'][0]*fw, index // spec['grid'][0]*fh
        cell = alpha.crop((x, y, x+fw, y+fh))
        bounds = cell.getbbox()
        if bounds is None:
            raise ValueError('Every declared animation frame must contain visible pixels')
        if spec['require_alpha'] and spec['kind'] not in ('tile', 'tileset') and cell.getextrema()[0] == 255:
            raise ValueError('Every declared frame requires actual transparency')
        frames.append(dict(index=index, rect=[x, y, fw, fh], alpha_bounds=list(bounds)))
    return dict(profile=PROFILE, sha256=sha256(raw).hexdigest(), bytes=len(raw),
                dimensions_px=info['dimensions_px'], frames=frames,
                transparency=extrema[0] < 255, production_sha256=digest(spec['production']),
                basis='PNG, dimensions, frame occupancy and transparency checked. Visual quality, frame consistency and claimed provider origin require review.')


def package(raw, spec):
    report = inspect_png(raw, spec)
    result = PREFIX + canonical(dict(spec=spec, report=report, png_base64=b64encode(raw).decode('ascii'))).decode('utf-8') + SUFFIX
    if len(result.encode('utf-8')) > 524288:
        raise ValueError('Atlas metadata and pixels exceed the asset.js budget')
    return result


def write_source(output, raw, spec, request=None):
    """Create one validated source package, shared by chat and the CLI."""
    content = package(raw, spec)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / (spec['id'] + '.png')).write_bytes(raw)
    (output / 'asset-spec.json').write_text(json.dumps(spec, indent=2), encoding='utf-8')
    if request:
        (output / 'generation-request.json').write_text(json.dumps(request, indent=2), encoding='utf-8')
    (output / 'asset.js').write_text(content, encoding='utf-8', newline='\n')
    return dict(source=str(output), png_sha256=inspect_png(raw, spec)['sha256'],
                status='prepared', basis='Local artifact only; no game writes or asset acceptance')


def prepare_generated_png(raw, spec):
    """Explicit Muse Image preparation: atlas sizing, magenta matte and PNG packing.

    Muse Image returns opaque images at its own resolution. Preserve its source
    separately; this deliberate conversion produces the declared runtime atlas.
    """
    info = describe(spec)
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= 12 * 1024 * 1024:
        raise ValueError('Muse Image source exceeds the preparation limit')
    with Image.open(BytesIO(raw)) as picture:
        if picture.format != 'PNG' or picture.width * picture.height > 16_777_216 or getattr(picture, 'n_frames', 1) != 1:
            raise ValueError('Muse Image must return one bounded PNG')
        picture.load()
        original_size = list(picture.size)
        expected = info['dimensions_px']
        if abs((picture.width / picture.height) / (expected[0] / expected[1]) - 1) > .08:
            raise ValueError('Generated artwork has the wrong aspect ratio; the original is saved for review')
        picture = picture.convert('RGBA')
        if spec['require_alpha']:
            # A fixed matte is requested from Muse, never inferred from subject colors.
            pixels = picture.load()
            for y in range(picture.height):
                for x in range(picture.width):
                    r, g, b, a = pixels[x, y]
                    distance = max(255-r, g, 255-b)
                    if distance < 96:
                        alpha = max(0, min(255, round((distance-24) * 255 / 72)))
                        pixels[x, y] = (r, g, b, min(a, alpha))
        picture = picture.resize(expected, Image.Resampling.NEAREST if spec['sampling'] == 'nearest' else Image.Resampling.LANCZOS)
        output = BytesIO(); picture.save(output, format='PNG', optimize=True)
        prepared = output.getvalue()
        quantized = False
        if len(prepared) > MAX_PNG:
            picture = picture.quantize(colors=256, method=Image.Quantize.FASTOCTREE)
            output = BytesIO(); picture.save(output, format='PNG', optimize=True)
            prepared = output.getvalue(); quantized = True
    report = inspect_png(prepared, spec)
    return prepared, dict(version=1, source_sha256=sha256(raw).hexdigest(),
        source_dimensions=original_size, output_sha256=report['sha256'], output_dimensions=expected,
        matte_removed=spec['require_alpha'], matte='#FF00FF' if spec['require_alpha'] else None,
        palette_quantized=quantized, basis='Scripted sizing and matte removal; inspect edges and frame consistency before acceptance')


def unpack(content):
    if not isinstance(content, str) or len(content.encode('utf-8')) > 524288 or not content.startswith(PREFIX) or not content.endswith(SUFFIX):
        raise ValueError('Use a canonical Ember PNG package')
    try:
        data = json.loads(content[len(PREFIX):-len(SUFFIX)])
        raw = b64decode(data['png_base64'], validate=True)
        report = inspect_png(raw, data['spec'])
        if data.get('report') != report or package(raw, data['spec']) != content:
            raise ValueError('Atlas bytes or measurements changed')
        return raw, data['spec'], report
    except (KeyError, TypeError, UnicodeError) as error:
        raise ValueError('Invalid PNG asset package') from error


def effect_spec(name='ember-impact', *, style='Original warm amber sparks with a bright ivory core', seed=7):
    return dict(profile=PROFILE, id=name, display_name='Ember impact', art_direction=style,
                kind='vfx', frame_size=[96, 96], grid=[4, 3], frames=12, fps=24,
                loop=False, pivot=[.5, .5], blend='lighter', sampling='smooth', require_alpha=True,
                production=dict(method='scripted', tool='ember.impact-v1',
                                prompt='Radial impact flash, expanding shock ring, ballistic sparks and soft glow.', seed=seed))


def render_effect(spec):
    """Deterministic built-in recipe, never an eval or a subprocess supplied by a model."""
    info = describe(spec)
    if spec['production']['method'] != 'scripted' or spec['production']['tool'] != 'ember.impact-v1' or spec['production']['seed'] is None or spec['kind'] != 'vfx':
        raise ValueError('Scripted VFX requires the seeded ember.impact-v1 recipe')
    if any(not 16 <= side <= 256 for side in spec['frame_size']):
        raise ValueError('The scripted recipe supports frame sizes from 16 to 256 pixels')
    atlas = Image.new('RGBA', info['dimensions_px'])
    fw, fh = spec['frame_size']
    scale = 3
    w, h = fw*scale, fh*scale
    rng = random.Random(spec['production']['seed'])
    sparks = [(rng.random()*math.tau, rng.uniform(.18, .38), rng.uniform(.6, 1)) for _ in range(28)]
    cx, cy = w/2, h/2
    unit = min(w, h)
    for index in range(spec['frames']):
        t = (index+.5)/spec['frames']
        layer = Image.new('RGBA', (w, h)); draw = ImageDraw.Draw(layer)
        fade = max(1, int(235*(1-t)**1.3))
        radius = unit*(.06+.31*t)
        draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), outline=(255, 158, 55, fade), width=max(1, int(unit*.015*(1-t))))
        core = unit*.16*(1-t)**2
        draw.ellipse((cx-core, cy-core, cx+core, cy+core), fill=(255, 239, 183, fade))
        for angle, speed, life in sparks:
            if t > life: continue
            distance = unit*speed*t
            x, y = cx+math.cos(angle)*distance, cy+math.sin(angle)*distance+unit*.09*t*t
            tail = unit*.045*(1-t)
            draw.line((x-math.cos(angle)*tail, y-math.sin(angle)*tail, x, y), fill=(255, 185, 80, fade), width=max(1, int(unit*.009)))
        glow = layer.filter(ImageFilter.GaussianBlur(unit*.018))
        frame = Image.alpha_composite(glow, layer).resize((fw, fh), Image.Resampling.LANCZOS)
        atlas.paste(frame, (index % spec['grid'][0]*fw, index // spec['grid'][0]*fh))
    out = BytesIO(); atlas.save(out, format='PNG', optimize=True)
    raw = out.getvalue(); inspect_png(raw, spec)
    return raw


def assemble(content):
    """An offline canvas workshop uses the exact PNG and its animation metadata."""
    _, spec, _ = unpack(content)
    from .chat_build import validate_files
    from .asset_workshop import TEMPLATES
    template = 'tile_' if spec['kind'] in ('tile', 'tileset') else 'sprite_'
    files = {name: (TEMPLATES / (template + name)).read_text(encoding='utf-8') for name in ('index.html', 'app.js')}
    files['asset.js'] = content
    files = attach_player(files, {})
    validate_files(files)
    return files


def player_source():
    return (Path(__file__).with_name('asset_lab') / 'sprite-player.js').read_text(encoding='utf-8')


def attach_player(files, basis):
    """Bundle the shared player in the exact proposal, ahead of scene scripts."""
    from html.parser import HTMLParser
    result = dict(files)
    runtime = basis.get('sprite-player.js', player_source())
    if 'sprite-player.js' in result and result['sprite-player.js'] != runtime:
        raise ValueError('Keep the prepared sprite player unchanged')
    result['sprite-player.js'] = runtime
    order = [name for name in ('asset.js','sprite-assets.js','sprite-plan.js','sprite-player.js') if name in result]
    managed = set(order)

    class Scripts(HTMLParser):
        def __init__(self, html):
            super().__init__(); self.first = None; self.players = []; self.open_player = None; self.html = html

        def source_index(self):
            line, col = self.getpos()
            return sum(len(s) for s in self.html.splitlines(keepends=True)[:line-1]) + col

        def handle_starttag(self, tag, attrs):
            if tag != 'script': return
            if self.first is None:
                self.first = self.source_index()
            if (dict(attrs).get('src') or '').removeprefix('./') in managed:
                self.open_player = self.source_index()

        def handle_endtag(self, tag):
            if tag == 'script' and self.open_player is not None:
                end = self.html.index('>', self.source_index()) + 1
                self.players.append((self.open_player, end)); self.open_player = None

    for name, html in list(result.items()):
        if not name.endswith('.html'): continue
        parser = Scripts(html); parser.feed(html); parser.close()
        if parser.open_player is not None:
            raise ValueError('Close asset/player script tags before scene code')
        # Synchronous data and player loads ahead of scene code, including missing/late/deferred tags.
        for start, end in reversed(parser.players): html = html[:start] + html[end:]
        parser = Scripts(html); parser.feed(html); parser.close()
        index = parser.first if parser.first is not None else len(html)
        loaders = ''.join('<script src="'+name+'"></script>' for name in order)
        result[name] = html[:index] + loaders + html[index:]
    return result


def plan(spec):
    """Observable workshop checks; arbitrary games keep their own gameplay plan."""
    if spec['kind'] in ('tile', 'tileset'):
        return dict(title=spec['display_name'] + ' tile inspection', scenarios=[
            dict(name='Tile atlas and repeated edges', viewport='desktop', steps=[
                dict(action='text', selector='#load-state', value='Asset ready'),
                dict(action='text', selector='#repeat-state', value='Repeated 4 × 4'),
                dict(action='click', selector='#repeat'),
                dict(action='text', selector='#repeat-state', value='Single tile')]),
            dict(name='Touch tile inspection', viewport='mobile', steps=[
                dict(action='text', selector='#load-state', value='Asset ready'),
                dict(action='tap', selector='#repeat'),
                dict(action='text', selector='#repeat-state', value='Single tile')])])
    return dict(title=spec['display_name'] + ' sprite playback', scenarios=[
        dict(name='PNG loads and playback pauses', viewport='desktop', steps=[
            dict(action='text', selector='#load-state', value='Asset ready'),
            dict(action='click', selector='#paused'),
            dict(action='text', selector='#playback-state', value='Paused'),
            dict(action='click', selector='#replay'),
            dict(action='text', selector='#playback-state', value='Playing')]),
        dict(name='Touch replay', viewport='mobile', steps=[
            dict(action='text', selector='#load-state', value='Asset ready'),
            dict(action='tap', selector='#replay'),
            dict(action='text', selector='#playback-state', value='Playing')])])


def prepare(root, source, *, session_id=None):
    from . import asset_library, chat_build
    from .local_ui import App
    from .recovery import exclusive
    ref = asset_library.register(root, source)
    record, spec, _ = asset_library.load(root, ref)
    if spec.get('profile') != PROFILE: raise ValueError('Choose a 2D atlas source')
    app = App(root)
    if session_id: app.resume(session_id)
    else: app.start(record['display_name'] + ' · 2D asset workshop', chat_only=True)
    folder = app.sessions_dir / app.session['id']
    with exclusive(folder / 'chat.lock'), exclusive(folder / 'build.lock'):
        current = chat_build.context(root, folder)
        if current['manifest']:
            raise ValueError('Use a fresh workshop, or integrate the known asset through chat in your existing game')
        files = assemble(record['package'])
        request = chat_build.propose_build(root, folder, 'sprite-' + ref[:24], 'Review an original 2D game asset',
            dict(title=record['display_name'], summary='Inspect the exact PNG atlas at gameplay scale before acceptance.',
                 files=[dict(path=k, content=v) for k, v in files.items()]), asset_source=asset_library.provenance(root, ref))
    from .asset_workshop import seed_guidance
    seed_guidance(folder, spec)
    return dict(session_id=app.session['id'], request_ref=request, status='awaiting_owner')
