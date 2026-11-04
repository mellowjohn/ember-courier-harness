"""Entity artwork plans, checked replacements and bounded multi-atlas packages.

Plans are descriptive data. Only ordinary exact build reviews grant writes and
each changed atlas gets its own asset.accept action in that review.
"""
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import re

from jsonschema import Draft202012Validator

from . import asset_2d
from .core import canonical, digest
from .recovery import atomic_json, read_json

MAX_ATLASES = 8
ASSETS_FILE = 'sprite-assets.js'
PLAN_FILE = 'sprite-plan.js'
ASSETS_PREFIX = 'globalThis.EMBER_SPRITE_ASSETS = Object.freeze('
PLAN_PREFIX = 'globalThis.EMBER_SPRITE_PLAN = Object.freeze('
SUFFIX = ');\n'
NAME = dict(type='string', pattern='^[a-z][a-z0-9_-]{0,31}$')
VALUE = dict(anyOf=[dict(type='boolean'), dict(type='number', minimum=-1e6, maximum=1e6)])
CONDITION = dict(type='object', additionalProperties=False, required=['signal', 'op', 'value'], properties=dict(
    signal=NAME, op=dict(enum=['eq', 'ne', 'gt', 'gte', 'lt', 'lte']), value=VALUE))
MACHINE_SCHEMA = dict(type='object', additionalProperties=False, required=['initial', 'signals', 'states', 'transitions'], properties=dict(
    initial=NAME,
    signals=dict(type='object', maxProperties=16, propertyNames=NAME, additionalProperties=dict(
        type='object', additionalProperties=False, required=['type', 'default'], properties=dict(type=dict(enum=['boolean','number']), default=VALUE))),
    states=dict(type='object', minProperties=1, maxProperties=16, propertyNames=NAME, additionalProperties=dict(
        type='object', additionalProperties=False, required=['clip','priority','interruptible','terminal','on_complete','markers'], properties=dict(
            clip=NAME, priority=dict(type='integer', minimum=0, maximum=1000), interruptible=dict(type='boolean'), terminal=dict(type='boolean'),
            on_complete=dict(anyOf=[NAME, dict(type='null')]), markers=dict(type='array', maxItems=16, items=dict(
                type='object', additionalProperties=False, required=['event','frame'], properties=dict(event=NAME,frame=dict(type='integer',minimum=0,maximum=63))))))),
    transitions=dict(type='array', maxItems=64, items=dict(type='object', additionalProperties=False,
        required=['from','to','event','when'], properties=dict(
            **{'from':dict(type='array',minItems=1,maxItems=16,uniqueItems=True,items=dict(type='string',pattern='^(?:\\*|[a-z][a-z0-9_-]{0,31})$'))},
            to=NAME,event=dict(anyOf=[NAME,dict(type='null')]),when=dict(type='array',maxItems=8,items=CONDITION))))))
ENTITY_SCHEMA = dict(type='object', additionalProperties=False,
    required=['id','role','purpose','activation','required_clips','asset_ref','generation','binding','machine'], properties=dict(
        id=NAME, role=dict(enum=['player','enemy','npc','prop','background','tileset','effect','ui']),
        activation=dict(enum=['startup','on_demand']),
        purpose=dict(type='string',minLength=1,maxLength=1000),
        required_clips=dict(type='array',maxItems=32,uniqueItems=True,items=NAME),
        asset_ref=dict(anyOf=[dict(type='string',pattern='^[0-9a-f]{64}$'),dict(type='null')]),
        generation=dict(anyOf=[asset_2d.GENERATION_SCHEMA,dict(type='null')]),
        binding=dict(anyOf=[dict(type='null'),dict(type='object',additionalProperties=False,required=['file','replace'],properties=dict(
            file=dict(type='string',pattern='^[a-z][a-z0-9_-]{0,63}\\.(?:js|html)$'),replace=dict(type='string',maxLength=4000)))]),
        machine=dict(anyOf=[MACHINE_SCHEMA,dict(type='null')])) )
PLAN_SCHEMA = dict(type='object',additionalProperties=False,required=['version','entities'],properties=dict(
    version=dict(const=1),entities=dict(type='array',minItems=1,maxItems=16,items=ENTITY_SCHEMA)))
RESPONSE_SCHEMA = dict(type='object',additionalProperties=False,required=['intent','expected_revision','plan'],properties=dict(
    intent=dict(enum=['plan','implement']),expected_revision=dict(type='integer',minimum=0),plan=PLAN_SCHEMA))

INSTRUCTION = (
    'sprite_project supplies the saved entity artwork plan, inventory, missing art and animation requirements. '
    'Start a new visual game with generated character and environment artwork as part of its first build. '
    'Do not wait for the user to request each image or leave default shape placeholders for characters and environments. '
    'Asset counts in project plans are estimates, not limits; do not stop or request an amendment because artwork exceeds them. '
    'Respect explicit requests for no generated artwork or a procedural-only or text-only game. '
    'When a game brief or request calls for authored/generated sprite art, include the entity plan with the build; '
    'infer the relevant entities and actions from its actual mechanics rather than leaving placeholder art or asking the user to name every necessary sheet. '
    'When building a game, decide its needed artwork from actual mechanics and entities, reuse compatible known assets, '
    'and plan only the relevant roles (player/enemy/npc/prop/background/tileset/effect/ui). '
    'Return optional sprite_project:{intent:"plan"|"implement",expected_revision:sprite_project.revision,plan:{version:1,entities:[...]}}. '
    'Each entity has id, role, purpose, activation:"startup"|"on_demand", required_clips:[names], asset_ref:known ref or null, generation:full PNG specification or null, '
    'binding:{file:"game.js",replace:"exact old draw snippet, or empty for a new entity"} or null, machine:state definition or null. '
    'Use intent plan with build:null to save a descriptive inventory without generating or changing the game. '
    'Use plan only when the user asks to plan or discuss artwork. A saved inventory is not generated artwork or an implementation proposal. '
    'When the user asks to create, replace or fix artwork, use implement with actual build edits, retaining existing bindings when appropriate. '
    'Choose routine animation frame counts and timing from the request and saved design; do not ask for another confirmation of these implementation choices. '
    'Prepare the actual artwork for human review before asking for its acceptance. Never describe a planned generation as completed or ready for review. '
    'For implement provide actual targeted game edits in build. Missing art with generation is produced by the host, '
    'reused asset_ref entries are loaded from the library, and every new atlas requires exact human acceptance. '
    'Do not combine sprite_project with plan, asset or image_request. Keep unrelated entities in the saved plan. '
    'When sprite-plan.js is already present, assign replacement artwork through its entity plan rather than the single-asset use shortcut. '
    'Host supplies sprite-assets.js, sprite-plan.js and sprite-player.js; omit them from returned files and never invent PNG bytes. '
    'Use const scene=await EmberSprites.createScene(EMBER_SPRITE_PLAN,EMBER_SPRITE_ASSETS); '
    'For implement, every entity including backgrounds and on-demand effects requires a non-null binding '
    'naming an actual proposed source file. Create each declared entity with its literal ID in that file '
    'and use its artwork in the game; do not leave planned entities unconnected or draw their art as placeholders. '
    'const hero=scene.createEntity("hero"); use that literal entity ID in its declared binding.file. '
    'Bind hero.update(dtSeconds,{moving:Math.abs(vx)>0.01,grounded,dead:hp<=0},["attack"]) to real game state and edge-triggered events. '
    'hero.draw(ctx,x,y,{scale:1,facing:direction}) draws the bound directional atlas. Retain the last facing when stopped. '
    'Compare source facing to world velocity or chase target. In a scrolling runner, both runner and pursuing enemy face along the course. '
    'Spawn independent instances with createEntity(id). '
    'hero.state,frame,completed,entityId,assetRef and scene.diagnostics() expose observed animation state and draw counts. '
    'update returns named marker events once per state entry, including entityId and sequence; apply gameplay damage only once for a hit marker. '
    'State machine: {initial,signals:{moving:{type:"boolean",default:false}},states:{idle:{clip:"idle",priority:0,interruptible:true,'
    'terminal:false,on_complete:null,markers:[]}},transitions:[{from:["*"],to:"walk",event:null,when:[{signal:"moving",op:"eq",value:true}]}]}. '
    'Use only declared signals and real clips. Higher target priority can interrupt a locked action; lower priority cannot. '
    'Terminal states ignore transitions until explicit reset for a real respawn. Same-state requests never restart attacks. '
    'on_complete names a state after a nonlooping clip; the machine owns transitions and ignores per-clip next. '
    'Before implementing, read each bound atlas specification for source facing, frame indices, playback speed and loop flags. '
    'Use one looping walk/run clip per sustained movement state, with several distinct stride poses. '
    'Use separate states only for actual gameplay changes such as jumping or stopping. '
    'Avoid unconditional or competing transitions while moving and never reset the locomotion clip every tick. '
    'Check multiple successive rendered poses and the loop seam while holding movement in the browser. Check the runner and pursuer face the course. '
    'A terminal state requires a nonlooping clip. If no suitable clip is available, let the game own the game-over '
    'state and stop updating the sprite there instead of assigning a looping clip to a terminal state. '
    'Markers use clip-local frame indices. Declare jump/fall/landing only when the game has those mechanics; '
    'death should be terminal with highest priority, hurt should interrupt ordinary motion, and attacks should lock appropriately. '
    'Use entity.reset() on respawn/restart to leave terminal states. The entity wrapper does not expose play(); drive '
    'machines through update signals/events. For on-demand animation, create or reset the effect when triggered, '
    'then update(dtSeconds) and draw it on each active frame. '
    'A static entity may use machine:null with required_clips:["default"] for legacy single frames. '
    'Discrete props such as obstacles can share a static tile or tileset atlas with machine:null and required_clips:["default"]. '
    'Draw each prop variant by name with drawTile; keep its collision in the game code. '
    'Terrain tiles use role:tileset, kind:tile or tileset, required_clips:["default"], machine:null. '
    'Declare tileset:{seamless:true,tiles:{grass:{frame:0,solid:false},wall:{frame:1,solid:true}}} in generation, '
    'with loop:false, pivot:[0,0], and no animations; tile cells are static terrain variants. '
    'Side-view platformers require tileset.view:"side-view", not overhead terrain. '
    'Use edge_mode:"blob" for new connected terrain or when replacing visibly tiled ground. The host turns one opaque swatch '
    'into 47 edge-compatible shape variants; use the logical tile name for all connected ground and null for gaps. '
    'Reuse a terrain atlas only when its camera view, adjacency and visual seams match the current level. '
    'If the existing atlas repeats outlined blocks or lacks needed corners, generate a replacement rather than reassigning the same cells. '
    'Render a representative map with a long center run, isolated pieces, both platform ends and a concave corner before approval. '
    'For standalone repeating textures without trim, use tileset.edge_mode:"repeat" with the same flags. '
    'Internal joins must not repeat a complete outline around every cell. Derive rendered terrain and collision from the same layout; '
    'preserve existing platform bounds when replacing artwork and clip any partial cells. '
    'const terrain=scene.createEntity("terrain"); terrain.drawMap(ctx,rows,x,y,{scale:2}) renders tile-name/index rows with null empty cells. '
    'terrain.drawTile(ctx,"grass",x,y) draws one cell; terrain.tiles and terrain.solidAt(rows,column,row) expose authored collision hints. '
    'Replace only the intended entity draw site: binding.replace must match once in the supplied old file and disappear in the proposed file; '
    'existing createEntity bindings can stay intact when only the selected atlas changes. Preserve game physics, scores, hitboxes and unrelated art. '
    'Technical validation covers declarations and source bindings. Expose observable gameplay state and use real browser checks for actual behavior. '
    'Startup entities must be observed drawing their bound art in browser checks. Use on_demand for hit effects, offscreen enemies or later-level entities; '
    'give them targeted gameplay checks that trigger their activation. '
)


def validate_machine(machine, spec=None):
    if machine is None: return
    Draft202012Validator(MACHINE_SCHEMA).validate(machine)
    states, signals = machine['states'], machine['signals']
    if machine['initial'] not in states: raise ValueError('State machine initial state is missing')
    for signal in signals.values():
        if not value_type(signal['default'], signal['type']): raise ValueError('Signal default has the wrong type')
    clips = asset_2d.animations(spec) if spec else None
    for name,state in states.items():
        if state['on_complete'] is not None and state['on_complete'] not in states:
            raise ValueError('Completion transition names a missing state')
        if state['terminal'] and state['on_complete'] is not None: raise ValueError('A terminal state cannot complete into another state')
        if state['on_complete'] == name: raise ValueError('Completion cannot restart the same state')
        markers = [m['event'] for m in state['markers']]
        if len(markers) != len(set(markers)): raise ValueError('Duplicate animation marker')
        if clips is not None:
            if state['clip'] not in clips: raise ValueError('State requires a missing animation clip: '+state['clip'])
            clip=clips[state['clip']]
            if (state['on_complete'] is not None or state['terminal']) and clip['loop']:
                raise ValueError('Completion and terminal states require nonlooping clips')
            if any(m['frame'] >= len(clip['frames']) for m in state['markers']): raise ValueError('Marker is outside its animation clip')
    for transition in machine['transitions']:
        if transition['to'] not in states or any(s!='*' and s not in states for s in transition['from']):
            raise ValueError('Transition names a missing state')
        if not transition['when'] and transition['event'] is None: raise ValueError('A transition requires an event or a condition')
        if any(s!='*' and states[s]['terminal'] and s!=transition['to'] for s in transition['from']):
            raise ValueError('Terminal states cannot have outgoing transitions')
        for condition in transition['when']:
            signal=signals.get(condition['signal'])
            if signal is None or not value_type(condition['value'],signal['type']): raise ValueError('Condition requires a declared signal of the same type')
            if signal['type']=='boolean' and condition['op'] not in ('eq','ne'): raise ValueError('Boolean signals only support equality comparisons')


def value_type(value, kind):
    return type(value) is bool if kind=='boolean' else type(value) in (int,float) and math.isfinite(value) and abs(value)<=1e6


def validate_plan(plan):
    Draft202012Validator(PLAN_SCHEMA).validate(plan)
    if len(canonical(plan)) > 96000: raise ValueError('Sprite plan exceeds its size budget')
    ids=[e['id'] for e in plan['entities']]
    if len(ids)!=len(set(ids)): raise ValueError('Each sprite entity needs a unique ID')
    for entity in plan['entities']:
        if entity['asset_ref'] and entity['generation']: raise ValueError('Choose reuse or generation for each entity')
        validate_machine(entity['machine'])
        if entity['machine'] and not {s['clip'] for s in entity['machine']['states'].values()} <= set(entity['required_clips']):
            raise ValueError('Required clips must include every state animation')
        if entity['generation']: validate_entity_asset(entity, entity['generation'])
    return plan


def validate_entity_asset(entity, spec):
    asset_2d.describe(spec)
    tile_kinds=('tile','tileset')
    kinds={'background':('background',),'tileset':tile_kinds,'prop':('sprite',*tile_kinds),'effect':('vfx','sprite')}
    allowed=kinds.get(entity['role'],('sprite',))
    if spec['kind'] not in allowed: raise ValueError('Artwork kind does not match entity role: '+entity['id'])
    if entity['role'] == 'tileset' and (entity['machine'] is not None or entity['required_clips'] != ['default']):
        raise ValueError('Terrain requires static default cells without an animation state machine')
    if entity['role'] == 'prop' and spec['kind'] in tile_kinds and (entity['machine'] is not None or entity['required_clips'] != ['default']):
        raise ValueError('Tile props require static default cells without an animation state machine')
    missing=set(entity['required_clips'])-set(asset_2d.animations(spec))
    if missing: raise ValueError(entity['id']+' needs missing clips: '+', '.join(sorted(missing)))
    validate_machine(entity['machine'],spec)


def pack_assets(assets):
    if not isinstance(assets,dict) or not 1<=len(assets)<=MAX_ATLASES: raise ValueError('Use one to eight PNG atlases per game')
    for ref,data in assets.items():
        if not re.fullmatch('[0-9a-f]{64}',ref): raise ValueError('Sprite assets require frozen library references')
        asset_2d.unpack(asset_2d.PREFIX+canonical(data).decode()+asset_2d.SUFFIX)
    result=ASSETS_PREFIX+canonical(assets).decode()+SUFFIX
    if len(result.encode())>4*1024*1024: raise ValueError('Sprite atlas collection exceeds 4 MiB')
    return result


def unpack_assets(content):
    if not isinstance(content,str) or not content.startswith(ASSETS_PREFIX) or not content.endswith(SUFFIX):
        raise ValueError('sprite-assets.js must be a canonical PNG collection')
    data=json.loads(content[len(ASSETS_PREFIX):-len(SUFFIX)])
    if pack_assets(data)!=content: raise ValueError('Sprite collection bytes changed')
    return data


def pack_plan(plan):
    validate_plan(plan)
    return PLAN_PREFIX+canonical(plan).decode()+SUFFIX


def unpack_plan(content):
    if not content.startswith(PLAN_PREFIX) or not content.endswith(SUFFIX): raise ValueError('sprite-plan.js must be canonical plan data')
    plan=json.loads(content[len(PLAN_PREFIX):-len(SUFFIX)])
    if pack_plan(plan)!=content: raise ValueError('Sprite plan bytes changed')
    return plan


def validate_files(files, before=None):
    has_assets=ASSETS_FILE in files; has_plan=PLAN_FILE in files
    if not has_assets and not has_plan: return
    if not has_assets or not has_plan or 'sprite-player.js' not in files: raise ValueError('A sprite scene needs its plan, atlas collection and player')
    assets=unpack_assets(files[ASSETS_FILE]); plan=unpack_plan(files[PLAN_FILE])
    bound=set()
    for entity in plan['entities']:
        ref=entity['asset_ref']
        if ref not in assets: raise ValueError('Every implemented entity needs a bound atlas: '+entity['id'])
        bound.add(ref); validate_entity_asset(entity,assets[ref]['spec'])
        if entity['role'] in ('player','enemy','npc') and len(entity['required_clips'])>1 and entity['machine'] is None:
            raise ValueError('Animated characters require an explicit state machine: '+entity['id'])
        if entity['machine'] is None and len(entity['required_clips'])!=1:
            raise ValueError('An entity without a state machine must select exactly one clip: '+entity['id'])
    if bound!=set(assets): raise ValueError('Sprite collection must contain exactly the bound entity assets')
    check_bindings(plan,files,before)


class BindingError(ValueError):
    """A proposed entity plan is not connected to its game source."""


def check_bindings(plan,files,before=None):
    prior=unpack_plan(before[PLAN_FILE]) if before is not None and PLAN_FILE in before else {'entities':[]}
    if before is not None and not {e['id'] for e in prior['entities']} <= {e['id'] for e in plan['entities']}:
        raise ValueError('Keep existing sprite entities when implementing replacements')
    for entity in plan['entities']:
        binding=entity['binding']
        if binding is None:
            raise BindingError('Entity '+entity['id']+' has no draw binding; provide its source file and createEntity call')
        if binding['file'] not in files:
            raise BindingError('Entity '+entity['id']+' draw binding names a missing source file: '+binding['file'])
        source=files[binding['file']]
        pattern=r'\.createEntity\(\s*([\'"])'+re.escape(entity['id'])+r'\1\s*\)'
        if not re.search(pattern,source): raise BindingError('Entity must be created at its declared draw binding: '+entity['id'])
        if before is not None and binding['replace']:
            old=before.get(binding['file'],''); snippet=binding['replace']
            # Only a new/revised binding must remove its reviewed old snippet.
            previous=next((e for e in prior['entities'] if e['id']==entity['id']),None)
            if previous is None or previous['binding']!=binding:
                if old.count(snippet)!=1 or snippet in source: raise BindingError('Replacement must remove exactly the declared old draw snippet: '+entity['id'])


def corrected_bindings(original, corrected):
    """A source-binding correction cannot change artwork choices or inventory."""
    Draft202012Validator(RESPONSE_SCHEMA).validate(corrected)
    def inventory(response):
        result=deepcopy(response)
        for entity in result['plan']['entities']: entity.pop('binding')
        return result
    if inventory(original)!=inventory(corrected):
        raise BindingError('Artwork correction must preserve every entity, asset choice and animation requirement')
    return corrected


def asset_rows(files):
    """Flatten packages for separate acceptance, exports and human review."""
    if ASSETS_FILE not in files: return []
    return [dict(ref=ref,path=ASSETS_FILE,spec=data['spec'],report=data['report'],
        package_sha256=sha256((asset_2d.PREFIX+canonical(data).decode()+asset_2d.SUFFIX).encode()).hexdigest())
        for ref,data in unpack_assets(files[ASSETS_FILE]).items()]


def load_draft(folder):
    path=Path(folder)/'sprite-project.json'
    if not path.exists(): return dict(revision=0,plan=None)
    saved=read_json(path)
    if saved.get('sha256')!=digest({k:v for k,v in saved.items() if k!='sha256'}): raise ValueError('Saved sprite plan changed')
    validate_plan(saved['plan'])
    return saved


def sync_applied(folder,plan,request_ref):
    current=load_draft(folder)
    if current['plan']!=plan:save_draft(folder,plan,current['revision'],'applied:'+request_ref)


def save_draft(folder,plan,expected_revision,turn_id,*,source_sha256=None):
    validate_plan(plan); current=load_draft(folder)
    source_sha256=source_sha256 or digest(plan)
    if current.get('turn_id')==turn_id:
        if current.get('source_sha256',digest(current['plan']))!=source_sha256: raise ValueError('This turn already saved another sprite plan')
        if current['plan']==plan:return current
    elif current['revision']!=expected_revision: raise ValueError('Sprite plan changed; prepare a fresh revision')
    body=dict(revision=expected_revision+1,plan=plan,turn_id=turn_id,source_sha256=source_sha256)
    result={**body,'sha256':digest(body)}; atomic_json(Path(folder)/'sprite-project.json',result)
    return result


def context(root,folder,files):
    draft=load_draft(folder)
    applied=unpack_plan(files[PLAN_FILE]) if PLAN_FILE in files else None
    plan=draft['plan'] or applied
    inventory=[]
    if plan:
        from .asset_library import load
        for e in plan['entities']:
            status='needs_generation' if e['generation'] else 'needs_artwork'
            if e['asset_ref']:
                try: validate_entity_asset(e,load(root,e['asset_ref'])[1]); status='ready'
                except (ValueError,OSError): status='incompatible_or_unavailable'
            inventory.append(dict(id=e['id'],role=e['role'],purpose=e['purpose'],required_clips=e['required_clips'],asset_ref=e['asset_ref'],status=status))
    return dict(revision=draft['revision'],plan=plan,applied_plan=applied,inventory=inventory,max_atlases=MAX_ATLASES,
        note='Saved inventory is descriptive. Generation uses the existing bounded credits; only exact proposals and separate asset actions authorize game changes.')


def requirements(text):
    """Grounded planning hints, not authority to add mechanics or spend credits."""
    walk = r'\bwalk(?:s|ing)?\b'
    run = r'\b(?:runners?|runs|running|auto[ -]?run(?:s|ning)?|sprint(?:s|ing)?)\b|\brun (?:cycle|animation|clip|stride)\b'
    running = bool(re.search(run, text, re.I))
    movement = ['idle']
    if not running or re.search(walk, text, re.I):
        movement.append('walk')
    if running:
        movement.append('run')
    groups=[(rf'\b(?:move|movement|run|courier|platformer)\b|{walk}|{run}',movement,'Movement'),
            (r'\b(jump|jumping|platformer|airborne)\b',['jump','fall'],'Airborne movement'),
            (r'\b(combat|attack|fight|fighting|damage)\b',['attack','hurt','death'],'Combat'),
            (r'\b(projectile|fireball|bullet)\b',['travel','impact'],'Projectiles'),
            (r'\b(pickup|collect|collectible)\b',['idle','collect'],'Collectibles')]
    return [dict(reason=reason,clips=clips) for pattern,clips,reason in groups if re.search(pattern,text,re.I)]


def excludes_generated_artwork(exclusions):
    return any(re.search(r'\b(?:no (?:AI[- ])?generated (?:art(?:work)?|assets|images)|(?:procedural|text)[ -]only)\b', text, re.I)
               or re.fullmatch(r'(?:AI[- ]|image[- ])?generated (?:art(?:work)?|assets|images)', text.strip(), re.I)
               for text in exclusions)


def prepare(root,folder,response,snapshot,build,basis,turn_id,*,budget=None,progress=None,project_binding=None,generate=None):
    """Resolve a complete plan before proposing any game writes; replay generation by stable ID."""
    from . import asset_library,game_audio,muse_image
    Draft202012Validator(RESPONSE_SCHEMA).validate(response)
    plan=deepcopy(validate_plan(response['plan']))
    current=load_draft(folder)
    if current['revision']!=response['expected_revision'] and current.get('turn_id')!=turn_id:
        raise ValueError('Sprite plan changed; prepare a fresh revision')
    # Validate every reuse and generation before spending on any entity.
    for e in plan['entities']:
        binding = e['binding']
        if response['intent'] == 'implement' and binding and binding['file'] not in basis:
            # A new file has no approved draw snippet to replace. The literal
            # createEntity call in the proposed file is still checked below.
            binding['replace'] = ''
        if e['asset_ref']: validate_entity_asset(e,asset_library.select(root,snapshot,e['asset_ref'])[1])
        elif response['intent']=='implement' and not e['generation']: raise ValueError('Choose artwork for '+e['id'])
        if response['intent']=='implement' and e['role'] in ('player','enemy','npc') and len(e['required_clips'])>1 and e['machine'] is None:
            raise ValueError('Animated characters require an explicit state machine: '+e['id'])
        if response['intent']=='implement' and e['machine'] is None and len(e['required_clips'])!=1:
            raise ValueError('An entity without a state machine must select exactly one clip: '+e['id'])
    unique={e['asset_ref'] or digest(e['generation']) for e in plan['entities'] if e['asset_ref'] or e['generation']}
    if len(unique)>MAX_ATLASES: raise ValueError('Use at most eight independent sprite atlases')
    if response['intent']=='plan':
        if build is not None: raise ValueError('Inventory planning must use build null')
        return None,save_draft(folder,plan,response['expected_revision'],turn_id)
    if build is None: raise ValueError('Supply actual game edits when implementing the sprite plan')
    from .project_plan import check_binding
    check_binding(root,folder,project_binding)
    # Preflight draw replacements and required source bindings before dispatching images.
    files={i['path']:i['content'] for i in build['files']}
    check_bindings(plan,files,basis)
    files=game_audio.attach(files,basis)
    from . import chat_build
    names=set(files)|set(basis)&set(chat_build.PROTECTED_FILES)|{ASSETS_FILE,PLAN_FILE,'sprite-player.js'}
    if len(names)>chat_build.MAX_FILES: raise ValueError('Sprite scene exceeds the eight-file game limit')
    preflight={name:files.get(name,basis.get(name,'')) for name in names}
    for name,content in files.items():
        if name.endswith('.html'):
            chat_build.validate_html(content); chat_build.ResourcePreview(preflight).feed(content)
    generated=[];by_request={}
    for e in plan['entities']:
        if e['generation']:
            request=asset_2d.generation_request(e['generation'])
            request_id=sha256((turn_id+':sprite:'+e['id']).encode()).hexdigest()
            result=by_request.get(request['request_sha256'])
            if result is None:
                try:
                    name=e['generation']['display_name']
                    notify=(lambda phase,**metadata:progress(phase,generating_asset=name,**metadata)) if progress else None
                    result=(generate or muse_image.generate)(root,folder,request_id,request,budget=budget,progress=notify)
                except muse_image.ImageUnavailable as error:
                    error.sprite_saved={**save_draft(folder,plan,response['expected_revision'],turn_id,source_sha256=digest(response['plan'])),'generated':generated}
                    raise
                by_request[request['request_sha256']]=result;generated.append(result)
            e['asset_ref']=result['asset_ref'];e['generation']=None
    assets={}
    for e in plan['entities']:
        record,spec,_=asset_library.load(root,e['asset_ref']);validate_entity_asset(e,spec)
        assets[e['asset_ref']]=json.loads(record['package'][len(asset_2d.PREFIX):-len(asset_2d.SUFFIX)])
    for name in ('asset.js','engine.js'):
        if name in basis:
            if name in files and files[name]!=basis[name]: raise ValueError('Keep unrelated prepared assets unchanged')
            files[name]=basis[name]
    for name in (ASSETS_FILE,PLAN_FILE,'sprite-player.js'):
        if name in files and files[name]!=basis.get(name): raise ValueError('The host supplies sprite plan, atlas and player files')
    files[ASSETS_FILE]=pack_assets(assets);files[PLAN_FILE]=pack_plan(plan)
    # Reviewed upgrades supply the current canonical player, including state machines.
    files.pop('sprite-player.js',None)
    files=asset_2d.attach_player(files,{})
    validate_files(files,basis)
    from .chat_build import validate_files as validate_build
    validate_build(files)
    result=deepcopy(build);result['files']=[dict(path=k,content=v) for k,v in files.items()]
    saved=save_draft(folder,plan,response['expected_revision'],turn_id,source_sha256=digest(response['plan']))
    saved={**saved,'generated':generated}
    return result,saved
