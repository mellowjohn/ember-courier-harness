"""Deterministic intent-to-scope proposals. Never saves or approves authority."""
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from .core import draft, normal, validate, content_hash

TEXT = {'type': 'string', 'minLength': 1, 'maxLength': 8000, 'pattern': r'\S'}
TEXTS = {'type': 'array', 'minItems': 1, 'maxItems': 30, 'uniqueItems': True, 'items': TEXT}
BRIEF_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'game_concept': TEXT, 'core_loop': TEXT, 'features': TEXTS,
        'out_of_scope': TEXTS, 'done_criteria': TEXTS,
        'asset_budget': {'type': 'object', 'minProperties': 1, 'maxProperties': 20,
                         'propertyNames': TEXT,
                         'additionalProperties': {'type': 'integer', 'minimum': 0, 'maximum': 16}},
    },
}
DEFAULTS = {
    'core_loop': 'Start one local scene, perform the main interaction, reach a success or failure state, and restart.',
    'features': ['One scene', 'One player interaction', 'Visible success and failure states', 'Restart'],
    'out_of_scope': ['Multiplayer', 'Save system', 'Engine changes, bake and import',
                     'Paid services', 'Publishing, deployment and submission'],
    'asset_budget': {'player': 1, 'environment': 1, 'interaction_target': 1},
    'done_criteria': ['One local start-to-finish sample demonstrates the core loop',
                      'Johnathan accepts every asset', 'Regression and acceptance tests pass',
                      'Evidence and audit history verify'],
}


def propose(contract_id, agent, intent, workspace, *, brief=None, asset_workflow=False):
    """Return an unapproved draft with a fixed local capability ceiling.

    Free text is data. The optional brief customizes design, never permissions.
    No workspace directories or contract records are created here.
    """
    Draft202012Validator(TEXT).validate(intent)
    brief = {} if brief is None else deepcopy(brief)
    Draft202012Validator(BRIEF_SCHEMA).validate(brief)
    root = normal(str(workspace))
    if root.rstrip('/') == Path(root).anchor.rstrip('/\\'):
        raise ValueError('workspace must be a project directory, not a drive root')
    if any(c in root for c in '*?[]{}'):
        raise ValueError('workspace cannot contain glob characters')
    scope = {'game_concept': intent, **deepcopy(DEFAULTS), **brief}
    if sum(scope['asset_budget'].values()) > 16:
        raise ValueError('sample asset budget cannot exceed 16 assets')
    proposal = {
        'compiler': 'deterministic-v1', 'workspace': root,
        'assumed_fields': sorted(set(scope) - set(brief) - {'game_concept'}),
        'notice': 'Design fields describe the proposed game; the gate enforces tools, paths and limits. '
                  'No model interpretation or game implementation is claimed. Engine work remains paused.',
    }
    c = draft(contract_id, agent, intent, role='scope',
              extensions={'scope': scope, 'scope_proposal': proposal})
    c['goal'] = 'Propose a small sample game: ' + scope['game_concept']
    pattern = root.rstrip('/') + '/scope-output/**'
    c['allowed_paths'] = {'read': [pattern], 'write': [pattern]}
    c['allowed_actions'] = [
        {'action_id': 'inspect', 'tool': 'fs.read', 'class': 'read',
         'args_constraints': {'path': {'path_within': pattern}}, 'allow_no_evidence': True},
        {'action_id': 'write', 'tool': 'fs.write', 'class': 'write',
         'args_constraints': {'path': {'path_within': pattern},
                              'content': {'pattern': r'^[\s\S]{0,65536}$'}},
         'allow_no_evidence': False},
    ]
    c['required_evidence'] = {'write': [{'kind': 'file_hash', 'params': {}}]}
    if asset_workflow:
        from .assets import capabilities
        c['allowed_actions'].extend(capabilities(pattern))
        c['required_evidence']['asset_copy'] = [{'kind': 'source_dest_hash', 'params': {}}]
    c['art_direction'] = {
        'style': 'Simple original readable shapes', 'palette': ['#241B2F', '#FF914D', '#FFF1CE'],
        'mood': 'Warm light in a quiet dark environment', 'references': [],
        'do': ['Keep silhouettes readable', 'Use original assets'],
        'dont': ['Heat distortion', 'Copyrighted or trademarked material'],
    }
    c['extensions']['scope_proposal']['assumed_art_direction'] = True
    validate(c)
    return c


def review(contract):
    """Human-readable design and authority summary bound to the full draft hash."""
    validate(contract)
    scope = contract.get('extensions', {}).get('scope')
    if contract.get('extensions', {}).get('orchestration', {}).get('role') != 'scope' or scope is None:
        raise ValueError('scope proposal required')
    Draft202012Validator({**BRIEF_SCHEMA, 'required': list(BRIEF_SCHEMA['properties'])}).validate(scope)
    return {
        'id': contract['id'], 'version': contract['version'],
        'reviewed_hash': content_hash(contract), 'status': contract['status'],
        'intent': contract['intent_text'], 'proposed_game': deepcopy(scope),
        'assumptions': deepcopy(contract.get('extensions', {}).get('scope_proposal', {})),
        'art_direction': deepcopy(contract.get('art_direction')),
        'authority': {key: deepcopy(contract[key]) for key in
                      ('agent', 'allowed_actions', 'allowed_paths', 'limits', 'forbidden_actions',
                       'required_evidence', 'requires_approval', 'approval_mode')},
        'approval_note': 'Johnathan must approve this reviewed hash through the trusted host. '
                         'A scope is only a ceiling; each child contract needs separate approval.',
    }
