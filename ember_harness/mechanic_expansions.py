"""Immutable camera, impact, enemy and level recipes for the second reference profile."""
from copy import deepcopy
from hashlib import sha256
import json
import math
import re

from .core import digest
from . import mechanic_recipes as base

PROFILE = 'ember-platformer-v2'
RESOURCE = base.RESOURCE
CONFIG_FILE, PREFIX = base.CONFIG_FILE, base.PREFIX
LIMIT = ('Only Ember\'s original expanded reference platformer is supported. Fixed-step values are '
         'game-influenced observations, paired with browser input/captures; human comfort, impact feel '
         'and quality remain separate. No recipe grants permission, acceptance or network access.')

DEFINITIONS = {
    'camera-follow': dict(id='camera-follow', version=1, title='Smoother camera', target=PROFILE,
        purpose='Keep nearby movement inside a calm camera window and ease longer follows within the level.',
        settings=dict(camera_deadzone_px=dict(label='Camera quiet window', unit='px', default=96, min=0, max=240, integer=True),
                      camera_easing_ms=dict(label='Camera follow time', unit='ms', default=200, min=0, max=600, integer=True),
                      reduced_motion=dict(label='Reduced motion', unit='0 off / 1 on', default=0, min=0, max=1, integer=True)),
        guidance=['The camera moves only beyond the quiet window, remains inside level bounds and resets on restart or teleport.',
                  'Reduced motion removes easing and optional ambient animation; it preserves the quiet window.'], limitations=[LIMIT]),
    'impact-protection': dict(id='impact-protection', version=1, title='Clearer hits and damage protection', target=PROFILE,
        purpose='Give a hit a short pause and prevent continuous overlap from draining health every frame.',
        settings=dict(hit_stop_ms=dict(label='Hit pause', unit='ms', default=60, min=0, max=120, integer=True),
                      invincibility_ms=dict(label='Protection after a hit', unit='ms', default=750, min=0, max=2000, integer=True)),
        guidance=['Player and enemy actors pause; protection and hit-pause timers use unpaused simulation time.',
                  'Menus and restart remain responsive. One continuous contact episode can start at most one hit pause.',
                  'Protection includes all steps before its expiry; another hit is possible exactly at expiry.'], limitations=[LIMIT]),
    'enemy-states': dict(id='enemy-states', version=1, title='Patrol, chase and attack', target=PROFILE,
        purpose='Give one trail sentinel readable states, stable range transitions and a bounded attack cooldown.',
        settings=dict(enemy_detection_px=dict(label='Notice distance', unit='px', default=260, min=120, max=400, integer=True),
                      enemy_attack_px=dict(label='Attack distance', unit='px', default=50, min=24, max=90, integer=True),
                      enemy_hysteresis_px=dict(label='Range return margin', unit='px', default=40, min=10, max=80, integer=True),
                      enemy_cooldown_ms=dict(label='Time between attacks', unit='ms', default=700, min=200, max=2000, integer=True)),
        guidance=['Exactly one state is active. Leaving a range needs the additional return margin.',
                  'Cooldown and patrol/chase movement use actor time, which pauses during hit stop.',
                  'The unobstructed trail has one enemy; pathfinding and crowds are outside this profile.'], limitations=[LIMIT]),
    'seeded-levels': dict(id='seeded-levels', version=1, title='Reproducible trail layouts', target=PROFILE,
        purpose='Build a small reachable trail from an explicit seed and generator version.',
        settings=dict(level_seed=dict(label='Level seed', unit='whole number', default=1729, min=1, max=2147483647, integer=True),
                      level_sections=dict(label='Trail sections', unit='sections', default=10, min=6, max=12, integer=True)),
        guidance=['Generator version one uses a fixed integer PRNG and contiguous platforms with reachable height changes.',
                  'Start and goal sections remain safe; the same seed, version and section count reproduce the full layout.',
                  'This is a bounded trail generator, not an arbitrary world generator.'], limitations=[LIMIT]),
}
BASE = dict(**base.BASE, camera_deadzone_px=0, camera_easing_ms=0, reduced_motion=0,
            hit_stop_ms=0, invincibility_ms=0, enemy_detection_px=0, enemy_attack_px=0,
            enemy_hysteresis_px=0, enemy_cooldown_ms=700, level_seed=0, level_sections=10)
FILES = {'index.html': 'advanced-index.html', 'style.css': 'advanced-style.css',
         'app.js': 'advanced-app.js', 'mechanic-runtime.js': 'mechanic-runtime.js',
         'advanced-runtime.js': 'advanced-runtime.js'}


def catalog():
    return deepcopy(list(DEFINITIONS.values()))


def resolve(recipe_id, settings=None, *, version=1):
    if type(version) is not int or version != 1 or recipe_id not in DEFINITIONS:
        raise ValueError('Choose a supported expanded recipe and version')
    definition = deepcopy(DEFINITIONS[recipe_id])
    row = dict(id=recipe_id, version=version, target=PROFILE, definition=definition,
        definition_sha256=digest(definition), settings=base._settings(definition, {} if settings is None else settings))
    row['sha256'] = digest(row)
    return row


def validate_snapshot(row):
    if isinstance(row, dict) and row.get('id') in base.DEFINITIONS:
        return base.validate_snapshot(row)
    if (not isinstance(row, dict) or set(row) != {'id', 'version', 'target', 'definition', 'definition_sha256', 'settings', 'sha256'}
            or row.get('id') not in DEFINITIONS or type(row.get('version')) is not int or row['version'] != 1 or row.get('target') != PROFILE):
        raise ValueError('Unsupported frozen expanded recipe')
    if (row['definition'] != DEFINITIONS[row['id']] or digest(row['definition']) != row['definition_sha256']
            or base._settings(row['definition'], row['settings']) != row['settings']
            or digest({k: v for k, v in row.items() if k != 'sha256'}) != row['sha256']):
        raise ValueError('The frozen expanded recipe changed')
    return deepcopy(row)


def configuration(recipes=None):
    if recipes is None:
        recipes = [base.resolve(name) for name in base.DEFINITIONS] + [resolve(name) for name in DEFINITIONS]
    if not isinstance(recipes, list) or len(recipes) > 6:
        raise ValueError('Choose at most six reference recipes')
    rows = [validate_snapshot(row) for row in recipes]
    if len({row['id'] for row in rows}) != len(rows):
        raise ValueError('Choose each recipe at most once')
    rows.sort(key=lambda row: row['id'])
    settings = deepcopy(BASE)
    for row in rows:
        settings.update(row['settings'])
    result = dict(profile=PROFILE, version=2, generator_version=1, recipes=rows, settings=settings)
    result['sha256'] = digest(result)
    return result


def reference_files(recipes=None):
    files = {name: (RESOURCE / source).read_text(encoding='utf-8') for name, source in FILES.items()}
    files[CONFIG_FILE] = PREFIX + json.dumps(configuration(recipes), sort_keys=True, separators=(',', ':')) + ';\n'
    return files


def inspect(files):
    if not isinstance(files, dict):
        raise ValueError('Use the supported expanded reference platformer')
    for name, source in FILES.items():
        if name != 'style.css' and files.get(name) != (RESOURCE / source).read_text(encoding='utf-8'):
            raise ValueError('The expanded reference runtime or controls changed; integration requires separate review')
    text = files.get(CONFIG_FILE, '')
    if not text.startswith(PREFIX) or not text.endswith(';\n'):
        raise ValueError('The expanded mechanic configuration is missing')
    try:
        saved = json.loads(text[len(PREFIX):-2]); current = configuration(saved['recipes'])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('The expanded mechanic configuration is damaged') from error
    if saved != current:
        raise ValueError('The expanded settings differ from their frozen recipes')
    return current


def upgrade(files):
    """Produce a normal exact proposal; this helper does not write or approve it."""
    if 'advanced-runtime.js' in files:
        inspect(files)
        return dict(files)
    original = base.inspect(files)
    return reference_files(original['recipes'])


def apply(files, recipe):
    result = upgrade(files)
    saved = inspect(result); frozen = validate_snapshot(recipe)
    rows = [row for row in saved['recipes'] if row['id'] != frozen['id']] + [frozen]
    result[CONFIG_FILE] = reference_files(rows)[CONFIG_FILE]
    return result


def request(recipe):
    row = validate_snapshot(recipe)
    return row['definition']['purpose'] + ' ' + ', '.join(
        field['label'] + ': ' + str(row['settings'][name]) + ' ' + field['unit']
        for name, field in row['definition']['settings'].items())


def binding(files, build_ref, plan_revision, plan_sha256=None):
    if not isinstance(build_ref, str) or not build_ref or type(plan_revision) is not int or plan_revision < 0:
        raise ValueError('Bind expanded observations to a build and plan revision')
    if plan_sha256 is not None and (not isinstance(plan_sha256, str) or re.fullmatch('[0-9a-f]{64}', plan_sha256) is None):
        raise ValueError('Bind expanded observations to the saved plan hash')
    return dict(profile=PROFILE, scenario_version=1, configuration=inspect(files),
        source_manifest={name: sha256(text.encode()).hexdigest() for name, text in sorted(files.items())},
        build_ref=build_ref, plan_revision=plan_revision, plan_sha256=plan_sha256, basis=LIMIT)


def layout(seed, sections):
    value = seed & 0xffffffff
    def random():
        nonlocal value
        value = (1664525 * value + 1013904223) & 0xffffffff
        return value
    tops = [360 if seed == 0 or i < 2 or i >= sections - 2 else 360 - random() % 3 * 16 for i in range(sections)]
    hazards = [sections // 2] if seed == 0 else sorted({2 + random() % (sections - 4) for _ in range(2)})
    signature = json.dumps([seed, 1, sections, tops, hazards], separators=(',', ':'))
    fingerprint = 2166136261
    for character in signature:
        fingerprint = ((fingerprint ^ ord(character)) * 16777619) & 0xffffffff
    return dict(seed=seed, version=1, sections=sections, width=1000, tops=tops, hazards=hazards,
        hash=format(fingerprint, '08x'), reachable=all(abs(a - b) <= 88 for a, b in zip(tops, tops[1:])),
        spawn_safe=all(i >= 2 for i in hazards), goal_safe=all(i < sections - 2 for i in hazards))


def _advanced_expected(settings):
    dt = 1000 / 120
    target = 500 - settings['camera_deadzone_px'] / 2
    alpha = 1 if settings['camera_easing_ms'] == 0 else min(1, dt / settings['camera_easing_ms'])
    first = target if settings['reduced_motion'] else target * alpha
    settled = target if settings['reduced_motion'] else target * (1 - (1 - alpha) ** 120)
    immunity = math.ceil(settings['invincibility_ms'] / dt - 1e-8)
    stop = math.ceil(settings['hit_stop_ms'] / dt - 1e-8)
    enabled = settings['enemy_detection_px'] > 0
    generated = layout(settings['level_seed'], settings['level_sections'])
    return [dict(inside=0, first=first, settled=settled, positions=[settled] * 3,
                 bounds=[0, 600], teleport=0, reduced_motion=target),
        dict(invincible_steps=immunity, hit_stop_steps=stop, after_hit=4, inside=4, at_expiry=3,
             stop_not_extended=True, actors_advanced=max(0, max(1, immunity) - stop), pause_tick_unchanged=True, reset_health=5),
        dict(initial='patrol', noticed='chase' if enabled else 'patrol', near='attack' if enabled else 'patrol',
             attack_boundary='attack' if enabled else 'patrol', attack_exit='chase' if enabled else 'patrol',
             disengaged='patrol', jitter=['chase' if enabled else 'patrol'] * 4,
             attacks=3 if enabled else 0, cooldown_steps=math.ceil(settings['enemy_cooldown_ms'] / dt - 1e-8),
             reset_state='patrol', reset_attacks=0),
        dict(seed=generated['seed'], version=1, sections=generated['sections'], width=1000,
             hash=generated['hash'], platform_tops=generated['tops'], hazard_sections=generated['hazards'],
             reachable=generated['reachable'], spawn_safe=generated['spawn_safe'], goal_safe=generated['goal_safe'],
             repeat_equal=True, distinct_hashes=[layout(seed, settings['level_sections'])['hash'] for seed in (17, 29)],
             distinct_layouts=(layout(17, settings['level_sections'])['tops'], layout(17, settings['level_sections'])['hazards'])
                 != (layout(29, settings['level_sections'])['tops'], layout(29, settings['level_sections'])['hazards']), reset_equal=True)]


def validate_report(bound, report):
    config = bound['configuration']
    if (bound.get('profile') != PROFILE or not isinstance(report, dict) or report.get('profile') != PROFILE
            or report.get('scenario_version') != 1 or report.get('settings') != config['settings']
            or report.get('recipe_sha256') != [row['sha256'] for row in config['recipes']]
            or report.get('step_ms') != 1000 / 120 or not isinstance(report.get('checks'), list)):
        raise ValueError('Expanded observations do not match the frozen settings')
    ids = ['acceleration', 'friction', 'reversal', 'render-rates', 'coyote', 'buffer', 'single-jump', 'trajectory',
           'camera', 'damage', 'enemy', 'level']
    if [row.get('id') for row in report['checks']] != ids:
        raise ValueError('Expanded observations are incomplete')
    old_rows = [row for row in config['recipes'] if row['id'] in base.DEFINITIONS]
    old_config = base.configuration(old_rows)
    old_report = dict(profile=base.PROFILE, scenario_version=1, step_ms=1000 / 120, settings=old_config['settings'],
        recipe_sha256=[row['sha256'] for row in old_config['recipes']], checks=report['checks'][:8],
        outcome='passed' if all(row.get('status') == 'passed' for row in report['checks'][:8]) else 'failed')
    base.validate_report(dict(bound, profile=base.PROFILE, configuration=old_config), old_report)
    def matches(actual, expected):
        if isinstance(expected, dict):
            return isinstance(actual, dict) and set(actual) == set(expected) and all(matches(actual[k], v) for k, v in expected.items())
        if isinstance(expected, list):
            return isinstance(actual, list) and len(actual) == len(expected) and all(matches(a, e) for a, e in zip(actual, expected))
        if type(expected) in (bool, str):
            return type(actual) is type(expected) and actual == expected
        return type(actual) in (int, float) and math.isfinite(actual) and abs(actual - expected) <= 1e-6
    for row, expected in zip(report['checks'][8:], _advanced_expected(config['settings'])):
        if row.get('status') not in ('passed', 'failed') or not isinstance(row.get('observed'), dict):
            raise ValueError('Expanded observations are incomplete')
        if row['status'] == 'passed' and not matches(row['observed'], expected):
            raise ValueError('Positive expanded result lacks the required ' + row['id'] + ' observations')
    passed = all(row.get('status') == 'passed' for row in report['checks'])
    if report.get('outcome') != ('passed' if passed else 'failed'):
        raise ValueError('Expanded outcome differs from its observations')
    return deepcopy(dict(binding=bound, observations=report, qualified=passed, human_playtest='pending', basis=LIMIT))


def gameplay_plans():
    return [dict(title='Expanded fixed-step mechanics', scenarios=[dict(name='Configured reference scenarios', viewport='desktop',
        coverage=['success', 'failure'], steps=[dict(action='click', selector='#check-mechanics'),
        dict(action='text', selector='#mechanic-result', value='passed')])]),
        dict(title='Expanded keyboard and touch', scenarios=[dict(name='Keyboard jump and restart', viewport='desktop',
            coverage=['reset', 'repeated_play'], steps=[dict(action='press', key='Space'),
                dict(action='number_at_least', selector='#jump-count', value=1), dict(action='click', selector='#restart'),
                dict(action='text', selector='#jump-count', value='0')]),
            dict(name='Touch jump and restart', viewport='mobile', coverage=['reset'], steps=[dict(action='tap', selector='#jump'),
                dict(action='number_at_least', selector='#jump-count', value=1), dict(action='tap', selector='#restart'),
                dict(action='text', selector='#jump-count', value='0')])])]
