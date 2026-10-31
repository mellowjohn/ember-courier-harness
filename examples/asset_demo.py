"""Offline CLI asset workflow with three original PNG fixtures and simulated approvals."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import uuid

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def fixture_images(folder):
    folder.mkdir(parents=True, exist_ok=True)
    candidates = []
    for slug, color, shape in [('ember-drop', '#FF914D', 'drop'), ('ember-star', '#FFF1CE', 'star'),
                                ('ember-crystal', '#FF5C3A', 'crystal')]:
        image = Image.new('RGBA', (128, 128), (36, 27, 47, 255))
        draw = ImageDraw.Draw(image)
        if shape == 'drop':
            draw.ellipse((36, 40, 92, 102), fill=color)
            draw.polygon([(40, 60), (64, 18), (88, 60)], fill=color)
        elif shape == 'star':
            draw.polygon([(64, 16), (76, 48), (110, 64), (76, 80), (64, 112), (48, 80), (18, 64), (48, 48)], fill=color)
        else:
            draw.polygon([(64, 14), (98, 64), (64, 114), (30, 64)], fill=color)
        path = folder / (slug + '.png')
        image.save(path)
        candidates.append(dict(slug=slug, path=path.as_posix(), sha256=sha256(path.read_bytes()).hexdigest(),
                               pitch='Original local ' + shape + ' silhouette fixture', target=[128, 128], require_alpha=True))
    return candidates


def main():
    folder = ROOT / '.harness' / 'demos' / ('assets-' + uuid.uuid4().hex[:10])
    workspace = folder / 'workspace'
    outputs = workspace / 'scope-output'
    candidates = fixture_images(outputs / 'candidates')
    (outputs / 'assets').mkdir()
    store = folder / 'state'
    rows = []

    def save(name, obj):
        path = folder / (name + '.json')
        path.write_text(json.dumps(obj, indent=2), encoding='utf-8')
        return str(path)

    def cli(*args, fail=False):
        result = subprocess.run([sys.executable, '-m', 'ember_harness', '--store', str(store), *map(str, args)],
                                cwd=ROOT, capture_output=True, text=True, timeout=60)
        if fail:
            assert result.returncode != 0, result.stdout
        else:
            assert result.returncode == 0, result.stderr or result.stdout
        return json.loads(result.stderr or result.stdout)

    def record(label, result):
        rows.append((label, result))

    quote = 'SIMULATED owner approval for isolated asset end-to-end test only.'
    scope = cli('scope-propose', 'ct-asset-scope-0001', 'planner', 'Choose an original ember silhouette and ingest it',
                '--workspace', workspace, '--asset-workflow')
    scope['approval_mode'] = 'approve_all'
    cli('save', save('scope', scope))
    reviewed = cli('scope-review', save('scope', scope))
    cli('approve', scope['id'], 1, '--reviewed-hash', reviewed['reviewed_hash'], '--quote', quote)
    manifest_path = outputs / 'manifest.json'
    manifest_path.write_text(json.dumps(dict(topic='Ember Courier player concept', candidates=candidates), indent=2), encoding='utf-8')
    child = cli('asset-draft', '--scope', scope['id'], '--manifest', manifest_path,
                '--id', 'ct-asset-worker-0001', '--agent', 'asset-worker')
    child_path = save('asset-contract', child)
    cli('save', child_path)
    assert 'error' in cli('concept-review', '--contract', child['id'], fail=True)
    record('Draft asset contract cannot review or ingest', 'rejected')
    reviewed = cli('review', child_path)
    cli('approve', child['id'], 1, '--reviewed-hash', reviewed['reviewed_hash'], '--quote', quote, '--parent', scope['id'])
    assert cli('verify-inputs', child['id'])['passed']
    review = cli('concept-review', '--contract', child['id'])
    ref, choice = review['review_ref'], candidates[0]['slug']
    record('Three PNGs decoded; hashes, targets, alpha and inherited art direction recorded', 'awaiting_pick')
    dest = outputs / 'assets' / 'player.png'
    assert 'error' in cli('asset-ingest', ref, '--contract', child['id'], '--dest', dest, fail=True)
    record('Ingest before owner selection', 'rejected')
    pending = cli('concept-select', ref, '--contract', child['id'], '--choice', choice)
    assert pending['decision'] == 'needs_approval'
    record('Selection under approve_all', 'needs owner approval')
    cli('approve-action', save('selection-action', pending['approval_action']), '--quote', quote)
    assert cli('concept-select', ref, '--contract', child['id'], '--choice', choice)['status'] == 'selected'
    record('Exact owner-selected candidate', choice)
    result = cli('asset-ingest', ref, '--contract', child['id'], '--dest', dest)
    assert result['status'] == 'ingested' and result['evidence']['status'] == 'complete'
    assert dest.read_bytes() == Path(candidates[0]['path']).read_bytes()
    record('Create-only copy and machine-checked source/destination evidence', 'ingested')
    assert cli('asset-status', ref, '--contract', child['id'], '--dest', dest)['status'] == 'awaiting_acceptance'
    assert 'error' in cli('asset-ingest', ref, '--contract', child['id'], '--dest', dest, fail=True)
    record('Overwrite an identical existing file', 'rejected')
    outside = folder / 'outside.png'
    assert 'error' in cli('asset-ingest', ref, '--contract', child['id'], '--dest', outside, fail=True)
    assert not outside.exists()
    record('Destination outside scope', 'rejected')
    pending = cli('asset-accept', ref, '--contract', child['id'], '--dest', dest)
    assert pending['decision'] == 'needs_approval'
    record('Asset acceptance under approve_all', 'needs separate owner approval')
    cli('approve-action', save('acceptance-action', pending['approval_action']), '--quote', quote)
    assert cli('asset-accept', ref, '--contract', child['id'], '--dest', dest)['status'] == 'accepted'
    assert cli('asset-status', ref, '--contract', child['id'], '--dest', dest)['status'] == 'accepted'
    record('Owner acceptance of the ingested bytes', 'accepted')
    original = dest.read_bytes()
    dest.write_bytes(b'changed fixture bytes')
    assert cli('asset-status', ref, '--contract', child['id'], '--dest', dest, fail=True)['status'] == 'incomplete'
    record('Changed destination after acceptance', 'incomplete')
    dest.write_bytes(original)
    source = Path(candidates[0]['path'])
    source.write_bytes(b'changed source fixture')
    assert cli('asset-status', ref, '--contract', child['id'], '--dest', dest, fail=True)['status'] == 'incomplete'
    assert 'error' in cli('asset-ingest', ref, '--contract', child['id'], '--dest', outputs / 'assets' / 'stale.png', fail=True)
    record('Changed source after selection', 'incomplete; new ingest rejected')
    source.write_bytes(original)
    assert cli('asset-status', ref, '--contract', child['id'], '--dest', dest)['status'] == 'accepted'
    assert cli('contract-lock')['ok'] and cli('audit-verify')['ok']
    record('Audit and retained decision/selection/copy/acceptance provenance', 'pass')
    cli('revoke', scope['id'], '--reason', 'Finish isolated asset fixture demo')
    assert 'error' in cli('asset-ingest', ref, '--contract', child['id'], '--dest', outputs / 'assets' / 'revoked.png', fail=True)
    assert cli('contract-lock')['ok']
    record('Parent scope revoked', 'further ingest rejected')
    report = folder / 'ASSET_DEMO.md'
    lines = ['# Concept selection and gated asset ingest', '',
        'All approvals are simulated local fixtures. The three original PNG silhouettes are procedural test fixtures, not AI-generated artwork. Technical checks do not establish artistic quality or owner acceptance. No engine import is performed.', '',
        '| Scenario | Result |', '|---|---|'] + [f'| {a} | {b} |' for a, b in rows]
    lines += ['', '## Supplied concepts', '']
    for v in candidates:
        lines += [f"### {v['slug']}", '', v['pitch'], '', f"![{v['slug']}](<{v['path']}>)", '']
    lines += ['## Ingested asset', '', f'![Selected asset](<{dest.as_posix()}>)', '']
    report.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(dict(passed=True, report=str(report), scenarios=rows), indent=2))
    return dict(report=report, folder=folder, scenarios=rows)


if __name__ == '__main__':
    main()
