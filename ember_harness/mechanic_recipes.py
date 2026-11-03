"""Versioned, bounded recipes for Ember's original reference platformer.

These are source proposals and observations, never permission or acceptance.
"""
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import re

from .core import digest

PROFILE = 'ember-platformer-v1'
CONFIG_FILE = 'mechanic-config.js'
PREFIX = 'const EMBER_MECHANIC_CONFIG = '
RESOURCE = Path(__file__).with_name('mechanics')
LIMIT = ('Only the original reference platformer is supported. Game-reported values and '
         'deterministic simulation checks are observations influenced by game code; real keyboard/touch '
         'checks and human playtesting remain separate. A recipe grants no write permission or acceptance.')

DEFINITIONS = {
    'movement-smoothing': dict(id='movement-smoothing', version=1, title='Smoother movement',
        purpose='Make movement less abrupt by accelerating, braking and stopping gradually.', target=PROFILE,
        settings=dict(
            max_speed=dict(label='Maximum speed', unit='px/s', default=240, min=60, max=480, integer=False),
            acceleration_ms=dict(label='Time to full speed', unit='ms', default=200, min=20, max=600, integer=True),
            stopping_ms=dict(label='Stopping time', unit='ms', default=100, min=10, max=600, integer=True),
            reversal_multiplier=dict(label='Reversal braking', unit='×', default=2, min=1, max=5, integer=False)),
        guidance=['Use a fixed 120 Hz simulation and time-based acceleration.',
                  'Brake toward zero before accelerating in the opposite direction.',
                  'Opposite directions together are neutral; release must never cause reverse drift.',
                  'Preserve the level, jump trajectory and art.'],
        limitations=[LIMIT]),
    'forgiving-jumps': dict(id='forgiving-jumps', version=1, title='More forgiving jumps',
        purpose='Allow a short jump after leaving an edge and remember a jump just before landing.', target=PROFILE,
        settings=dict(
            coyote_ms=dict(label='Grace after an edge', unit='ms', default=100, min=0, max=200, integer=True),
            jump_buffer_ms=dict(label='Remember jump before landing', unit='ms', default=100, min=0, max=200, integer=True)),
        guidance=['Windows include their exact boundary at 120 simulation steps per second.',
                  'Zero disables the corresponding assistance.',
                  'A successful jump consumes both eligibility and buffered input.',
                  'Holding or repeating jump must never create an extra jump; preserve jump height.'],
        limitations=[LIMIT]),
}
BASE = dict(max_speed=240, acceleration_ms=0, stopping_ms=0, reversal_multiplier=1,
            coyote_ms=0, jump_buffer_ms=0)


def catalog():
    from . import mechanic_expansions
    return deepcopy(list(DEFINITIONS.values())) + mechanic_expansions.catalog()


def _settings(definition, values):
    if not isinstance(values, dict) or set(values) - set(definition['settings']):
        raise ValueError('Choose only the displayed mechanic settings')
    result = {}
    for name, field in definition['settings'].items():
        value = values.get(name, field['default'])
        if (type(value) not in (int, float) or not math.isfinite(value) or
                not field['min'] <= value <= field['max'] or field['integer'] and type(value) is not int):
            raise ValueError(field['label'] + ' must be a finite value within its displayed bounds')
        result[name] = value
    return result


def resolve(recipe_id, settings=None, *, version=1):
    if isinstance(recipe_id, str) and recipe_id not in DEFINITIONS:
        from . import mechanic_expansions
        return mechanic_expansions.resolve(recipe_id, settings, version=version)
    if type(version) is not int or version != 1 or not isinstance(recipe_id, str) or recipe_id not in DEFINITIONS:
        raise ValueError('Choose a supported recipe and version')
    definition = deepcopy(DEFINITIONS[recipe_id])
    row = dict(id=recipe_id, version=version, target=PROFILE, definition=definition,
               definition_sha256=digest(definition), settings=_settings(definition, {} if settings is None else settings))
    row['sha256'] = digest(row)
    return row


def validate_snapshot(row):
    if (isinstance(row, dict) and row.get('target') == 'ember-platformer-v2' and
            isinstance(row.get('id'), str) and row['id'] not in DEFINITIONS):
        from . import mechanic_expansions
        return mechanic_expansions.validate_snapshot(row)
    if (not isinstance(row, dict) or set(row) != {'id', 'version', 'target', 'definition',
            'definition_sha256', 'settings', 'sha256'} or row['target'] != PROFILE or
            type(row['version']) is not int or row['version'] != 1 or not isinstance(row['id'], str) or row['id'] not in DEFINITIONS):
        raise ValueError('Unsupported frozen mechanic recipe')
    definition = row['definition']
    # Version one is immutable. New definitions must use a new supported version,
    # while UI draft/catalog copies cannot alter an existing reviewed snapshot.
    if (definition != DEFINITIONS[row['id']] or digest(definition) != row['definition_sha256'] or
            _settings(definition, row['settings']) != row['settings'] or
            digest({k:v for k,v in row.items() if k != 'sha256'}) != row['sha256']):
        raise ValueError('The frozen mechanic settings or definition changed')
    return deepcopy(row)


def configuration(recipes=None):
    if isinstance(recipes, list) and any(isinstance(row, dict) and row.get('target') == 'ember-platformer-v2' for row in recipes):
        from . import mechanic_expansions
        return mechanic_expansions.configuration(recipes)
    if recipes is None:
        recipes = [resolve(name) for name in DEFINITIONS]
    if not isinstance(recipes, list) or len(recipes) > 2:
        raise ValueError('Choose at most two reference-platformer recipes')
    rows = [validate_snapshot(row) for row in recipes]
    if len({row['id'] for row in rows}) != len(rows):
        raise ValueError('Choose each mechanic recipe at most once')
    rows.sort(key=lambda row: row['id'])
    settings = deepcopy(BASE)
    for row in rows:
        settings.update(row['settings'])
    result = dict(profile=PROFILE, version=1, recipes=rows, settings=settings)
    result['sha256'] = digest(result)
    return result


def reference_files(recipes=None):
    if isinstance(recipes, list) and any(isinstance(row, dict) and row.get('target') == 'ember-platformer-v2' for row in recipes):
        from . import mechanic_expansions
        return mechanic_expansions.reference_files(recipes)
    result = {name:(RESOURCE / name).read_text(encoding='utf-8')
              for name in ('index.html', 'style.css', 'app.js', 'mechanic-runtime.js')}
    result[CONFIG_FILE] = PREFIX + json.dumps(configuration(recipes), sort_keys=True, separators=(',', ':')) + ';\n'
    return result


def inspect(files):
    if isinstance(files, dict) and 'advanced-runtime.js' in files:
        from . import mechanic_expansions
        return mechanic_expansions.inspect(files)
    if not isinstance(files, dict):
        raise ValueError('Use the original Ember reference platformer before applying these recipes')
    for name in ('index.html', 'app.js', 'mechanic-runtime.js'):
        if files.get(name) != (RESOURCE / name).read_text(encoding='utf-8'):
            raise ValueError('This game is not the supported Ember reference platformer; source integration needs separate review')
    text = files.get(CONFIG_FILE, '')
    if not text.startswith(PREFIX) or not text.endswith(';\n'):
        raise ValueError('The reference mechanic configuration is missing or changed')
    try:
        saved = json.loads(text[len(PREFIX):-2])
        current = configuration(saved['recipes'])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError('The reference mechanic configuration is damaged') from error
    if saved != current or current['profile'] != PROFILE:
        raise ValueError('The reference mechanic values do not match their frozen recipes')
    return current


def apply(files, recipe):
    if ('advanced-runtime.js' in files or isinstance(recipe, dict) and recipe.get('target') == 'ember-platformer-v2'):
        from . import mechanic_expansions
        return mechanic_expansions.apply(files, recipe)
    saved = inspect(files)
    frozen = validate_snapshot(recipe)
    rows = [row for row in saved['recipes'] if row['id'] != frozen['id']] + [frozen]
    result = dict(files)
    result[CONFIG_FILE] = reference_files(rows)[CONFIG_FILE]
    return result


def request(recipe):
    if isinstance(recipe, dict) and recipe.get('target') == 'ember-platformer-v2':
        from . import mechanic_expansions
        return mechanic_expansions.request(recipe)
    row = validate_snapshot(recipe)
    values = ', '.join(field['label'] + ': ' + str(row['settings'][name]) + ' ' + field['unit']
                       for name, field in row['definition']['settings'].items())
    return row['definition']['purpose'] + ' ' + values + '. ' + ' '.join(row['definition']['guidance'])


def binding(files, build_ref, plan_revision, plan_sha256=None):
    if isinstance(files, dict) and 'advanced-runtime.js' in files:
        from . import mechanic_expansions
        return mechanic_expansions.binding(files, build_ref, plan_revision, plan_sha256)
    if not isinstance(build_ref, str) or not build_ref or type(plan_revision) is not int or plan_revision < 0:
        raise ValueError('Bind mechanic observations to a build and saved plan revision')
    if plan_sha256 is not None and (not isinstance(plan_sha256, str) or not re.fullmatch('[0-9a-f]{64}', plan_sha256)):
        raise ValueError('Bind mechanic observations to the exact saved gameplay plan')
    return dict(profile=PROFILE, scenario_version=1, configuration=inspect(files),
        source_manifest={name:sha256(content.encode()).hexdigest() for name, content in sorted(files.items())},
        build_ref=build_ref, plan_revision=plan_revision, plan_sha256=plan_sha256, basis=LIMIT)


def validate_report(bound, report):
    if isinstance(bound, dict) and bound.get('profile') == 'ember-platformer-v2':
        from . import mechanic_expansions
        return mechanic_expansions.validate_report(bound, report)
    if (not isinstance(report, dict) or report.get('profile') != PROFILE or report.get('scenario_version') != 1 or
            report.get('settings') != bound['configuration']['settings'] or
            report.get('recipe_sha256') != [row['sha256'] for row in bound['configuration']['recipes']] or
            report.get('step_ms') != 1000 / 120 or not isinstance(report.get('checks'), list)):
        raise ValueError('Mechanic observations do not match the frozen recipe')
    ids = [row.get('id') for row in report['checks']]
    expected = ['acceleration', 'friction', 'reversal', 'render-rates', 'coyote', 'buffer', 'single-jump', 'trajectory']
    if ids != expected or any(row.get('status') not in ('passed', 'failed') or not isinstance(row.get('observed'), dict)
                              for row in report['checks']):
        raise ValueError('Mechanic observations are incomplete')
    settings = bound['configuration']['settings']
    dt = 1000 / 120
    cap = settings['max_speed']
    ramp = max(1, math.ceil(settings['acceleration_ms'] / dt - 1e-8))
    stop = max(1, math.ceil(settings['stopping_ms'] / dt - 1e-8))
    first = cap if settings['acceleration_ms'] == 0 else min(cap, cap * dt / settings['acceleration_ms'])
    braking = 1 if settings['stopping_ms'] == 0 else math.ceil(settings['stopping_ms'] / settings['reversal_multiplier'] / dt - 1e-8)
    neutral = 0 if settings['stopping_ms'] == 0 else min(0, -first + cap * dt / settings['stopping_ms'])
    distance = 40 + sum(cap if settings['acceleration_ms'] == 0 else
                        min(cap, cap * i * dt / settings['acceleration_ms']) for i in range(1, 121)) / 120
    ci, bi = (math.floor(settings[key] / dt + 1e-8) for key in ('coyote_ms', 'jump_buffer_ms'))
    expected_rows = [
        dict(first_velocity=first, full_velocity=cap, steps=ramp, configured_ms=settings['acceleration_ms']),
        dict(velocity=0, minimum_velocity=0, steps=stop),
        dict(braked_velocity=0, reversed_velocity=-first, neutral_velocity=neutral, braking_steps=braking),
        dict(fps=[30, 60, 120], positions=[distance] * 3, tolerance_px=2),
        dict(inside_steps=ci, inside_jumps=int(settings['coyote_ms'] > 0), outside_steps=ci + 1,
             outside_jumps=0, zero_age_jumps=int(settings['coyote_ms'] > 0), inclusive=True),
        dict(inside_steps=bi, inside_jumps=int(settings['jump_buffer_ms'] > 0), outside_steps=bi + 1,
             outside_jumps=0, natural_landing_jumps=int(settings['jump_buffer_ms'] + 1e-8 >= 5 * dt), inclusive=True),
        dict(held_jumps=1, repressed_in_air_jumps=1, reset_jumps=0),
        dict(maximum_difference=0, steps=70),
    ]
    def matches(actual, expected, *, tolerance=1e-6):
        if isinstance(expected, dict):
            return isinstance(actual, dict) and set(actual) == set(expected) and all(matches(actual[k], v, tolerance=tolerance) for k,v in expected.items())
        if isinstance(expected, list):
            return isinstance(actual, list) and len(actual) == len(expected) and all(matches(a, e, tolerance=tolerance) for a,e in zip(actual, expected))
        if type(expected) is bool:
            return type(actual) is bool and actual == expected
        return type(actual) in (int, float) and math.isfinite(actual) and abs(actual - expected) <= tolerance
    for row, expected in zip(report['checks'], expected_rows):
        observed = row['observed']
        observed_pass = matches(observed, expected)
        if row['id'] == 'render-rates' and isinstance(observed, dict) and set(observed) == set(expected):
            values = observed['positions']
            observed_pass = (matches(observed['fps'], expected['fps']) and observed['tolerance_px'] == 2 and
                isinstance(values, list) and len(values) == 3 and all(type(v) in (int, float) and math.isfinite(v) and abs(v-distance) <= 2 for v in values) and max(values)-min(values) <= 2)
        if row['status'] == 'passed' and not observed_pass:
            raise ValueError('Positive mechanic result lacks the required ' + row['id'] + ' observations')
    passed = all(row['status'] == 'passed' for row in report['checks'])
    if report.get('outcome') != ('passed' if passed else 'failed'):
        raise ValueError('Mechanic outcome differs from its observations')
    return deepcopy(dict(binding=bound, observations=report, qualified=passed,
                         human_playtest='pending', basis=LIMIT))


def gameplay_plans():
    """Separate bounded plans: simulation observations and real browser input."""
    return [dict(title='Reference mechanic simulation observations', scenarios=[
        dict(name='Fixed-step recipe checks', viewport='desktop', coverage=['success'], steps=[
            dict(action='click', selector='#check-mechanics'),
            dict(action='text', selector='#mechanic-result', value='passed')])]),
        dict(title='Reference keyboard and touch input', scenarios=[
            dict(name='Keyboard jump and reset', viewport='desktop', coverage=['success', 'reset'], steps=[
                dict(action='press', key='Space'), dict(action='number_at_least', selector='#jump-count', value=1),
            dict(action='click', selector='#restart'), dict(action='text', selector='#jump-count', value='0')]),
            dict(name='Touch jump and reset', viewport='mobile', coverage=['success', 'reset'], steps=[
                dict(action='tap', selector='#jump'), dict(action='number_at_least', selector='#jump-count', value=1),
                dict(action='tap', selector='#restart'), dict(action='text', selector='#jump-count', value='0')])])]
