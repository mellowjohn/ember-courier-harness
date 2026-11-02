"""Workspace contracts, exclusions and exact sandbox application; synthetic owner decisions."""
from contextlib import redirect_stdout
from copy import deepcopy
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ember_harness import workspace
from ember_harness.local_ui import App, server

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'examples').mkdir()
        (self.root / 'examples/product_demo.py').touch()
        self.app = App(self.root)
        self.app.start('SYNTHETIC workspace onboarding', chat_only=True)
        self.sid = self.app.session['id']
        self.folder = self.app.sessions_dir / self.sid
        self.source = self.root / 'Existing game'
        self.source.mkdir()
        (self.source / 'app.js').write_text('throw new Error("never execute source")', encoding='utf-8')

    def prepare(self, stage='scan'):
        with redirect_stdout(io.StringIO()):
            return self.app.workspace_control(self.sid, stage, **(
                dict(source=str(self.source)) if stage == 'scan' else dict(run_id=self.saved()['run_id'])))['request_ref']

    def respond(self, ref, choice='approve'):
        with redirect_stdout(io.StringIO()):
            return self.app.respond(ref, choice, 'SYNTHETIC fixture: ' + choice + ' reviewed workspace step')

    def saved(self):
        return workspace.status(self.folder)['latest']

    def scan(self):
        return self.respond(self.prepare())

    def plan(self):
        self.scan()
        return self.respond(self.prepare('plan'))

    def files(self, folder=None):
        return {p.relative_to(folder or self.source).as_posix(): sha256(p.read_bytes()).hexdigest()
                for p in (folder or self.source).rglob('*') if p.is_file()}

    def test_scan_is_reviewed_read_only_and_excludes_secrets_source_and_ignored_contents(self):
        (self.source / '.env').write_text('SENSITIVE CONTENT')
        (self.source / 'id_private').write_text('SENSITIVE CONTENT')
        (self.source / '.gitignore').write_text('*.log\n!keep.log\ncache/\n')
        for name in ('skip.log', 'keep.log'):
            (self.source / name).write_text('contents')
        (self.source / 'cache').mkdir(); (self.source / 'cache/private.js').write_text('do not open')
        before = self.files()
        ref = self.prepare()
        self.assertIsNone(self.saved().get('scan'))
        original = Path.open

        def guard(path, *args, **kwargs):
            if path.is_relative_to(self.source) and path.name != '.gitignore':
                self.fail('Unexpected source content read: ' + str(path))
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', guard):
            result = self.respond(ref)
        report = result['result']; rows = {r['path']: r for r in report['entries']}
        self.assertEqual(before, self.files())
        self.assertEqual(rows['.env']['reason'], 'secret_name_only')
        self.assertEqual(rows['id_private']['reason'], 'secret_name_only')
        self.assertEqual(rows['skip.log']['reason'], 'gitignored')
        self.assertEqual(rows['keep.log']['kind'], 'file')
        self.assertNotIn('cache/private.js', rows)
        self.assertNotIn('SENSITIVE CONTENT', json.dumps(workspace.status(self.folder)))
        self.assertEqual(report['languages'], ['JavaScript'])
        self.assertEqual(self.app.snapshot()['workspace']['latest'], self.saved())

    def test_plan_records_conflicts_identical_files_and_full_create_contents(self):
        (self.source / 'AGENTS.md').write_text('Existing human rules')
        (self.source / 'evidence').mkdir()
        (self.source / 'evidence/README.md').write_bytes(workspace.FILES['evidence/README.md'].encode())
        before = self.files()
        result = self.plan()['result']; entries = {r['path']: r for r in result['entries']}
        self.assertEqual(entries['AGENTS.md']['action'], 'conflict')
        self.assertEqual(entries['evidence/README.md']['action'], 'skip_exists')
        self.assertEqual(entries['contracts/README.md']['action'], 'create')
        self.assertEqual(entries['.gitattributes']['action'], 'manual')
        for entry in result['entries']:
            self.assertEqual(entry['bytes'], len(entry['content'].encode()))
            self.assertEqual(entry['content_sha256'], sha256(entry['content'].encode()).hexdigest())
        self.assertEqual(before, self.files())
        self.assertFalse(Path(self.saved()['sandbox']).exists())

    def test_exact_action_approval_create_only_evidence_and_idempotence(self):
        (self.source / 'AGENTS.md').write_text('Human instructions')
        before = self.files(); self.plan()
        result = self.respond(self.prepare('apply'))
        exact = result['awaiting_action']
        self.assertFalse(Path(self.saved()['sandbox']).exists())
        h = workspace.authority(self.folder)
        payload = workspace.load_request(h, exact)
        act = payload['body']['action']
        self.assertEqual(h.check(act)['decision'], 'needs_approval')
        changed = deepcopy(act); changed['args']['plan_sha256'] = 'f' * 64
        self.assertEqual(h.check(changed)['decision'], 'deny')
        result = self.respond(exact)
        sandbox = Path(result['result']['sandbox'])
        expected = {r['path']: r['content_sha256'] for r in self.saved()['plan']['entries'] if r['action'] == 'create'}
        self.assertEqual(self.files(sandbox), expected)
        self.assertEqual(before, self.files())
        self.assertFalse((sandbox / 'AGENTS.md').exists())
        self.assertEqual(self.respond(exact), result)
        self.assertTrue(h.audit_verify())
        from ember_harness.contract_lock import verify
        self.assertTrue(verify(h.root)['ok'])
        workspace.validate_history(h, h._entries())
        self.assertTrue(any(e['kind'] == 'evidence' and e['status'] == 'complete' for e in h._entries()))
        next(sandbox.rglob('*.md')).write_text('Changed after receipt')
        with self.assertRaisesRegex(ValueError, 'changed since completion'):
            self.respond(exact)

    def test_new_or_changed_source_after_scan_stops_plan_and_rescan_recovers(self):
        self.scan(); (self.source / 'README.md').write_text('new input')
        with self.assertRaisesRegex(ValueError, 'changed since scanning'):
            self.respond(self.prepare('plan'))
        self.assertFalse(Path(self.saved()['sandbox']).exists())
        old_run = self.saved()['run_id']
        self.scan()
        self.assertNotEqual(self.saved()['run_id'], old_run)
        self.respond(self.prepare('plan'))
        self.assertIn('plan', self.saved())

    def test_source_conflict_or_sandbox_conflict_before_apply_writes_nothing(self):
        self.plan()
        exact = self.respond(self.prepare('apply'))['awaiting_action']
        (self.source / 'contracts').mkdir()
        (self.source / 'contracts/README.md').write_text('new source input')
        with self.assertRaisesRegex(ValueError, 'changed since scanning'):
            self.respond(exact)
        self.assertFalse(Path(self.saved()['sandbox']).exists())

    def test_sandbox_preflight_is_whole_plan_and_preserves_conflict(self):
        self.plan(); exact = self.respond(self.prepare('apply'))['awaiting_action']
        sandbox = Path(self.saved()['sandbox']); (sandbox / 'triage').mkdir(parents=True)
        (sandbox / 'triage/README.md').write_text('existing sandbox file')
        before = self.files(sandbox)
        with self.assertRaisesRegex(ValueError, 'Sandbox changed'):
            self.respond(exact)
        self.assertEqual(self.files(sandbox), before)
        h = workspace.authority(self.folder)
        act = workspace.load_request(h, exact)['body']['action']
        self.assertFalse(any(e['kind'] == 'decision' and e.get('action') == act and e['decision'] == 'allow' for e in h._entries()))

    def test_identical_or_unplanned_sandbox_files_without_started_action_are_stale(self):
        self.plan(); exact = self.respond(self.prepare('apply'))['awaiting_action']
        sandbox = Path(self.saved()['sandbox']); sandbox.mkdir(parents=True)
        (sandbox / 'AGENTS.md').write_bytes(workspace.FILES['AGENTS.md'].encode())
        with self.assertRaisesRegex(ValueError, 'Sandbox changed'):
            self.respond(exact)
        (sandbox / 'AGENTS.md').unlink()
        (sandbox / 'unplanned.txt').write_text('preserve me')
        with self.assertRaisesRegex(ValueError, 'unexpected path'):
            self.respond(exact)
        self.assertEqual(self.files(sandbox), {'unplanned.txt': sha256(b'preserve me').hexdigest()})

    def test_interrupted_started_action_resumes_exact_bytes_without_another_approval(self):
        self.plan(); exact = self.respond(self.prepare('apply'))['awaiting_action']
        original_open = Path.open
        sandbox = Path(self.saved()['sandbox'])

        def interrupted(path, *args, **kwargs):
            if path == sandbox / 'contracts/README.md' and args and args[0] == 'xb':
                raise OSError('SYNTHETIC interrupted after first write')
            return original_open(path, *args, **kwargs)
        with patch.object(Path, 'open', interrupted), self.assertRaisesRegex(OSError, 'SYNTHETIC interrupted'):
            self.respond(exact)
        self.assertTrue((sandbox / 'AGENTS.md').is_file())
        result = self.respond(exact)
        self.assertEqual(result['status'], 'completed')
        h = workspace.authority(self.folder)
        action_approvals = [e for e in h._entries() if e['kind'] == 'approval' and e.get('scope') == 'action']
        self.assertEqual(len(action_approvals), 1)

    def test_restart_retains_reviews_inventory_and_exact_sandbox_plan(self):
        ref = self.prepare()
        fresh = App(self.root); state = fresh.resume(self.sid)
        self.assertEqual(state['workspace']['pending'], ref)
        self.app = fresh; self.respond(ref)
        self.respond(self.prepare('plan'))
        exact = self.respond(self.prepare('apply'))['awaiting_action']
        fresh = App(self.root); state = fresh.resume(self.sid)
        self.assertEqual(state['workspace']['pending'], exact)
        self.app = fresh; self.respond(exact)
        self.assertIn('apply', fresh.resume(self.sid)['workspace']['latest'])

    def test_decline_stale_reviews_and_wrong_session_grant_no_authority(self):
        ref = self.prepare(); self.respond(ref, 'decline')
        self.assertNotIn('scan', self.saved())
        new = self.prepare()
        with self.assertRaisesRegex(ValueError, 'current workspace'):
            self.respond(ref)
        with self.assertRaisesRegex(ValueError, 'intended session'):
            self.app.workspace_control('f' * 24, 'scan', source=str(self.source))
        self.respond(new)
        self.assertFalse(Path(self.saved()['sandbox']).exists())

    def test_report_pin_and_contract_tampering_fail_closed(self):
        ref = self.prepare(); h = workspace.authority(self.folder)
        c = workspace.load_request(h, ref)['body']['contracts'][-1]['contract']
        path = h._path(c['id'], 1); changed = deepcopy(c); changed['goal'] += ' tampered'
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.respond(ref)
        path.write_text(json.dumps(c)); self.respond(ref)
        run = self.saved()['run_id']
        path = workspace.run_folder(h, run) / 'scan.json'
        ref = self.prepare('plan'); path.write_text('{}')
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            self.respond(ref)

    def test_inventory_limits_and_unsupported_ignore_syntax_fail_with_no_partial_report(self):
        ref = self.prepare()
        with patch.object(workspace, 'MAX_ENTRIES', 0), self.assertRaisesRegex(ValueError, 'inventory limit'):
            self.respond(ref)
        self.assertNotIn('scan', self.saved())
        (self.source / '.gitignore').write_text('[abc].log')
        with self.assertRaisesRegex(ValueError, 'Unsupported .gitignore'):
            self.scan()
        self.assertNotIn('scan', self.saved())

    def test_nested_gitignore_negation_double_star_and_excluded_engine_paths(self):
        for folder in ('assets', 'assets/cache', 'engine', 'node_modules'):
            (self.source / folder).mkdir(exist_ok=True)
        (self.source / '.gitignore').write_text('**/cache/\n*.log\n!keep.log\n')
        (self.source / 'assets/.gitignore').write_text('*.tmp\n')
        for name in ('assets/cache/hidden.js', 'assets/gone.tmp', 'assets/keep.log', 'assets/gone.log', 'engine/source.cpp', 'node_modules/huge.js'):
            (self.source / name).write_text('not opened')
        report = self.scan()['result']; rows = {r['path']: r for r in report['entries']}
        self.assertEqual(rows['assets/cache']['reason'], 'gitignored')
        self.assertEqual(rows['assets/gone.tmp']['reason'], 'gitignored')
        self.assertEqual(rows['assets/keep.log']['kind'], 'file')
        self.assertEqual(rows['engine']['reason'], 'engine_paused')
        self.assertNotIn('engine/source.cpp', rows)

    def test_gate_denies_secret_reads_writes_network_delete_and_wrong_plan(self):
        self.scan(); h = workspace.authority(self.folder)
        cid = workspace.requests(self.folder)[-1]['payload']['body']['contracts'][-1]['contract']['id']
        c = h._load(h._active(h._entries())[cid])
        for tool, args in [('fs.read', dict(path=(self.source / '.env').as_posix())),
                           ('fs.read', dict(path=(self.source / '.ENV/.gitignore').as_posix())),
                           ('fs.read', dict(path=(self.source / 'Secrets/.gitignore').as_posix())),
                           ('fs.read', dict(path=(self.source / 'Engine/.gitignore').as_posix())),
                           ('fs.read', dict(path=(self.source / 'app.js').as_posix())),
                           ('fs.write', dict(path=(self.source / 'new.js').as_posix(), content='x', expected_sha256='f'*64))]:
            self.assertEqual(h.check(workspace.action(c, tool, args))['decision'], 'deny')
        for tool in ('fs.delete', 'network.fetch'):
            act = workspace.action(c, 'workspace.scan', dict(root=self.source.as_posix()))
            act.update(tool=tool, args={})
            self.assertEqual(h.check(act)['decision'], 'deny')

    def test_revoked_workspace_scope_blocks_reviewed_sandbox_action(self):
        self.plan(); exact = self.respond(self.prepare('apply'))['awaiting_action']
        h = workspace.authority(self.folder)
        body = workspace.load_request(h, exact)['body']['workspace_apply']
        h.revoke(body['scope_id'], approver='johnathan', reason='SYNTHETIC owner revocation')
        with self.assertRaises((ValueError, KeyError)):
            self.respond(exact)
        self.assertFalse(Path(self.saved()['sandbox']).exists())

    def test_paused_engine_roots_traversal_and_internal_store_are_rejected(self):
        for source in (str(self.source / '..'), str(self.root), str(self.folder), 'relative/path'):
            with self.assertRaises(ValueError):
                self.app.workspace_control(self.sid, 'scan', source=source)
        engine = self.root / 'Wrathful Conquest'; engine.mkdir()
        with self.assertRaisesRegex(ValueError, 'paused engine'):
            self.app.workspace_control(self.sid, 'scan', source=str(engine))

    def test_links_are_never_followed_and_link_root_is_denied(self):
        outside = self.root / 'Outside'; outside.mkdir(); (outside / '.env').write_text('secret')
        link = self.source / 'linked'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Host does not permit creating symbolic links')
        rows = {r['path']: r for r in self.scan()['result']['entries']}
        self.assertEqual(rows['linked']['reason'], 'link_excluded')
        self.assertNotIn('linked/.env', rows)
        with self.assertRaises(ValueError):
            self.app.workspace_control(self.sid, 'scan', source=str(link))

    def test_http_authentication_and_scan_review_flow(self):
        http = server(self.app); thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
        self.addCleanup(http.server_close); self.addCleanup(http.shutdown)
        base = f'http://127.0.0.1:{http.server_port}'

        def request(route, data=None, authenticated=True):
            headers = {'Content-Type': 'application/json'}
            if authenticated:
                headers['X-Ember-Token'] = self.app.token
            with urlopen(Request(base + '/api/' + route, data=json.dumps(data).encode() if data else None, headers=headers), timeout=20) as response:
                return json.load(response)
        body = dict(session_id=self.sid, action='scan', source=str(self.source))
        with self.assertRaises(HTTPError) as denied:
            request('workspace', body, False)
        self.assertEqual(denied.exception.code, 403)
        self.assertFalse(workspace.requests(self.folder))
        with redirect_stdout(io.StringIO()):
            result = request('workspace', body)
            ref = result['request_ref']
            result = request('decide', dict(ref=ref, choice='approve', quote='SYNTHETIC HTTP approval'))
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(request('state')['workspace']['latest']['scan']['files'], 1)


if __name__ == '__main__':
    unittest.main()
