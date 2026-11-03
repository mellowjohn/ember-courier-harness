"""Persistent guidance gathered in conversation; never action authority."""
from datetime import datetime, timezone
from pathlib import Path

from .recovery import atomic_json, exclusive, read_json

FIELDS = ('goal', 'controls', 'visual_direction', 'constraints')
QUESTIONS = dict(
    goal='What should the player do, and what makes it fun?',
    controls='How should the player control the game: keyboard, mouse, touch, or a mix?',
    visual_direction='What should the game look and feel like?',
    constraints='What must we keep, and is there anything you want to avoid?')
UPDATE_SCHEMA = {'type': 'object', 'additionalProperties': False, 'minProperties': 1,
                 'properties': {key: {'type': 'string', 'maxLength': 2000} for key in FIELDS}}


def intake(brief):
    missing = [key for key in FIELDS if not brief['fields'][key]]
    return dict(missing=missing, questions={key: QUESTIONS[key] for key in missing})


def update_from_chat(folder, updates, revision, turn_id):
    """Save a validated partial answer while the caller holds chat.lock.

    The turn marker makes recovery after saving but before replying idempotent.
    A retry may never overwrite a newer answer from another turn or window.
    """
    from jsonschema import Draft202012Validator
    Draft202012Validator(UPDATE_SCHEMA).validate(updates)
    saved = load(folder)
    updates = {key: value.strip() for key, value in updates.items()}
    if saved.get('source_turn_id') == turn_id:
        if any(saved['fields'][key] != value for key, value in updates.items()):
            raise ValueError('This message already saved different project details')
        return saved
    if saved['revision'] != revision:
        raise ValueError('Project details changed since this message; send a fresh message')
    fields = {**saved['fields'], **updates}
    if fields == saved['fields']:
        return saved
    result = dict(revision=revision + 1, updated_at=datetime.now(timezone.utc).isoformat(),
                  fields=fields, source_turn_id=turn_id)
    if saved.get('purpose') and fields['goal']==saved['fields']['goal']:
        result['purpose']=saved['purpose']
    atomic_json(Path(folder) / 'project-brief.json', result)
    return result


def load(folder):
    path = Path(folder) / 'project-brief.json'
    if not path.exists():
        return dict(revision=0, updated_at=None, fields=dict.fromkeys(FIELDS, ''))
    data = read_json(path)
    if (type(data.get('revision')) is not int or data['revision'] < 1
            or not isinstance(data.get('fields'), dict) or set(data['fields']) != set(FIELDS)
            or any(not isinstance(v, str) or len(v) > 2000 for v in data['fields'].values())):
        raise ValueError('The saved project brief is damaged')
    return data


def save(folder, fields, revision, *, purpose=None):
    if (not isinstance(fields, dict) or set(fields) != set(FIELDS)
            or any(not isinstance(v, str) or len(v) > 2000 for v in fields.values())):
        raise ValueError('Use the four project brief fields, with at most 2000 characters each')
    if type(revision) is not int or revision < 0:
        raise ValueError('A valid project brief revision is required')
    # Share the chat lock so a running request keeps one stable brief.
    with exclusive(Path(folder) / 'chat.lock'):
        current=load(folder)
        if current['revision'] != revision:
            raise ValueError('This brief changed in another window. Reopen the session before saving')
        result = dict(revision=revision + 1, updated_at=datetime.now(timezone.utc).isoformat(),
                      fields={key: fields[key].strip() for key in FIELDS})
        retained=purpose or (current.get('purpose') if result['fields']['goal']==current['fields']['goal'] else None)
        if retained: result['purpose']=retained
        atomic_json(Path(folder) / 'project-brief.json', result)
        return result
