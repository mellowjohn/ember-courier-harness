"""The release gate must reject failures, empty discovery and timeouts."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
import io
import json

from tools.release_check import run_check


class ReleaseCheckTests(unittest.TestCase):
    def test_report_retains_live_mode_after_command_loop(self):
        from tools import release_check
        with tempfile.TemporaryDirectory() as directory:
            def checked(name, args, output, **kwargs):
                if name == 'product':
                    self.assertIn('--local-agent-binary', args)
                return dict(name=name, passed=True, seconds=0, log=str(output / (name + '.log')))
            with patch.object(release_check, 'ROOT', Path(directory)), patch.object(release_check, 'source_manifest', return_value={}), patch.object(release_check, 'run_check', side_effect=checked), redirect_stdout(io.StringIO()):
                self.assertEqual(release_check.main(['--local-agent-binary', 'fixture-only.exe']), 0)
            report = json.loads(next(Path(directory).rglob('report.json')).read_text())
            self.assertTrue(report['passed'])
            self.assertIn('uses real local model inference', report['coverage'])

    def test_nonzero_and_empty_suite_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('tools.release_check.subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
                self.assertFalse(run_check('failed', [], Path(directory))['passed'])
            with patch('tools.release_check.subprocess.run', return_value=subprocess.CompletedProcess([], 0)):
                self.assertFalse(run_check('empty', [], Path(directory), require_tests=True)['passed'])

    def test_timeout_fails_and_retains_log(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('tools.release_check.subprocess.run', side_effect=subprocess.TimeoutExpired([], 1)):
                result = run_check('timeout', [], Path(directory))
            self.assertFalse(result['passed'])
            self.assertEqual(result['reason'], 'timeout')
            self.assertTrue(Path(result['log']).is_file())

    def test_completed_tests_pass_with_assertions_enabled(self):
        def fake_run(args, **kwargs):
            self.assertNotIn('PYTHONOPTIMIZE', kwargs['env'])
            kwargs['stdout'].write('Ran 3 tests in 0.1s\nOK\n')
            return subprocess.CompletedProcess(args, 0)
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict('os.environ', {'PYTHONOPTIMIZE': '1'}):
                with patch('tools.release_check.subprocess.run', side_effect=fake_run):
                    self.assertTrue(run_check('pass', [], Path(directory), require_tests=True)['passed'])
