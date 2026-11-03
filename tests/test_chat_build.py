"""Custom builds use synthetic owner decisions in isolated test projects."""
import json
from pathlib import Path
import tempfile
import unittest
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch

from ember_harness.local_ui import App, server
from ember_harness import chat_build, playtests

ROOT = Path(__file__).resolve().parents[1]
HTML = '<!doctype html><html><head><title>Timer</title></head><body><button>Start</button></body></html>'
PROJECT = {
    'index.html': '<!doctype html><html><head><link rel="stylesheet" href="style.css"></head><body><button id="counter">0</button><script src="app.js"></script></body></html>',
    'style.css': 'body { background: rgb(20, 30, 40); }',
    'app.js': 'document.querySelector("button").onclick = e => e.target.textContent = Number(e.target.textContent) + 1;',
}


class ChatBuildTests(unittest.TestCase):
    def setUp(self):
        self.quality_patch=patch('ember_harness.proposal_quality.run',return_value=dict(status='unavailable',issues=['SYNTHETIC: verification tested separately']))
        self.quality_patch.start();self.addCleanup(self.quality_patch.stop)
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'examples').mkdir()
        (self.root / 'examples/product_demo.py').touch()
        self.app = App(self.root)
        self.app.start('Timer build', chat_only=True)
        self.sid = self.app.session['id']
        self.folder = self.app.sessions_dir / self.sid
        self.target = chat_build.project(self.root, self.folder) / 'index.html'

    def propose(self, turn='a' * 24, html=HTML, path='index.html'):
        response = dict(message='Review this timer implementation before I write it.',
                        build=dict(title='Timer', summary='One local timer page', files=[dict(path=path, content=html)]))
        with patch('ember_harness.session_chat.run_muse', return_value=dict(response=json.dumps(response))) as muse:
            self.app.chat('Build me a timer', turn)
            self.assertIn('output_schema', muse.call_args.kwargs)
        return self.app.snapshot()['build']['requests'][-1]['ref']

    def propose_project(self, files=None, turn='a' * 24):
        response = dict(message='Review this browser project.', build=dict(title='Counter', summary='Three local files',
                        files=[dict(path=name, content=value) for name, value in (files or PROJECT).items()]))
        with patch('ember_harness.session_chat.run_muse', return_value=dict(response=json.dumps(response))):
            self.app.chat('Build or revise a counter', turn)
        return self.app.snapshot()['build']['requests'][-1]['ref']

    def test_multifile_approval_revision_context_preview_and_tamper(self):
        ref = self.propose_project()
        self.assertFalse(self.target.exists())
        packet = self.app.snapshot()['build']['requests'][0]['payload']['body']['build']
        for name in PROJECT:
            self.assertIn('proposed/' + name, packet['diff'])
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: approve all three files')
        for name, value in PROJECT.items():
            self.assertEqual((self.target.parent / name).read_text(encoding='utf-8'), value)
        self.assertEqual(len(self.app.verify()['manifest']), 3)
        preview = self.app.build_preview()['html']
        self.assertIn('data:text/javascript;base64,', preview)
        self.assertIn('data:text/css;base64,', preview)
        self.assertEqual(len(chat_build.context(self.root, self.folder)['files']), 3)
        revised = {**PROJECT, 'style.css': 'body { background: red; }'}
        second = self.propose_project(revised, 'b' * 24)
        self.assertEqual(len(self.app.snapshot()['build']['requests'][-1]['payload']['body']['build']['files']), 1)
        self.app.respond(second, 'approve', 'SYNTHETIC TEST: approve CSS revision')
        fresh = App(self.root)
        fresh.resume(self.sid)
        self.assertTrue(fresh.verify()['passed'])
        (self.target.parent / 'app.js').write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed'):
            fresh.build_preview()

    def test_bulk_edits_across_files_share_one_review_and_preserve_unrelated_source(self):
        files={**PROJECT,'style.css':PROJECT['style.css']+'\n'+''.join(f'/* old-{i} */\n' for i in range(32)),
               'app.js':PROJECT['app.js']+'\n'+''.join(f'// old-{i}\n' for i in range(32))}
        original=self.propose_project(files)
        self.app.respond(original,'approve','SYNTHETIC TEST: initial bulk fixture')
        edits=[dict(path=name,before=f'old-{i}'+(' */' if name.endswith('.css') else '\n'),
                    after=f'new-{i}'+(' */' if name.endswith('.css') else '\n'))
               for name in ('style.css','app.js') for i in range(32)]
        reply=dict(message='Review all 64 edits.',build=dict(title='Bulk update',summary='Update both files.',edits=edits))
        with patch('ember_harness.session_chat.run_muse',return_value=dict(response=json.dumps(reply))):
            self.app.chat('Update all 64 markers across both files','synthetic-bulk-edits-12345678')
        pending=chat_build.list_requests(self.folder)[-1]
        self.assertFalse(pending['decision'])
        self.assertEqual(len(chat_build.list_requests(self.folder)),2)
        self.assertEqual({name:(self.target.parent/name).read_text() for name in files},files)
        self.assertEqual(len(pending['payload']['body']['build']['files']),2)
        self.app.respond(pending['ref'],'approve','SYNTHETIC TEST: approve one bulk diff')
        for name in ('style.css','app.js'):
            self.assertEqual((self.target.parent/name).read_text(),files[name].replace('old-','new-'))
        self.assertEqual(self.target.read_text(),files['index.html'])

    def test_targeted_revision_preserves_untouched_bytes_through_review_and_saved_versions(self):
        from ember_harness import project_versions
        files = {**PROJECT, 'style.css': '/* Café\r\n original */\r\n' + PROJECT['style.css']}
        ref = self.propose_project(files)
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: original game')
        before = {name: (self.target.parent / name).read_bytes() for name in files}
        reply = dict(message='Change only the counter increment.', build=dict(title='Increment by two', summary='Keep the current game.',
            edits=[dict(path='app.js', before=' + 1;', after=' + 2;')]))
        with patch('ember_harness.session_chat.run_muse', return_value=dict(response=json.dumps(reply))):
            self.app.chat('Increment by two; keep everything else.', 'targeted-revision-01')
        request = chat_build.list_requests(self.folder)[-1]
        self.assertEqual([row['name'] for row in request['payload']['body']['build']['files']], ['app.js'])
        self.assertEqual({name: (self.target.parent / name).read_bytes() for name in files}, before)
        self.assertEqual(set(self.app.proposal_preview(self.sid, request['ref'])['manifest']), set(files))
        self.app.respond(request['ref'], 'approve', 'SYNTHETIC TEST: exact targeted revision')
        snapshot = project_versions.snapshot(self.root, self.folder, request['ref'])
        for name in ('index.html', 'style.css'):
            self.assertEqual((self.target.parent / name).read_bytes(), before[name])
            self.assertEqual(snapshot['files'][name].encode('utf-8'), before[name])
        self.assertIn(' + 2;', snapshot['files']['app.js'])

    def test_swapped_page_and_script_are_repaired_in_the_reviewed_candidate(self):
        first=self.propose_project()
        self.app.respond(first,'approve','SYNTHETIC original project')
        page='<!doctype html><html><body><button id="counter">0</button><script src="game.js"></script></body></html>'
        script=PROJECT['app.js']
        ref=self.propose_project({'index.html':script,'game.js':page},'swapped-page-script-12345678')
        candidate=chat_build.proposal_snapshot(self.root,self.folder,ref)['files']
        self.assertEqual(candidate['index.html'],page)
        self.assertEqual(candidate['game.js'],script)
        self.assertEqual(candidate['app.js'],PROJECT['app.js'])
        self.assertEqual(self.target.read_text(encoding='utf-8'),PROJECT['index.html'])
        self.assertIsNone(chat_build.list_requests(self.folder)[-1]['decision'])

    def test_malformed_or_ambiguous_page_sources_are_not_guessed(self):
        def page(name):return '<html><body><script src="'+name+'"></script></body></html>'
        for files in ({'index.html':'const x=1;','game.js':page('game.js'),'other.js':page('other.js')},
                      {'index.html':'<div>Incomplete page</div>','game.js':page('game.js')},
                      {'index.html':'const x=1;','game.js':'const y=2;'}):
            result=chat_build.materialize_build(dict(title='Invalid page',summary='Do not invent a document',
                files=[dict(path=k,content=v) for k,v in files.items()]),{})
            with self.assertRaisesRegex(ValueError,'complete HTML document'):
                chat_build.validate_files({row['path']:row['content'] for row in result['files']})

    def test_full_file_reply_retains_omitted_files_and_reviews_only_actual_changes(self):
        first = self.propose_project()
        self.app.respond(first, 'approve', 'SYNTHETIC initial project')
        changed = PROJECT['app.js'].replace('+ 1', '+ 2')
        second = self.propose_project({'app.js': changed}, 'full-file-partial-revision')
        packet = chat_build.list_requests(self.folder)[-1]['payload']['body']['build']
        self.assertEqual([row['name'] for row in packet['files']], ['app.js'])
        candidate = chat_build.proposal_snapshot(self.root, self.folder, second)['files']
        self.assertEqual(candidate, {**PROJECT, 'app.js': changed})
        self.assertEqual((self.target.parent / 'app.js').read_text(encoding='utf-8'), PROJECT['app.js'])
        self.app.respond(second, 'approve', 'SYNTHETIC exact partial revision')
        self.assertEqual(chat_build.context(self.root, self.folder)['manifest'], packet['manifest'])

    def test_full_file_reply_can_add_a_new_entry_script_without_dropping_old_source(self):
        first = self.propose_project()
        self.app.respond(first, 'approve', 'SYNTHETIC initial project')
        supplied = {'index.html': PROJECT['index.html'].replace('app.js', 'game.js'), 'game.js': PROJECT['app.js']}
        ref = self.propose_project(supplied, 'full-file-new-entry-script')
        candidate = chat_build.proposal_snapshot(self.root, self.folder, ref)['files']
        self.assertEqual(candidate, {**PROJECT, **supplied})
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            chat_build.materialize_build(dict(title='Invalid', summary='Duplicate paths', files=[
                dict(path='app.js', content='one'), dict(path='app.js', content='two')]), PROJECT)

    def test_targeted_edits_reject_ambiguous_missing_overlapping_and_protected_changes(self):
        base = {**PROJECT, 'app.js': 'aaaa; first(); second();', 'engine.js': 'prepared runtime'}
        invalid = [
            [dict(path='app.js', before='aa', after='b')],
            [dict(path='app.js', before='missing', after='b')],
            [dict(path='missing.js', before='first()', after='b')],
            [dict(path='app.js', before='first()', after='x'), dict(path='app.js', before='first(); second()', after='y')],
            [dict(path='../app.js', before='first()', after='x')],
            [dict(path='engine.js', before='prepared runtime', after='replacement')],
            [dict(path='app.js', before='', after='replacement')],
        ]
        for edits in invalid:
            with self.subTest(edits=edits), self.assertRaises(Exception):
                chat_build.materialize_build(dict(title='Rejected', summary='Invalid edit', edits=edits), base)
        build = dict(title='Two edits and new system', summary='Preserve intervening source.', edits=[
            dict(path='app.js', before='first()', after='firstImproved()'),
            dict(path='app.js', before='second()', after='secondImproved()')],
            files=[dict(path='system.js', content='const newSystem = true;')])
        result = {row['path']: row['content'] for row in chat_build.materialize_build(build, base)['files']}
        self.assertEqual(result['app.js'], 'aaaa; firstImproved(); secondImproved();')
        self.assertEqual(result['engine.js'], base['engine.js'])
        self.assertEqual(result['system.js'], 'const newSystem = true;')
        build['files'] = [dict(path='app.js', content='replacement')]
        with self.assertRaisesRegex(ValueError, 'unique new'):
            chat_build.materialize_build(build, base)

    def test_targeted_revision_cannot_rebase_cached_response_after_project_changes(self):
        ref = self.propose_project()
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: original game')
        with patch('ember_harness.session_chat.run_muse', side_effect=ValueError('SYNTHETIC interrupted provider')):
            with self.assertRaisesRegex(ValueError, 'interrupted provider'):
                self.app.chat('Improve the counter', 'targeted-retry-01')
        (self.target.parent / 'style.css').write_bytes(b'body { color: red; }')
        with patch('ember_harness.session_chat.run_muse') as model:
            with self.assertRaisesRegex(ValueError, 'changed since this request'):
                self.app.chat('Improve the counter', 'targeted-retry-01')
            model.assert_not_called()
        self.assertEqual(len(chat_build.list_requests(self.folder)), 1)

    def test_proposal_preview_does_not_approve_write_or_call_muse(self):
        ref = self.propose_project()
        h = chat_build.harness(self.folder)
        before = h._entries()
        with patch('ember_harness.session_chat.run_muse') as muse:
            for _ in range(2):
                preview = self.app.proposal_preview(self.sid, ref)
                self.assertEqual(preview['request_ref'], ref)
                self.assertEqual(set(preview['manifest']), set(PROJECT))
                self.assertIn('data:text/javascript;base64,', preview['html'])
                self.assertIn('data:text/css;base64,', preview['html'])
            muse.assert_not_called()
        self.assertFalse(self.target.exists())
        self.assertEqual(h._entries(), before)
        self.assertEqual(self.app.snapshot()['build']['completed'], [])
        with self.assertRaisesRegex(ValueError, 'approval'):
            self.app.resume_build(ref)

    def test_proposal_preview_carries_unchanged_files_and_survives_restart(self):
        original = self.propose_project()
        self.app.respond(original, 'approve', 'SYNTHETIC TEST: original project')
        updated = {**PROJECT, 'style.css': 'body { background: red; }'}
        ref = self.propose_project(updated, 'b' * 24)
        fresh = App(self.root)
        fresh.resume(self.sid)
        before = chat_build.harness(self.folder)._entries()
        preview = fresh.proposal_preview(self.sid, ref)
        self.assertEqual(preview['manifest'], {name: chat_build.sha256(value.encode()).hexdigest() for name, value in updated.items()})
        for name, value in PROJECT.items():
            self.assertEqual((self.target.parent / name).read_text(encoding='utf-8'), value)
        self.assertEqual(chat_build.harness(self.folder)._entries(), before)
        self.assertEqual(len(fresh.snapshot()['build']['completed']), 1)

    def test_proposal_preview_rejects_changed_inputs_and_decided_proposals(self):
        ref = self.propose()
        self.app.respond(ref, 'decline', 'SYNTHETIC TEST: discard preview')
        with self.assertRaisesRegex(ValueError, 'pending proposal'):
            self.app.proposal_preview(self.sid, ref)
        ref = self.propose('b' * 24)
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: approve fixture')
        with self.assertRaisesRegex(ValueError, 'pending proposal'):
            self.app.proposal_preview(self.sid, ref)
        ref = self.propose('c' * 24, HTML.replace('Start', 'New start'))
        self.target.write_text('Externally changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed|HTML'):
            self.app.proposal_preview(self.sid, ref)
        self.assertIsNone(self.app.snapshot()['build']['requests'][-1]['decision'])

    def test_proposal_preview_rejects_modified_review_packet(self):
        ref = self.propose()
        request = chat_build.harness(self.folder).root / 'owner-review' / ref / 'request.json'
        payload = json.loads(request.read_bytes())
        payload['body']['build']['title'] = 'Tampered proposal'
        request.write_text(json.dumps(payload), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'hash|mismatch'):
            self.app.proposal_preview(self.sid, ref)
        self.assertFalse(self.target.exists())

    def test_proposal_preview_http_requires_authentication_and_intended_session(self):
        ref = self.propose()
        http = server(self.app)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join)
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        url = f'http://127.0.0.1:{http.server_port}/api/proposal-preview?session_id={self.sid}&ref={ref}'
        with self.assertRaises(HTTPError) as denied:
            urlopen(url, timeout=10)
        self.assertEqual(denied.exception.code, 403)
        headers = {'X-Ember-Token': self.app.token}
        with urlopen(Request(url, headers=headers), timeout=10) as response:
            self.assertIn('<button>Start</button>', json.load(response)['html'])
        self.app.start('Different session', chat_only=True)
        with self.assertRaises(HTTPError) as stale:
            urlopen(Request(url, headers=headers), timeout=10)
        self.assertEqual(stale.exception.code, 400)
        with self.assertRaisesRegex(ValueError, 'intended session'):
            self.app.proposal_preview(self.sid, ref)
        self.assertFalse(self.target.exists())

    def test_multifile_partial_write_resumes_without_repeating_actions(self):
        ref = self.propose_project()
        replace = chat_build.os.replace
        def interrupt(source, destination):
            replace(source, destination)
            if Path(destination) == self.target:
                raise OSError('SYNTHETIC interruption after second project write')
        with patch('ember_harness.chat_build.os.replace', side_effect=interrupt):
            with self.assertRaises(OSError):
                self.app.respond(ref, 'approve', 'SYNTHETIC TEST: approve interrupted project')
        self.assertTrue((self.target.parent / 'app.js').exists())
        self.assertFalse((self.target.parent / 'style.css').exists())
        with self.assertRaisesRegex(ValueError, 'Resume'):
            self.app.build_preview()
        fresh = App(self.root)
        fresh.resume(self.sid)
        fresh.resume_build(ref)
        fresh.resume_build(ref)
        self.assertTrue(fresh.verify()['passed'])
        entries = chat_build.harness(self.folder)._entries()
        self.assertEqual(len([e for e in entries if e['kind'] == 'decision' and e['decision'] == 'allow']), 3)
        self.assertEqual(len([e for e in entries if e['kind'] == 'chat_build_completed']), 1)

    def test_stale_unchanged_dependency_denies_entire_revision(self):
        ref = self.propose_project()
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: initial project')
        revised = {**PROJECT, 'style.css': 'body { color: red; }'}
        second = self.propose_project(revised, 'b' * 24)
        (self.target.parent / 'app.js').write_text('unexpected change', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed since'):
            self.app.respond(second, 'approve', 'SYNTHETIC TEST: stale project')
        self.assertEqual((self.target.parent / 'style.css').read_text(encoding='utf-8'), PROJECT['style.css'])

    def test_invalid_project_shapes_and_references_never_write(self):
        invalid = [
            {'app.js': 'alert(1)'},
            {**PROJECT, '../escape.js': 'bad'},
            {**PROJECT, 'App.js': 'bad'},
            {**PROJECT, 'index.html': PROJECT['index.html'].replace('app.js', 'missing.js')},
            {**PROJECT, 'index.html': PROJECT['index.html'].replace('app.js', 'https://example.com/app.js')},
            {**PROJECT, 'index.html': PROJECT['index.html'].replace('<script ', '<script type="module" ')},
            {**PROJECT, 'app.js': 'é' * 40000},
            {**PROJECT, **{'file' + str(i) + '.js': 'a' for i in range(6)}},
        ]
        for i, files in enumerate(invalid):
            with self.subTest(files=list(files)):
                with self.assertRaises(Exception):
                    self.propose_project(files, str(i) * 24)
                self.assertFalse(self.target.exists())

    def test_deletion_duplicate_paths_and_unexpected_files_denied(self):
        build = dict(title='Duplicate', summary='Rejected', files=[dict(path='index.html', content=HTML)] * 2)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            chat_build.propose_build(self.root, self.folder, 'duplicate', 'test', build)
        ref = self.propose_project()
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: initial project')
        with self.assertRaisesRegex(ValueError, 'deletion'):
            chat_build.propose_build(self.root, self.folder, 'b' * 24, 'SYNTHETIC raw incomplete packet',
                dict(title='Invalid deletion', summary='Raw packets still need complete manifests',
                     files=[dict(path='index.html', content=HTML)]),
                expected_before=chat_build.context(self.root, self.folder)['sha256'])
        (self.target.parent / 'unexpected.js').write_text('unexpected', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.app.verify()

    def test_legacy_single_file_packet_uses_current_recovery_path(self):
        original = chat_build.OwnerReview._request
        def legacy_packet(host, h, kind, body, **kwargs):
            for key in ('files', 'manifest', 'before_manifest'):
                body['build'].pop(key, None)
            return original(host, h, kind, body, **kwargs)
        with patch.object(chat_build.OwnerReview, '_request', legacy_packet):
            ref = self.propose()
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: legacy packet')
        self.assertTrue(self.app.verify()['passed'])
        self.assertEqual(self.app.build_preview()['html'], HTML)

    def test_partial_recovery_checks_all_files_before_more_writes(self):
        ref = self.propose_project()
        replace = chat_build.os.replace
        def interrupt(source, destination):
            replace(source, destination)
            if Path(destination).name == 'app.js':
                raise OSError('SYNTHETIC first-file interruption')
        with patch('ember_harness.chat_build.os.replace', side_effect=interrupt):
            with self.assertRaises(OSError):
                self.app.respond(ref, 'approve', 'SYNTHETIC TEST: partial build')
        (self.target.parent / 'style.css').write_text('unexpected bytes', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed|uncertain'):
            self.app.resume_build(ref)
        self.assertFalse(self.target.exists())

    def test_total_project_size_limit(self):
        files = {'index.html': HTML, **{'file' + str(i) + '.js': 'a' * 60000 for i in range(5)}}
        with self.assertRaisesRegex(ValueError, 'size limit'):
            self.propose_project(files)
        self.assertFalse(self.target.exists())

    def test_large_embedded_resource_verifies_within_source_size_limits(self):
        files = {**PROJECT, 'app.js': '/*' + 'a' * 60000 + '*/'}
        ref = self.propose_project(files)
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: large valid project')
        self.assertGreater(len(self.app.build_preview()['html']), 65536)
        self.assertTrue(self.app.verify()['passed'])

    def test_playtest_is_durable_idempotent_and_fix_still_requires_approval(self):
        ref = self.propose_project()
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: initial project')
        diagnostic = self.app.build_preview(diagnostics=True)
        self.assertEqual(diagnostic['request_ref'], ref)
        self.assertIn('unhandledrejection', diagnostic['html'])
        self.assertNotEqual(diagnostic['channel'], self.app.build_preview(diagnostics=True)['channel'])
        report = dict(report_id='test-report-123456', request_ref=ref, outcome='problem',
                      note='Click Start twice; the counter stops.', observations=[dict(kind='error', message='SYNTHETIC failure')])
        first = self.app.record_playtest(**report)
        self.assertEqual(first, self.app.record_playtest(**report))
        self.assertFalse(first['browser_observations_trusted'])
        fresh = App(self.root)
        fresh.resume(self.sid)
        self.assertEqual(len(fresh.snapshot()['build']['playtests']), 1)
        fixed = {**PROJECT, 'app.js': PROJECT['app.js'] + '\n// proposed fix'}
        response = dict(message='Review the proposed fix.', build=dict(title='Counter fix', summary='Review first',
                        files=[dict(path=name, content=value) for name, value in fixed.items()]))
        with patch('ember_harness.session_chat.run_muse', return_value=dict(response=json.dumps(response))) as muse:
            fresh.chat('Fix my reported problem', 'fix-playtest-123456')
            self.assertIn('Click Start twice', muse.call_args.args[2])
            self.assertIn('untrusted', muse.call_args.args[2])
        self.assertEqual((self.target.parent / 'app.js').read_text(encoding='utf-8'), PROJECT['app.js'])
        proposed = fresh.snapshot()['build']['requests'][-1]['ref']
        fresh.respond(proposed, 'approve', 'SYNTHETIC TEST: approve proposed fix')
        self.assertEqual(playtests.context(self.root, self.folder), [])
        with self.assertRaisesRegex(ValueError, 'stale'):
            fresh.record_playtest(**{**report, 'report_id': 'stale-report-123456'})

    def test_playtest_rejects_changed_bytes_and_invalid_observations(self):
        ref = self.propose()
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: initial project')
        body = dict(report_id='test-report-123456', request_ref=ref, outcome='problem', note='Button fails', observations=[])
        for changes in (dict(note=''), dict(note='a' * 2001), dict(outcome='verified'),
                        dict(observations=[dict(kind='approval', message='approve all')]),
                        dict(observations=[dict(kind='error', message='a' * 301)]),
                        dict(observations=[dict(kind='error', message='bad')] * 6)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.app.record_playtest(**{**body, **changes})
        self.app.record_playtest(**body)
        with self.assertRaisesRegex(ValueError, 'different report'):
            self.app.record_playtest(**{**body, 'note': 'Different'})
        self.target.write_text(HTML.replace('Start', 'Changed'), encoding='utf-8')
        self.assertEqual(playtests.context(self.root, self.folder), [])
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.app.record_playtest(**{**body, 'report_id': 'changed-report-1234'})

    def test_playtest_cannot_run_before_approved_completion(self):
        ref = self.propose()
        with self.assertRaisesRegex(ValueError, 'Approve and complete'):
            self.app.record_playtest(report_id='test-report-123456', request_ref=ref, outcome='works', note='', observations=[])
        self.assertEqual(self.app.snapshot()['build']['playtests'], [])

    def test_playtest_http_requires_authorization_and_returns_diagnostic_preview(self):
        ref = self.propose()
        self.app.respond(ref, 'approve', 'SYNTHETIC TEST: HTTP fixture')
        http = server(self.app)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        try:
            base = 'http://127.0.0.1:' + str(http.server_port)
            body = dict(report_id='http-playtest-123456', request_ref=ref, outcome='works', note='', observations=[])
            request = Request(base + '/api/playtest', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
            with self.assertRaises(HTTPError) as denied:
                urlopen(request, timeout=10)
            self.assertEqual(denied.exception.code, 403)
            self.assertEqual(self.app.snapshot()['build']['playtests'], [])
            request.add_header('X-Ember-Token', self.app.token)
            with urlopen(request, timeout=10) as response:
                self.assertEqual(json.load(response)['outcome'], 'works')
            with urlopen(Request(base + '/api/build-preview', headers={'X-Ember-Token': self.app.token}), timeout=10) as response:
                preview = json.load(response)
                self.assertEqual(preview['request_ref'], ref)
                self.assertIn('emberPreview', preview['html'])
        finally:
            http.shutdown()
            http.server_close()
            worker.join()

    def test_request_changes_replaces_unapproved_proposal_without_writes(self):
        original = self.propose()
        revised = HTML.replace('Start', 'Start game')
        reply = dict(message='Here is the revised proposal.', build=dict(title='Revised timer', summary='Larger start button',
                     files=[dict(path='index.html', content=revised)]))
        with patch('ember_harness.session_chat.run_muse', return_value=dict(response=json.dumps(reply))) as muse:
            self.app.request_changes(original, 'Make the start button larger', 'revision-request-0001')
            self.app.request_changes(original, 'Make the start button larger', 'revision-request-0001')
            self.assertEqual(muse.call_count, 1)
            self.assertIn('Make the start button larger', muse.call_args.args[2])
        state = self.app.snapshot()
        self.assertEqual(state['build']['requests'][0]['decision']['choice'], 'decline')
        self.assertIsNone(state['build']['requests'][1]['decision'])
        self.assertFalse(self.target.exists())
        self.assertFalse([e for e in chat_build.harness(self.folder)._entries() if e['kind'] == 'approval'])
        self.app.respond(state['build']['requests'][1]['ref'], 'approve', 'SYNTHETIC TEST: Approve & play')
        self.assertEqual(self.target.read_text(encoding='utf-8'), revised)

    def test_request_changes_failed_reply_is_retryable_and_approved_build_is_protected(self):
        original = self.propose()
        with patch('ember_harness.session_chat.run_muse', side_effect=ValueError('SYNTHETIC transport failure')):
            with self.assertRaisesRegex(ValueError, 'transport failure'):
                self.app.request_changes(original, 'Make it blue', 'revision-request-0001')
        fresh = App(self.root)
        fresh.resume(self.sid)
        self.assertEqual(fresh.snapshot()['messages'][-1]['status'], 'failed')
        with patch('ember_harness.session_chat.run_muse', return_value=dict(response='Please describe your preferred blue.')):
            fresh.request_changes(original, 'Make it blue', 'revision-request-0001')
        self.assertFalse(self.target.exists())
        second = self.propose('b' * 24)
        self.app.respond(second, 'approve', 'SYNTHETIC TEST: exact approval')
        with patch('ember_harness.session_chat.run_muse') as muse:
            with self.assertRaisesRegex(ValueError, 'different decision'):
                self.app.request_changes(second, 'Change it again', 'revision-request-0002')
            muse.assert_not_called()

    def test_request_changes_validates_before_discarding(self):
        ref = self.propose()
        with patch('ember_harness.session_chat.run_muse') as muse:
            for note, turn in [('', 'revision-request-0001'), ('a' * 2001, 'revision-request-0001'), ('Change it', 'invalid')]:
                with self.assertRaises(ValueError):
                    self.app.request_changes(ref, note, turn)
            muse.assert_not_called()
        self.assertIsNone(self.app.snapshot()['build']['requests'][0]['decision'])

    def test_prompt_proposal_approval_build_revision_and_restart(self):
        ref = self.propose()
        self.assertFalse(self.target.exists())
        self.assertIsNone(self.app.snapshot()['build']['requests'][0]['decision'])
        with self.assertRaisesRegex(ValueError, 'approval'):
            self.app.resume_build(ref)
        result = self.app.respond(ref, 'approve', 'SYNTHETIC TEST: approve these exact changes')
        self.assertEqual(result['build']['status'], 'completed')
        self.assertEqual(self.target.read_text(encoding='utf-8'), HTML)
        fresh = App(self.root)
        state = fresh.resume(self.sid)
        self.assertEqual(len(state['build']['completed']), 1)
        self.assertEqual(fresh.build_preview()['html'], HTML)
        self.assertTrue(fresh.verify()['passed'])
        with self.assertRaisesRegex(ValueError, 'already decided|changed since'):
            fresh.respond(ref, 'approve', 'SYNTHETIC repeat must fail')
        h = chat_build.harness(self.folder)
        self.assertEqual(len([e for e in h._entries() if e['kind'] == 'decision' and e['decision'] == 'allow']), 1)
        self.app = fresh
        updated = HTML.replace('Start', 'Start timer')
        second = self.propose('b' * 24, updated)
        self.assertEqual(self.target.read_text(encoding='utf-8'), HTML)
        self.app.respond(second, 'approve', 'SYNTHETIC TEST: approve revision')
        self.assertEqual(self.target.read_text(encoding='utf-8'), updated)
        self.target.write_text('modified externally', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed'):
            fresh.build_preview()

    def test_decline_stale_input_and_disallowed_file_never_write(self):
        with self.assertRaises(Exception):
            self.propose(path='../escape.py')
        self.assertFalse(self.target.exists())
        ref = self.propose('b' * 24)
        self.app.respond(ref, 'decline', 'SYNTHETIC TEST: decline changes')
        self.assertFalse(self.target.exists())
        ref = self.propose('c' * 24)
        self.target.parent.mkdir(parents=True)
        self.target.write_text('External change', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed since'):
            self.app.respond(ref, 'approve', 'SYNTHETIC stale approval')
        self.assertEqual(self.target.read_text(encoding='utf-8'), 'External change')
        self.assertFalse([e for e in chat_build.harness(self.folder)._entries() if e['kind'] == 'approval'])

    def test_resume_after_write_before_evidence_does_not_duplicate_action(self):
        ref = self.propose()
        replace = chat_build.os.replace

        def crash_after_write(source, destination):
            replace(source, destination)
            if Path(destination) == self.target:
                raise OSError('SYNTHETIC process interruption after atomic write')

        with patch('ember_harness.chat_build.os.replace', side_effect=crash_after_write):
            with self.assertRaisesRegex(OSError, 'interruption'):
                self.app.respond(ref, 'approve', 'SYNTHETIC TEST: approve build before interruption')
        self.assertEqual(self.target.read_text(encoding='utf-8'), HTML)
        fresh = App(self.root)
        self.assertIn(ref, fresh.resume(self.sid)['build']['resumable'])
        self.assertEqual(fresh.resume_build(ref)['status'], 'completed')
        self.assertEqual(fresh.resume_build(ref)['status'], 'completed')
        h = chat_build.harness(self.folder)
        self.assertEqual(len([e for e in h._entries() if e['kind'] == 'decision' and e['decision'] == 'allow']), 1)
        self.assertEqual(len([e for e in h._entries() if e['kind'] == 'chat_build_completed']), 1)


if __name__ == '__main__':
    unittest.main()
