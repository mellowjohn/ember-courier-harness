"""Prepare the live Muse MVP rehearsal for owner review; never approve or dispatch."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ember_harness import chat_build, gameplay, polish_runtime, project_brief, project_plan
from ember_harness.local_ui import App
from ember_harness.muse_chat import CreditLedger, installed_binary
from tools.release_check import source_manifest


FEATURE = (
    'Build one original offline courier game: the player starts at position 0, picks up a parcel '
    'using Space or #interact, moves right using ArrowRight or #right, and delivers at position 3 '
    'using Space or #interact. Each key press or touch moves exactly one position. '
    'Expose numeric #position and #deliveries, #status (Ready, Carrying, or Delivered), '
    '#interact, #right, and #reset. Reset restores position 0, deliveries 0 and Ready. '
    'Show the player, parcel and destination visually, with clear instructions and touch controls.'
)


def gameplay_plan():
    scenarios = []
    for viewport in ('desktop', 'mobile'):
        interact = dict(action='press', key='Space') if viewport == 'desktop' else dict(action='tap', selector='#interact')
        move = dict(action='press', key='ArrowRight') if viewport == 'desktop' else dict(action='tap', selector='#right')
        scenarios.append(dict(name=viewport.title() + ' pickup, delivery and reset', viewport=viewport, steps=[
            deepcopy(interact), dict(action='text', selector='#status', value='Carrying'),
            *[deepcopy(move) for _ in range(3)],
            deepcopy(interact),
            dict(action='text', selector='#deliveries', value='1'),
            dict(action='click' if viewport == 'desktop' else 'tap', selector='#reset'),
            dict(action='text', selector='#position', value='0'),
            dict(action='text', selector='#deliveries', value='0'),
        ]))
    return dict(title='Courier live rehearsal: keyboard and touch', scenarios=scenarios)


def prepare(root=ROOT):
    root = Path(root).resolve()
    binary = installed_binary()
    if not binary:
        raise ValueError('Install and sign in to Muse before preparing the live rehearsal')
    runtime = polish_runtime.discover(root)
    credits = CreditLedger(root).summary()
    if credits['blocked'] or credits['available_usd'] < 10:
        raise ValueError('The shared Muse ledger must cover a worker and verifier pair')
    checks = gameplay_plan()
    gameplay.validate(checks)
    app = App(root)
    parent = root / '.harness/projects'
    parent.mkdir(parents=True, exist_ok=True)
    app.start('Live Muse MVP rehearsal', chat_only=True, project_parent=str(parent))
    folder = app.sessions_dir / app.session['id']
    project_brief.save(folder, dict(goal=FEATURE,
        controls='Space to interact; ArrowRight to move one tile; touch Interact/Right; Reset.',
        visual_direction='Original warm amber courier in a quiet indigo scene. Readable silhouettes and a visible destination.',
        constraints='Offline HTML/CSS/classic JavaScript only. No external assets or network. Keep the exact observable IDs and states.'), 0)
    gameplay.save(folder, checks, 0)
    document = project_plan.starter(folder)
    document['scope'].update(game_concept='Original one-scene courier pickup and delivery game',
        core_loop='Pick up a parcel, move three tiles, deliver it, then reset and replay.',
        features=[FEATURE], asset_budget={'external_assets': 0},
        out_of_scope=['Engine integration', 'Blender or asset production', 'External services and network access',
                      'Multiplayer and save systems', 'Publishing, deployment, submission and Git operations'],
        done_criteria=['Keyboard and touch pickup, delivery and reset checks pass on the exact candidate',
                       'Independent Muse verifier reports task completion and scope preservation',
                       'Johnathan reviews the exact build, plays it and separately accepts the task outcome'])
    review = project_plan.prepare(root, folder, document, None)
    pending = project_plan.status(root, folder)['pending']
    contract = pending['payload']['body']['contracts'][0]['contract']
    output = root / '.harness/live-task-checks' / folder.name
    output.mkdir(parents=True)
    receipt = dict(status='awaiting_scope_approval', created_at=datetime.now(timezone.utc).isoformat(),
        session_id=folder.name, session_name=app.session['name'], session_folder=str(folder),
        request_ref=review['request_ref'], contract_id=contract['id'],
        request_path=str(chat_build.harness(folder).root / 'owner-review' / review['request_ref'] / 'request.json'),
        document=document, gameplay=gameplay.load(folder), credit_snapshot=credits,
        muse_binary_sha256=sha256(Path(binary).read_bytes()).hexdigest(), browser_runtime=runtime,
        implementation_manifest=source_manifest(),
        boundary='Preparation only: no owner decisions, provider dispatch, reservation, game writes or quality acceptance.')
    (output / 'preparation.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    lines = ['# Live Muse MVP rehearsal — scope review', '',
        'Status: awaiting Johnathan’s scope approval. No model call has started.', '',
        'Session: **' + app.session['name'] + '** (`' + folder.name + '`).', '',
        '## Proposed game', '', FEATURE, '',
        'The saved keyboard and touch checks each require pickup, three moves, delivery and reset.', '',
        '## Exact scope contract', '',
        '- Contract: `' + contract['id'] + '` version ' + str(contract['version']),
        '- Request hash: `' + review['request_ref'] + '`',
        '- [Full review packet](<' + Path(receipt['request_path']).as_posix() + '>)',
        '- Project: `' + str(chat_build.project(root, folder)) + '`',
        '- Approval window: ' + json.dumps(contract['limits']['time_window']), '',
        'The existing scope template contains candidate/browser/asset/finding capabilities as a ceiling. '
        'This rehearsal requests one browser task with zero external assets; child task contracts are reviewed separately.', '',
        '## Continue in Ember', '',
        '1. Open this session in History → Plan and review/approve its project scope.',
        '2. Choose Run task with Muse and review/approve the narrower coder/verifier contracts.',
        '3. The normal executor allows up to three attempts, six calls and $30 promotional credits '
        'inside the shared $150 ceiling; each call reserves $5. No cash fallback.',
        '4. Review exact task changes, approve the build, play it, then separately accept the task outcome.', '',
        'Initial shared ledger: ' + json.dumps(credits) + '.', '', receipt['boundary'], '',
        'Retain the real worker/verifier replies, browser reports/captures, final handoff and human feedback. '
        'Automated checks and AI judgment cannot establish human gameplay acceptance.']
    (output / 'REVIEW.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    print(prepare() / 'REVIEW.md')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
