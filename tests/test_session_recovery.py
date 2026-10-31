"""Crash real workers at review checkpoints; all responses are synthetic tests."""
import json
from pathlib import Path
import shutil
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import ember_harness
from ember_harness.local_ui import App
from ember_harness.recovery import Recovery, atomic_json, decode, encode, exclusive, worker_active

ROOT = Path(__file__).resolve().parents[1]


class SessionRecoveryTests(unittest.TestCase):
    def test_worker_finishing_between_state_read_and_lease_check_is_terminal(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            folder = Path(directory)
            app = App(ROOT)
            running = dict(status='running', exit_code=None, pid=123)
            for status, code in [('completed', 0), ('stopped', 1)]:
                with self.subTest(status=status):
                    atomic_json(folder / 'worker.json', running)
                    terminal = dict(status=status, exit_code=code, pid=123)
                    def finish(_):
                        atomic_json(folder / 'worker.json', terminal)
                        return False
                    with patch('ember_harness.local_ui.worker_active', side_effect=finish):
                        self.assertEqual(app.worker_state(folder), terminal)
            atomic_json(folder / 'worker.json', running)
            with patch('ember_harness.local_ui.worker_active', return_value=False):
                self.assertEqual(app.worker_state(folder)['status'], 'interrupted')

    def test_changed_workspace_and_uncheckpointed_actions_block_recovery(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            session = root / 'session'
            session.mkdir()
            workspace = root / '.harness/demos/recovery-fixture'
            workspace.mkdir(parents=True)
            source = workspace / 'source.txt'
            source.write_text('original', encoding='utf-8')
            journal = Recovery(session, root)
            journal.run('setup', SimpleNamespace(folder=workspace), lambda state, **kw: None)
            source.write_text('modified', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'files changed'):
                Recovery(session, root)
            source.write_text('original', encoding='utf-8')
            from ember_harness import Harness
            h = Harness(workspace / 'sample/control')
            with h._lock():
                h._append('unexpected_worker_action')
            with self.assertRaisesRegex(ValueError, 'Uncheckpointed'):
                Recovery(session, root)

    def test_killed_workers_resume_all_seven_reviews_without_repeating_approvals(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            shutil.copytree(ROOT / 'examples', root / 'examples', ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(Path(ember_harness.__file__).parent, root / 'ember_harness',
                            ignore=shutil.ignore_patterns('__pycache__'))
            # Crash once immediately after the durable local commit checkpoint.
            product_source = root / 'examples/product_demo.py'
            source = product_source.read_text(encoding='utf-8')
            source = source.replace("        recovery = Recovery(args.checkpoint_dir, ROOT) if args.checkpoint_dir else None", """        recovery = Recovery(args.checkpoint_dir, ROOT) if args.checkpoint_dir else None
        original_run = Recovery.run
        def crash_after_commit(self, name, *values, **options):
            result = original_run(self, name, *values, **options)
            marker = self.path.parent / 'test-crash-after-commit'
            if name == 'fix.commit' and marker.exists():
                marker.unlink()
                import os
                os._exit(91)
            return result
        Recovery.run = crash_after_commit""")
            product_source.write_text(source, encoding='utf-8')
            app = App(root)
            workers = []
            try:
                app.start('Crash recovery test')
                session_id = app.session['id']
                workers.append(app.process)
                (app.sessions_dir / session_id / 'test-crash-after-commit').touch()
                seen = set()
                recovered_commit = False
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    state = app.snapshot()
                    if state['status'] == 'interrupted' and len(seen) == 7 and not recovered_commit:
                        app.process.wait(timeout=15)
                        app = App(root)
                        app.resume(session_id)
                        app.recover()
                        workers.append(app.process)
                        recovered_commit = True
                        continue
                    if state['status'] != 'running':
                        break
                    pending = [r for r in state['requests'] if not r['decision']]
                    if not pending:
                        time.sleep(.1)
                        continue
                    request = pending[0]
                    if request['ref'] not in state['log'] or (Path(state['store']) / '.writer.lock').exists():
                        time.sleep(.05)
                        continue
                    self.assertNotIn(request['ref'], seen)
                    before = state['audit']
                    app.process.kill()
                    app.process.wait(timeout=15)
                    app = App(root)  # Fresh UI and fresh worker, like reopening after a reboot.
                    opened = app.resume(session_id)
                    self.assertEqual(opened['status'], 'interrupted')
                    self.assertTrue(opened['recovery_available'])
                    restored = app.recover()
                    workers.append(app.process)
                    self.assertEqual(restored['status'], 'running', restored['log'])
                    self.assertEqual(restored['audit'], before)
                    self.assertEqual(restored['requests'][-1]['ref'], request['ref'])
                    # Duplicate recovery requests attach to the same OS-held worker.
                    current_pid = app.process.pid
                    app.recover()
                    self.assertEqual(app.process.pid, current_pid)
                    choice = request['payload']['body']['options'][0]['choice'] if request['payload']['kind'] == 'choice' else 'approve'
                    app.respond(request['ref'], choice, 'SYNTHETIC recovery test response')
                    seen.add(request['ref'])
                self.assertEqual(state['status'], 'completed', state['log'])
                self.assertEqual(len(seen), 7)
                self.assertTrue(recovered_commit)
                from ember_harness.contract_lock import git
                self.assertEqual(git(Path(state['store']).parent, 'rev-list', '--count', 'HEAD').decode().strip(), '2')
                self.assertEqual(len([r for r in state['requests'] if r['decision']]), 7)
                self.assertTrue(app.verify()['passed'])
                journal = json.loads((app.sessions_dir / session_id / 'recovery.json').read_bytes())['payload']
                self.assertEqual(journal['steps']['fix.commit']['status'], 'complete')
            finally:
                for process in workers:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=15)

    def test_journal_integrity_unknown_types_and_inflight_steps_fail_closed(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            path = Path(folder)
            journal = Recovery(path, ROOT)
            state = SimpleNamespace(value=1)
            calls = []

            def finish(state, **kwargs):
                calls.append(1)
                state.value += 1

            journal.run('finished', state, finish)
            reopened = Recovery(path, ROOT)
            restored = reopened.run('finished', SimpleNamespace(value=99), finish)
            self.assertEqual(restored.value, 2)
            self.assertEqual(calls, [1])
            reopened.data['steps']['uncertain_write'] = dict(status='running', retry=False)
            reopened.save()
            with self.assertRaisesRegex(ValueError, 'needs inspection'):
                Recovery(path, ROOT).check_ready()
            envelope = json.loads(reopened.path.read_bytes())
            envelope['payload']['version'] = 2
            atomic_json(reopened.path, envelope)
            with self.assertRaisesRegex(ValueError, 'damaged|unsupported'):
                Recovery(path, ROOT)
            with self.assertRaises(ValueError):
                decode({'type': 'python_code', 'value': 'anything'})
            self.assertEqual(decode(encode((Path(folder), b'bytes'))), (Path(folder), b'bytes'))
            with exclusive(path / 'worker.lock'):
                self.assertTrue(worker_active(path))
            self.assertFalse(worker_active(path))


if __name__ == '__main__':
    unittest.main()
