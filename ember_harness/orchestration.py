"""Host-owned specialist routing; plans propose delegation, never authority.

The selected approved task determines the route. Source, model replies and
feedback cannot add agents, tools or stages. Execution stays sequential so each
specialist receives the preceding checked candidate without concurrent writes.
"""
import re


SPECIALISTS = {
    'gameplay': ('ember-gameplay-coder', 'Gameplay specialist',
        'Implement game rules, controls, progression and interactions.'),
    'interface': ('ember-interface-coder', 'Interface specialist',
        'Implement readable responsive UI, HUD, menus and accessible feedback.'),
    'effects': ('ember-effects-coder', 'VFX specialist',
        'Implement scripted particles, animation timing and visual effects using existing assets.'),
    'presentation': ('ember-presentation-coder', 'Presentation specialist',
        'Implement the interface and scripted effects together, preserving gameplay rules.'),
    'general': ('ember-task-coder', 'Browser game specialist',
        'Implement the selected browser task and preserve unrelated systems.'),
    'fix': ('ember-fix-coder', 'Bug fix specialist',
        'Repair only the frozen finding and preserve its regression expectations.'),
}
PATTERNS = {
    'gameplay': r'\b(gameplay|mechanics?|movement|controls?|collision|scoring|score|combat|enemy|enemies|pickup|delivery|progression|inventory|quest|quests)\b',
    'interface': r'\b(ui|hud|interface|menus?|buttons?|responsive|accessibility|layout|typography|touchscreen)\b',
    'effects': r'\b(vfx|particles?|effects?|trails?|animation|animations|sparks?|explosions?)\b',
}


def asset_profile(goal):
    """Only explicit native prop production requests select a production adapter."""
    if not re.search(r'\b(create|model|produce|design)\b', goal, re.I):
        return None
    if re.search(r'\b(integrate|import|existing|scene|inventory|ui|hud|menus?|buttons?|scoring|score|logic|code)\b', goal, re.I):
        return None
    profiles = [p for p, pattern in [('chest', r'\bchest\b'), ('gate', r'\b(gate|waygate)\b')]
                if re.search(pattern, goal, re.I)]
    return profiles[0] if len(profiles) == 1 else None


def plan(goal, *, kind=None):
    if kind == 'asset':
        stages = [
            dict(id='concept', role='worker', agent='ember-prop-concept', label='Prop concept specialist',
                 focus='Propose and render original bounded prop directions; wait for the human pick.', phase='directions'),
            dict(id='production', role='worker', agent='ember-prop-producer', label='Blender production specialist',
                 focus='Produce and refine the chosen native prop and prepare its browser package.', phase='refine'),
            dict(id='verify', role='verifier', agent='ember-prop-verifier', label='Asset verifier',
                 focus='Independently check native exports, browser behavior and visual quality.', phase='verify')]
        reason = 'Native prop production needs concepts, a human direction pick, production and independent verification.'
    elif kind == 'artwork':
        stages = [
            dict(id='artwork', role='worker', agent='ember-artwork-producer', label='Artwork specialist',
                 focus='Plan and integrate original character and environment artwork using the host generation tools before gameplay implementation.', phase='artwork'),
            dict(id='implement', role='worker', agent='ember-task-coder', label='Game implementation specialist',
                 focus='Implement the selected gameplay, interface and scripted effects using the prepared artwork.', phase='generate'),
            dict(id='verify', role='verifier', agent='ember-task-verifier', label='Independent task verifier',
                 focus='Check the combined game, actual artwork rendering and frozen gameplay expectations.', phase='verify')]
        reason = 'Generate and bind the needed artwork first, then implement and independently verify the game.'
    else:
        domains = ['fix'] if kind == 'finding' else [k for k, pattern in PATTERNS.items() if re.search(pattern, goal, re.I)]
        if len(domains) == 3:
            domains = ['gameplay', 'presentation']
        domains = domains or ['general']
        stages = []
        for index, domain in enumerate(domains):
            agent, label, focus = SPECIALISTS[domain]
            stages.append(dict(id='implement' if index == 0 else 'specialize', role='worker',
                               agent=agent, label=label, focus=focus,
                               phase='generate' if index == 0 else 'specialize'))
        stages.append(dict(id='verify', role='verifier', agent='ember-task-verifier', label='Independent task verifier',
                           focus='Assess the full task against the exact final candidate and frozen gameplay checks.', phase='verify'))
        reason = ('The selected task spans multiple specialties; pass the checked candidate between two workers.'
                  if len(domains) > 1 else 'One implementation specialist is sufficient; independent verification follows.')
    for index, stage in enumerate(stages):
        stage['depends_on'] = [stages[index - 1]['id']] if index else []
    return dict(version=1, mode='sequential', max_workers=2, reason=reason, stages=stages)


def validate(route, contracts):
    """Bind every planned agent to exactly one reviewed child contract."""
    stages = route['stages']
    workers = [s for s in stages if s['role'] == 'worker']
    if (route['version'] != 1 or route['mode'] != 'sequential' or route['max_workers'] != 2
            or not 1 <= len(workers) <= 2 or len(stages) != len(workers) + 1
            or stages[-1]['role'] != 'verifier' or len(contracts) != len(stages)
            or len({s['id'] for s in stages}) != len(stages)
            or len({s['agent'] for s in stages}) != len(stages)):
        raise ValueError('Invalid specialist route or worker cap')
    assigned = {c['contract']['extensions']['orchestration'].get('stage_id'): c['contract'] for c in contracts}
    for index, stage in enumerate(stages):
        c = assigned.get(stage['id'])
        if (not c or c['agent'] != stage['agent'] or c['extensions']['orchestration']['role'] != stage['role']
                or stage['depends_on'] != ([stages[index - 1]['id']] if index else [])):
            raise ValueError('Specialist route differs from reviewed contracts')


def stage_for(route, phase):
    return next((s for s in route['stages'] if phase == s['phase'] or phase.startswith(s['phase'] + '-')), None)
