"""Synthetic criterion judgments for workflow tests; never real quality evidence."""

def review_sheets(output, rows, ratios=()):
    """Synthetic image packing for isolated browser fixtures, not Chromium evidence."""
    from PIL import Image
    from ember_harness.polish_runtime import file_digest
    for row in rows:
        names = [row['screenshot'], row.get('before_screenshot', row['name'] + '-before.png')]
        names += [row[key + '_screenshot'] for key in ('action', 'panel') if row.get(key + '_screenshot')]
        names += [v['screenshot'] for v in ratios if v['group'] == row['name']]
        sheet = Image.new('RGB', (80, 30 * ((len(names) + 1) // 2)), '#222222')
        for index, name in enumerate(names):
            with Image.open(output / name) as image:
                sheet.paste(image.resize((40, 30)), ((index % 2) * 40, (index // 2) * 30))
        filename = row['name'] + '-review.png'
        sheet.save(output / filename)
        row.update(review_screenshot=filename, review_sha256=file_digest(output/filename), review_sources=names)


def aspect_captures(request, output, report):
    """Synthetic protocol evidence for unit tests, never a visual quality claim."""
    from PIL import Image
    from ember_harness.polish_runtime import file_digest
    if request.get('players'):
        for view in report['viewports']:
            view['players'] = [dict(id=player['id'], visible=True) for player in request['players']]
    ratios = []
    for profile in request.get('aspect_ratios', []):
        filename = 'aspect-' + profile['name'] + '.png'
        Image.new('RGB', (40, 30), '#445566').save(output / filename)
        ratios.append(dict(**profile, screenshot=filename, sha256=file_digest(output/filename),
            layout=dict(viewport={k: profile[k] for k in ('width', 'height')},
                document_preserved=True, horizontal_overflow=False, clipped_controls=[])))
    if 'aspect_ratios' in request:
        report['aspect_ratios'] = ratios
    if request.get('review_sheets'):
        review_sheets(output, report['viewports'], ratios)
    return report


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
            if criterion['id'] == 'game-viewport-fit':
                observed = data.get('observations', {})
                observed = observed.get('candidate', observed)
                evidence += [dict(kind='capture', ref=p['screenshot'], detail='SYNTHETIC resize judgment')
                    for p in observed.get('aspect_ratios', [])]
        else:
            name, content = next((k, v) for k, v in data['files'].items() if len(v.strip()) >= 12)
            evidence = [dict(kind='source', ref=name, detail=content[:200])]
        rows.append(dict(id=criterion['id'], status='not_observed' if method == 'human' else 'met',
                         reason='SYNTHETIC assessment only', evidence=evidence))
    return rows
