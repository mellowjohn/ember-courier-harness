"""Synthetic criterion judgments for workflow tests; never real quality evidence."""
def assessments(data):
    rows = []
    for criterion in data['quality']['criteria']:
        method = criterion['method']
        if method == 'human':
            evidence = []
        elif method == 'gameplay':
            evidence = [dict(kind='gameplay', ref=str(criterion['scenario']), detail='SYNTHETIC scenario observation')]
        elif method == 'visual':
            evidence = [dict(kind='capture', ref=name + '.png', detail='SYNTHETIC readable presentation judgment') for name in ('desktop', 'mobile')]
        else:
            name, content = next((k, v) for k, v in data['files'].items() if len(v.strip()) >= 12)
            evidence = [dict(kind='source', ref=name, detail=content[:200])]
        rows.append(dict(id=criterion['id'], status='not_observed' if method == 'human' else 'met',
                         reason='SYNTHETIC assessment only', evidence=evidence))
    return rows
