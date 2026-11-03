"""Reviewed source snapshots: real files/gates, synthetic owner choices, no execution."""
from contextlib import redirect_stdout
from hashlib import sha256
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import test_workspace as shared
from ember_harness import chat_build, workspace
from ember_harness.contract_lock import verify


PROJECT = {
    'index.html': '<!doctype html><html><head><link rel="stylesheet" href="style.css"></head><body><button>Start</button><script src="app.js"></script></body></html>',
    'style.css': 'body{background:#123;color:#fff}',
    'app.js': 'let score=0;document.querySelector("button").onclick=()=>{score++};',
}


class WorkspaceImportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = shared.WorkspaceTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.folder, self.source = self.fixture.folder, self.fixture.source
        for name, content in PROJECT.items():
            (self.source / name).write_bytes(content.encode('utf-8'))

    def prepare(self, stage):
        with redirect_stdout(io.StringIO()):
            return workspace.prepare(self.folder, stage=stage, run_id=self.fixture.saved()['run_id'])['request_ref']

    def plan(self):
        self.fixture.scan()
        return self.fixture.respond(self.prepare('import_plan'))['result']

    def copy(self):
        self.plan()
        exact = self.fixture.respond(self.prepare('import_apply'))['awaiting_action']
        return exact, self.fixture.respond(exact)['result']

    def test_separate_reviews_exact_copy_retained_receipt_and_no_game_adoption(self):
        (self.source / '.env').write_text('SENSITIVE never read')
        (self.source / 'notes.md').write_text('Owner notes remain outside import')
        (self.source / 'art.png').write_bytes(b'Not an imported image')
        before = self.fixture.files()
        self.fixture.scan()
        h = workspace.authority(self.folder)
        scan = workspace.requests(self.folder)[-1]['payload']['body']['contracts'][-1]['contract']
        self.assertEqual(h.check(workspace.action(scan, 'fs.read', dict(path=(self.source/'app.js').as_posix())))['decision'], 'deny')
        ref = self.prepare('import_plan')
        self.assertNotIn('import_plan', self.fixture.saved())
        plan = self.fixture.respond(ref)['result']
        self.assertEqual({r['path']: r['content'] for r in plan['entries']}, PROJECT)
        self.assertEqual(plan['manifest'], {k: sha256(v.encode()).hexdigest() for k,v in PROJECT.items()})
        self.assertIn('.env', [r['path'] for r in plan['omitted']])
        self.assertNotIn('SENSITIVE', str(plan))
        self.assertFalse(Path(plan['sandbox']).exists())
        exact = self.fixture.respond(self.prepare('import_apply'))['awaiting_action']
        act = workspace.load_request(h, exact)['body']['action']
        self.assertEqual(h.check(act)['decision'], 'needs_approval')
        changed = dict(act, args={**act['args'], 'dest': self.source.as_posix()})
        self.assertEqual(h.check(changed)['decision'], 'deny')
        result = self.fixture.respond(exact)
        self.assertEqual(workspace.imported_files(self.folder, self.fixture.saved()['run_id']), PROJECT)
        self.assertEqual(self.fixture.files(), before)
        self.assertFalse(chat_build.context(self.fixture.root, self.folder)['files'])
        self.assertEqual(self.fixture.respond(exact), result)
        self.assertTrue(verify(h.root)['ok'])
        self.assertEqual(len([e for e in h._entries() if e['kind']=='approval' and e.get('scope')=='action']), 1)

    def test_source_change_with_restored_metadata_blocks_exact_action(self):
        plan = self.plan()
        exact = self.fixture.respond(self.prepare('import_apply'))['awaiting_action']
        path = self.source / 'app.js'; info = path.stat()
        path.write_bytes(PROJECT['app.js'].replace('score++', 'score--').encode())
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, 'inputs_unverified|inputs changed'):
            self.fixture.respond(exact)
        self.assertFalse(Path(plan['sandbox']).exists())

    def test_destination_conflicts_and_completed_copy_changes_are_never_overwritten(self):
        plan = self.plan()
        exact = self.fixture.respond(self.prepare('import_apply'))['awaiting_action']
        target = Path(plan['sandbox']); target.mkdir(parents=True)
        (target / 'keep.txt').write_text('preserve this')
        with self.assertRaisesRegex(ValueError, 'Sandbox changed'):
            self.fixture.respond(exact)
        self.assertEqual((target/'keep.txt').read_text(), 'preserve this')
        self.assertFalse((target/'index.html').exists())

    def test_retained_import_is_independent_of_source_but_rejects_extra_or_changed_copy(self):
        exact, result = self.copy()
        run = self.fixture.saved()['run_id']; target = Path(result['sandbox'])
        (self.source/'app.js').write_text('Changed external source after snapshot')
        self.assertEqual(workspace.imported_files(self.folder, run), PROJECT)
        extra = target/'unexpected.js'; extra.write_text('do not include')
        with self.assertRaisesRegex(ValueError, 'unexpected path'):
            workspace.imported_files(self.folder, run)
        extra.unlink()
        (target/'app.js').write_text('changed copy')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.fixture.respond(exact)

    def test_interrupted_copy_replays_exact_action_without_another_approval(self):
        plan = self.plan(); exact = self.fixture.respond(self.prepare('import_apply'))['awaiting_action']
        target = Path(plan['sandbox']); original = Path.open
        def interrupt(path, *args, **kwargs):
            if path == target/'index.html' and args and args[0] == 'xb':
                raise OSError('SYNTHETIC copy interruption')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', interrupt), self.assertRaisesRegex(OSError, 'copy interruption'):
            self.fixture.respond(exact)
        self.assertTrue((target/'app.js').exists())
        self.fixture.respond(exact)
        self.assertEqual(workspace.imported_files(self.folder, self.fixture.saved()['run_id']), PROJECT)
        h = workspace.authority(self.folder)
        self.assertEqual(len([e for e in h._entries() if e['kind']=='approval' and e.get('scope')=='action']), 1)

    def test_nested_dependency_and_oversized_source_refuse_import_without_writes(self):
        (self.source/'index.html').write_text('<html><body><script src="scripts/game.js"></script></body></html>')
        (self.source/'scripts').mkdir(); (self.source/'scripts/game.js').write_text('never execute')
        self.fixture.scan()
        with self.assertRaises(ValueError):
            self.fixture.respond(self.prepare('import_plan'))
        self.assertNotIn('import_plan', self.fixture.saved())
        (self.source/'index.html').write_bytes(PROJECT['index.html'].encode())
        (self.source/'app.js').write_bytes(b'x'*(workspace.MAX_READ+1))
        self.fixture.scan()
        with self.assertRaisesRegex(ValueError, '64 KiB'):
            self.fixture.respond(self.prepare('import_plan'))
        self.assertFalse(Path(self.fixture.saved()['import_sandbox']).exists())

    def test_passive_git_and_asset_inventory_never_reads_config_hooks_or_code(self):
        git = self.source/'.git'; (git/'refs/heads').mkdir(parents=True); (git/'hooks').mkdir()
        (git/'HEAD').write_text('ref: refs/heads/main\n')
        (git/'refs/heads/main').write_text('a'*40+'\n')
        (git/'config').write_text('[include]\n path=/outside/secrets\n')
        (git/'hooks/post-checkout').write_text('NEVER EXECUTE')
        (self.source/'art.png').write_bytes(b'asset contents remain unread')
        original = Path.open
        def restricted(path, *args, **kwargs):
            if path.is_relative_to(self.source) and path not in (git/'HEAD', git/'refs/heads/main'):
                self.fail('Unexpected source read: ' + str(path))
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', restricted):
            report = self.fixture.scan()['result']
        self.assertEqual(report['git']['branch'], 'main')
        self.assertEqual(report['git']['commit'], 'a'*40)
        self.assertEqual(report['git']['worktree_state'], 'not_inspected')
        h = workspace.authority(self.folder)
        contract = workspace.requests(self.folder)[-1]['payload']['body']['contracts'][-1]['contract']
        traversal = self.source.as_posix() + '/.git/refs/heads/../../config'
        self.assertEqual(h.check(workspace.action(contract, 'fs.read', dict(path=traversal)))['decision'], 'deny')
        self.assertEqual(report['project']['assets'][0]['path'], 'art.png')
        self.assertEqual(report['project']['browser_candidates'], ['app.js', 'index.html', 'style.css'])
        self.assertNotIn('NEVER EXECUTE', str(report))

    def test_external_git_pointer_and_revoked_import_scope_are_not_followed(self):
        (self.source/'.git').write_text('gitdir: /outside/private\n')
        report = self.fixture.scan()['result']
        self.assertEqual(report['git']['state'], 'unsupported_metadata')
        self.fixture.respond(self.prepare('import_plan'))
        exact = self.fixture.respond(self.prepare('import_apply'))['awaiting_action']
        h = workspace.authority(self.folder)
        body = workspace.load_request(h, exact)['body']['workspace_apply']
        h.revoke(body['scope_id'], approver='johnathan', reason='SYNTHETIC revoked copy permission')
        with self.assertRaises((ValueError, KeyError)):
            self.fixture.respond(exact)
        self.assertFalse(Path(self.fixture.saved()['import_sandbox']).exists())

    def test_source_hardlinks_do_not_enter_import(self):
        linked = self.source/'linked.js'
        try:
            os.link(self.source/'app.js', linked)
        except OSError:
            self.skipTest('Host does not support creating hard links')
        self.fixture.scan()
        with self.assertRaisesRegex(ValueError, '64 KiB'):
            self.fixture.respond(self.prepare('import_plan'))

    def test_changed_passive_git_head_invalidates_source_inventory(self):
        git = self.source/'.git'; git.mkdir(); (git/'HEAD').write_text('a'*40)
        self.fixture.scan()
        (git/'HEAD').write_text('b'*40)
        with self.assertRaisesRegex(ValueError, 'changed since scanning'):
            self.fixture.respond(self.prepare('import_plan'))

    def test_import_total_limit_includes_packaged_runtime_and_unused_sources(self):
        for name in ('engine.js', 'extra.js', 'more.js', 'last.js'):
            (self.source/name).write_bytes(b' ' * workspace.MAX_READ)
        self.fixture.scan()
        with self.assertRaisesRegex(ValueError, '256 KiB'):
            self.fixture.respond(self.prepare('import_plan'))
        self.assertFalse(Path(self.fixture.saved()['import_sandbox']).exists())
