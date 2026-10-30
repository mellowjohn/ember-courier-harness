"""Read completed project versions from approved content and historical evidence."""
from hashlib import sha256
import io
import json
import re
import zipfile

from . import chat_build
from .core import digest
from .owner_review import validate_history
from .recovery import exclusive, read_json


def history(folder):
    requests = chat_build.list_requests(folder)
    if not requests:
        return []
    titles = {r['ref']: r['payload']['body']['build']['title'] for r in requests}
    done = [e for e in chat_build.harness(folder)._entries() if e['kind'] == 'chat_build_completed']
    return [dict(number=index + 1, request_ref=e['request_ref'], title=titles[e['request_ref']],
                 created_at=e['ts'], file_count=len(e.get('manifest', {'index.html': e['sha256']})),
                 latest=index == len(done) - 1) for index, e in enumerate(done)][-20:]


def snapshot(root, folder, ref):
    if not isinstance(ref, str) or not re.fullmatch('[0-9a-f]{64}', ref):
        raise ValueError('Choose a completed build version')
    chat_build.project(root, folder)
    h = chat_build.harness(folder)
    entries = h._entries()
    validate_history(h, entries)
    requests = {r['ref']: r for r in chat_build.list_requests(folder)}
    contents = {}
    versions = [e for e in entries if e['kind'] == 'chat_build_completed']
    if not any(e['request_ref'] == ref for e in versions):
        raise ValueError('Only completed approved builds can be exported or previewed')
    for index, complete in enumerate(versions):
        request = requests[complete['request_ref']]
        if not request['decision'] or request['decision']['choice'] != 'approve':
            raise ValueError('Version has no owner approval')
        body = request['payload']['body']
        build, child = body['build'], body['contracts'][1]['contract']
        if complete['contract_id'] != child['id']:
            raise ValueError('Version contract differs from the approved build')
        actions = {a['action_id']: a for a in child['allowed_actions']}
        rows = build.get('files', [dict(name='index.html', path=build['path'], action_id='write', after_sha256=build['after_sha256'])])
        for row in rows:
            name = row['name']
            if not re.fullmatch(chat_build.PATH_PATTERN, name):
                raise ValueError('Invalid path in historical build')
            action = actions[row['action_id']]
            content = action['args_constraints']['content']['equals']
            if (action['tool'] != 'fs.write' or action['args_constraints']['path']['equals'] != row['path'] or
                    sha256(content.encode('utf-8')).hexdigest() != row['after_sha256']):
                raise ValueError('Historical reviewed bytes do not match the version')
            evidence = next((e for e in reversed(entries[:complete['seq'] - 1])
                             if e['kind'] == 'evidence' and e.get('contract_id') == child['id'] and
                             e.get('action_id') == row['action_id'] and e.get('status') == 'complete'), None)
            if not evidence:
                raise ValueError('Historical build evidence is missing')
            decision = entries[evidence['decision_seq'] - 1]
            expected_action = dict(agent=child['agent'], contract_id=child['id'], contract_version=child['version'],
                                   tool='fs.write', args=dict(path=row['path'], content=content),
                                   paths=dict(read=[], write=[row['path']]), spend=0)
            if (decision['kind'] != 'decision' or decision.get('decision') != 'allow' or
                    decision.get('action') != expected_action or
                    not request['decision']['seq'] < decision['seq'] < evidence['seq'] < complete['seq']):
                raise ValueError('Historical write lacks its approved gate decision')
            evidence_ref = evidence['evidence_refs'][0]
            proof = read_json(h.root / 'evidence' / (evidence_ref + '.json'))
            if (digest(proof) != evidence_ref or proof['contract_id'] != child['id'] or
                    proof['action_id'] != row['action_id'] or not any(
                        item.get('kind') == 'file_hash' and item.get('label') == 'verified' and
                        item.get('params') == dict(path=row['path'], sha256=row['after_sha256']) for item in proof['items'])):
                raise ValueError('Historical file evidence changed')
            contents[name] = content
        manifest = complete.get('manifest', {'index.html': complete['sha256']})
        actual = {name: sha256(content.encode('utf-8')).hexdigest() for name, content in contents.items()}
        if actual != manifest or build.get('manifest', manifest) != manifest:
            raise ValueError('Historical project manifest does not match reviewed content')
        chat_build.validate_files(contents)
        if complete['request_ref'] == ref:
            return dict(number=index + 1, request_ref=ref, title=build['title'], created_at=complete['ts'],
                        manifest=manifest, files=contents)
    raise ValueError('Build version was not found')


def preview(root, folder, ref):
    with exclusive(folder / 'build.lock'):
        saved = snapshot(root, folder, ref)
        parser = chat_build.ResourcePreview(saved['files'])
        parser.feed(saved['files']['index.html'])
        parser.close()
        return dict(html=''.join(parser.output), number=saved['number'], title=saved['title'], request_ref=ref)


def export(root, folder, ref):
    with exclusive(folder / 'build.lock'):
        saved = snapshot(root, folder, ref)
        metadata = {key: value for key, value in saved.items() if key != 'files'}
        metadata['verification'] = 'Reviewed bytes, owner receipts and historical gate/evidence records verified. Gameplay is not automatically verified.'
        files = {name: content.encode('utf-8') for name, content in saved['files'].items()}
        files['ember-build.json'] = json.dumps(metadata, indent=2, ensure_ascii=False).encode('utf-8')
        files['README.txt'] = b'Extract this ZIP, then open index.html in a browser.\nThis export is a saved approved version. Test gameplay before sharing it.\n'
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            for name, content in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, content)
        return output.getvalue(), 'ember-game-v' + str(saved['number']) + '.zip'
