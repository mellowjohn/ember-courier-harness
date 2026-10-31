"""Owner-editable session guidance; never contract or action authority."""
from datetime import datetime, timezone
from pathlib import Path

from .recovery import atomic_json, exclusive, read_json

FIELDS = ('goal', 'controls', 'visual_direction', 'constraints')


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


def save(folder, fields, revision):
    if (not isinstance(fields, dict) or set(fields) != set(FIELDS)
            or any(not isinstance(v, str) or len(v) > 2000 for v in fields.values())):
        raise ValueError('Use the four project brief fields, with at most 2000 characters each')
    if type(revision) is not int or revision < 0:
        raise ValueError('A valid project brief revision is required')
    # Share the chat lock so a running request keeps one stable brief.
    with exclusive(Path(folder) / 'chat.lock'):
        if load(folder)['revision'] != revision:
            raise ValueError('This brief changed in another window. Reopen the session before saving')
        result = dict(revision=revision + 1, updated_at=datetime.now(timezone.utc).isoformat(),
                      fields={key: fields[key].strip() for key in FIELDS})
        atomic_json(Path(folder) / 'project-brief.json', result)
        return result
