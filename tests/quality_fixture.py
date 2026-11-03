"""Synthetic criterion judgments for workflow tests; never real quality evidence."""

def review_sheets(output, rows):
    """Synthetic image packing for isolated browser fixtures, not Chromium evidence."""
    from PIL import Image
    from ember_harness.polish_runtime import file_digest
    for row in rows:
        names = [row['screenshot'], row['before_screenshot']]
        names += [row[key + '_screenshot'] for key in ('action', 'panel') if row.get(key + '_screenshot')]
        sheet = Image.new('RGB', (80, 60), '#222222')
        for index, name in enumerate(names):
            with Image.open(output / name) as image:
                sheet.paste(image.resize((40, 30)), ((index % 2) * 40, (index // 2) * 30))
        filename = row['name'] + '-review.png'
        sheet.save(output / filename)
        row.update(review_screenshot=filename, review_sha256=file_digest(output/filename), review_sources=names)


def comparison(data):
    """A fixture opinion paired to actual supplied files/observation references."""
    files, baseline = data['files'], data.get('baseline_files', {})
    name, content = next(((name, content) for name, content in files.items()
        if content != baseline.get(name) and len(content.strip()) >= 12), next(iter(files.items())))
    evidence = [dict(kind='source', ref=name, detail=content[:1000]),
        *[dict(kind='capture', ref=view + '.png', detail='SYNTHETIC candidate judgment') for view in ('desktop', 'mobile')],
        dict(kind='gameplay', ref='0', detail='SYNTHETIC candidate scenario')]
    if data['comparison']['baseline_status'] == 'captured':
        name, content = next((name, content) for name, content in baseline.items() if len(content.strip()) >= 12)
        evidence += [dict(kind='baseline_source', ref=name, detail=content[:1000]),
            *[dict(kind='baseline_capture', ref=view + '.png', detail='SYNTHETIC starting judgment') for view in ('desktop', 'mobile')],
            dict(kind='baseline_gameplay', ref='0', detail='SYNTHETIC starting scenario')]
    return dict(improved=True, improvement='SYNTHETIC task improvement; human playtest remains pending.', losses=[], evidence=evidence)


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
