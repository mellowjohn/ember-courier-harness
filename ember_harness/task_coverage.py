"""Advisory coverage inventory, not semantic verification or action authority."""
from . import chat_build, gameplay
from .core import digest

LABELS = dict(discoverability='Discover how to start', success='Reach the intended outcome',
              failure='Handle an unsuccessful attempt', reset='Restart from a known state',
              repeated_play='Play again after a restart', keyboard='Keyboard interaction',
              touch='Touch interaction')
SUGGESTIONS = dict(
    discoverability='Use the gameplay editor to check visible instructions and a way to begin.',
    success='Check the intended outcome after the actions that should reach it.',
    failure='Check the feedback after a bounded unsuccessful attempt.',
    reset='Add a restart action and check the initial state afterward.',
    repeated_play='Check another interaction after restart in the same scenario; scenarios start fresh.',
    keyboard='Add a supported key action followed by an observable expectation, if keyboard play applies.',
    touch='Add a mobile touch tap followed by an observable expectation, if touch play applies.')
OBSERVATION_LIMIT = (
    'Coverage labels describe the purpose chosen by the plan author, not verified behavior. '
    'Key and touch actions followed by assertions show configured input paths, not that those '
    'inputs cause the reported state. DOM text and numbers are influenced by game code; '
    'they do not independently verify physics, scoring, accessibility or fun.')


def analyze(task_title, brief, saved_plan):
    """Map one frozen task to explicit scenario intent and configured inputs.

    Scenario names and selectors are never interpreted as evidence of reset,
    success or other behavior. Missing paths are review prompts, not extra work
    assigned to the task and not reasons to waive a failing configured check.
    """
    plan = gameplay.validate(saved_plan['plan'])
    if (saved_plan.get('sha256') != digest(plan) or type(saved_plan.get('revision')) is not int or
            saved_plan['revision'] < 0):
        raise ValueError('Coverage review needs the exact saved gameplay plan')
    if not isinstance(task_title, str) or not task_title.strip():
        raise ValueError('Coverage review needs the selected task expectation')
    paths = []
    for path in (*gameplay.COVERAGE_PATHS, 'keyboard', 'touch'):
        refs = []
        for index, scenario in enumerate(plan['scenarios']):
            if path in gameplay.COVERAGE_PATHS:
                configured = path in scenario.get('coverage', [])
            else:
                actions = ('press', 'hold') if path == 'keyboard' else ('tap',)
                viewport = 'desktop' if path == 'keyboard' else 'mobile'
                # A key/tap placed after every assertion does not check its result.
                configured = scenario['viewport'] == viewport and any(
                    step['action'] in actions and any(later['action'] in gameplay.ASSERTIONS
                        for later in scenario['steps'][step_index + 1:])
                    for step_index, step in enumerate(scenario['steps']))
            if configured:
                refs.append(dict(index=index, name=scenario['name'], viewport=scenario['viewport']))
        paths.append(dict(id=path, label=LABELS[path], status='configured' if refs else 'missing',
                          scenario_refs=refs,
                          basis='declared_intent' if path in gameplay.COVERAGE_PATHS else 'observed_input',
                          relevance='owner_review', suggestion=SUGGESTIONS[path]))
    fields = brief.get('fields', {}) if isinstance(brief, dict) else {}
    return dict(version=1, task_expectation=task_title,
                controls_guidance=fields.get('controls', ''),
                plan_revision=saved_plan['revision'], plan_sha256=saved_plan['sha256'],
                paths=paths, missing=[row['id'] for row in paths if row['status'] == 'missing'],
                expectation_mapping=dict(
                    expectation=task_title, basis='review_required',
                    scenario_refs=[dict(index=i, name=s['name'], viewport=s['viewport'])
                                   for i, s in enumerate(plan['scenarios'])],
                    note='Review whether these configured observations actually exercise the selected task. '
                         'Names, labels and a passing happy path cannot establish that relationship.'),
                observation_limit=OBSERVATION_LIMIT,
                unsupported=['Independent physics and scoring verification',
                             'Complete accessibility coverage', 'Human comfort, feel and fun'],
                editor_limits=dict(scenario_slots=4-len(plan['scenarios']),
                                   action_budget_remaining_ms=gameplay.ACTION_BUDGET_MS-gameplay.action_cost_ms(plan),
                                   steps_per_scenario=chat_build.MAX_GAMEPLAY_STEPS),
                guidance='Review relevance for this task. Edit and save the existing gameplay plan before '
                         'preparing a new run; changes do not alter a frozen run. Every configured '
                         'scenario remains required, including reset, repeated play and mobile checks.')
