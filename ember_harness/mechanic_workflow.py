"""Recipe preparation uses the normal project scope and exact-build review."""
from copy import deepcopy
from pathlib import Path
import re

from . import chat_build, gameplay, project_plan
from .recovery import exclusive


def status(files):
    from . import mechanic_recipes
    try:
        current = mechanic_recipes.inspect(files)
        return dict(catalog=mechanic_recipes.catalog(), supported=True, current=current,
                    can_prepare_sample=False, reason='Reference platformer ready. Review recipe values before preparing changes.')
    except ValueError as error:
        return dict(catalog=mechanic_recipes.catalog(), supported=False, current=None,
                    can_prepare_sample=not bool(files),
                    reason='Prepare the original reference platformer in this empty session.' if not files else str(error))


def binding(files):
    if 'mechanic-config.js' not in files:
        return None
    from . import mechanic_recipes
    try:
        return mechanic_recipes.inspect(files)
    except ValueError:
        return None


def review(expected, files):
    if expected is None:
        return None
    actual = binding(files)
    compatible = actual is not None and (actual['profile'] == expected['profile'] or
        expected['profile'] == 'ember-platformer-v1' and actual['profile'] == 'ember-platformer-v2')
    blockers = [] if compatible else [
        'The candidate changed the supported mechanic reference code. Restore its canonical runtime and controls before reviewing recipe changes.']
    if compatible and actual['profile'] != expected['profile']:
        from .mechanic_recipes import DEFINITIONS
        previous = {row['id']: row for row in expected['recipes'] if row['id'] in DEFINITIONS}
        retained = {row['id']: row for row in actual['recipes'] if row['id'] in DEFINITIONS}
        if previous != retained or any(actual['settings'].get(key) != value for key, value in expected['settings'].items()):
            blockers.append('The expanded reference upgrade must preserve the exact existing movement and jump recipes and values. Review their tuning separately after the upgrade.')
    return dict(binding=actual, blockers=blockers,
                basis='Exact reference-source and recipe/settings binding; game observations and AI judgment do not establish human feel.')


def capture_binding(files, build_ref, saved):
    if binding(files) is None:
        return None
    from . import mechanic_recipes
    return mechanic_recipes.binding(files, build_ref, saved.get('revision', 0), plan_sha256=saved['sha256'])


def input_paths():
    from . import mechanic_recipes, mechanic_expansions
    return [Path(__file__), Path(mechanic_recipes.__file__), Path(mechanic_expansions.__file__),
            *[mechanic_recipes.RESOURCE / name for name in
              ('index.html', 'style.css', 'app.js', 'mechanic-runtime.js',
               'advanced-index.html', 'advanced-style.css', 'advanced-app.js', 'advanced-runtime.js')]]


def checks(profile='ember-platformer-v1'):
    if profile == 'ember-platformer-v2':
        from . import mechanic_expansions
        plans = mechanic_expansions.gameplay_plans()
        return dict(title='Expanded reference gameplay mechanics',
                    scenarios=[scenario for plan in plans for scenario in plan['scenarios']])
    if profile != 'ember-platformer-v1':
        raise ValueError('Choose a supported mechanic reference profile')
    return dict(title='Reference movement and jumping', scenarios=[
        dict(name='Configured fixed-step mechanic scenarios', viewport='desktop', coverage=['success', 'failure'], steps=[
            dict(action='click', selector='#check-mechanics'),
            dict(action='text', selector='#mechanic-result', value='passed')]),
        dict(name='Keyboard movement, jump and restart', viewport='desktop', coverage=['reset', 'repeated_play'], steps=[
            dict(action='hold', key='ArrowRight', ms=250),
            dict(action='number_at_least', selector='#position', value=41),
            dict(action='press', key='Space'),
            dict(action='number_at_least', selector='#jump-count', value=1),
            dict(action='click', selector='#restart'),
            dict(action='text', selector='#jump-count', value='0')]),
        dict(name='Touch jump and restart', viewport='mobile', coverage=['reset'], steps=[
            dict(action='tap', selector='#jump'),
            dict(action='number_at_least', selector='#jump-count', value=1),
            dict(action='tap', selector='#restart'),
            dict(action='text', selector='#jump-count', value='0')])])


def prepare(root, folder, *, operation_id, expected_manifest, action, recipe_id=None, settings=None, version=1):
    from . import mechanic_recipes
    folder = Path(folder)
    if not isinstance(operation_id, str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,80}', operation_id):
        raise ValueError('Use a new recipe preparation request')
    with exclusive(folder / 'chat.lock'), exclusive(folder / 'build.lock'):
        frozen = project_plan.context(root, folder)
        if not frozen:
            raise ValueError('Approve a project plan before preparing mechanic work')
        project_plan.check_binding(root, folder, frozen['binding'])
        current = chat_build.context(root, folder)
        if current['manifest'] != expected_manifest:
            raise ValueError('The game changed; review the current recipe values again')
        files = {row['path']: row['content'] for row in current['files']}
        if action == 'sample':
            if files:
                raise ValueError('Prepare the reference sample in an empty session')
            if recipe_id is not None or settings is not None:
                raise ValueError('The starting sample uses instant movement and no jump assistance')
            candidate = mechanic_recipes.reference_files([])
            title = 'Original movement and jumping reference'
            summary = 'Review the starting platformer. Movement is instant; coyote time and jump buffering are disabled.'
        elif action == 'recipe':
            snapshot = mechanic_recipes.resolve(recipe_id, settings, version=version)
            candidate = mechanic_recipes.apply(files, snapshot)
            title = 'Mechanic recipe: ' + snapshot['definition']['title']
            summary = snapshot['definition']['purpose'] + ' Resolved values: ' + ', '.join(
                name + '=' + str(value) for name, value in snapshot['settings'].items())
            if mechanic_recipes.inspect(files)['profile'] != mechanic_recipes.inspect(candidate)['profile']:
                summary = ('Upgrade Lantern Trail to the expanded Lantern Vale reference. Review the complete '
                    'source, layout, camera, hazard and sentinel scaffold against your approved project scope. '
                    'Existing movement/jump recipe values are preserved. ' + summary)
        else:
            raise ValueError('Choose a reference sample or a supported mechanic recipe')
        ref = chat_build.propose_build(root, folder, 'mechanic-' + operation_id, title,
            dict(title=title[:160], summary=summary,
                 files=[dict(path=name, content=text) for name, text in candidate.items()]),
            expected_before=current['sha256'], project_scope=frozen['binding'])
        return dict(request_ref=ref, mechanics=deepcopy(mechanic_recipes.inspect(candidate)))


def save_checks(folder, revision, profile='ember-platformer-v1'):
    # Saving a plan is an explicit owner action. It cannot mutate a frozen run.
    return gameplay.save(folder, checks(profile), revision)
