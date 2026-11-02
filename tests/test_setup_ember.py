"""Installer behavior without network access, AI calls or global package changes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import setup_ember

ROOT = Path(__file__).resolve().parents[1]


class SetupTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=scratch, prefix='setup with spaces ')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'pyproject.toml').touch()
        (self.root / 'examples').mkdir()
        (self.root / 'examples/product_demo.py').touch()

    def installed_python(self):
        python = setup_ember.environment_python(self.root)
        python.parent.mkdir(parents=True)
        python.touch()
        return python

    def test_fresh_setup_is_private_and_preserves_saved_data(self):
        saved = self.root / '.harness/muse-credits.json'
        saved.parent.mkdir()
        saved.write_text('existing ledger must remain unchanged', encoding='utf-8')
        wheels = self.root / 'local wheels'
        wheels.mkdir()
        with patch.object(setup_ember, 'run') as run, patch.object(setup_ember, 'check_install') as check:
            setup_ember.install(self.root, wheelhouse=wheels)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0][-3:], ['-m', 'venv', self.root / '.venv'])
        self.assertEqual(commands[2], [setup_ember.environment_python(self.root), '-m', 'pip', 'install',
                                      '--no-index', '--find-links', str(wheels), '-e', self.root])
        self.assertEqual(saved.read_text(encoding='utf-8'), 'existing ledger must remain unchanged')
        check.assert_called_once_with(self.root)

    def test_repeat_setup_reuses_environment(self):
        self.installed_python()
        with patch.object(setup_ember, 'run') as run, patch.object(setup_ember, 'check_install'):
            setup_ember.install(self.root)
        self.assertFalse(any('venv' in call.args[0] for call in run.call_args_list))
        self.assertEqual(run.call_args_list[1].args[0][-2:], ['-e', self.root])

    def test_incomplete_environment_is_not_overwritten(self):
        (self.root / '.venv').mkdir()
        marker = self.root / '.venv/keep.txt'
        marker.write_text('keep', encoding='utf-8')
        with patch.object(setup_ember, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                setup_ember.install(self.root)
        run.assert_not_called()
        self.assertEqual(marker.read_text(), 'keep')

    def test_check_never_installs(self):
        python = self.installed_python()
        with patch.object(setup_ember, 'run') as run:
            setup_ember.check_install(self.root)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[1], [python, '-m', 'pip', 'check'])
        self.assertTrue(all(command[0] == python for command in commands))
        self.assertFalse(any('install' in command for command in commands))

    def test_install_failure_is_not_reported_as_success(self):
        with patch.object(setup_ember, 'ROOT', self.root), patch.object(setup_ember, 'run',
                side_effect=subprocess.CalledProcessError(9, ['synthetic failed install'])), \
                patch.object(setup_ember, 'check_install') as check:
            self.assertEqual(setup_ember.main([]), 1)
        check.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Windows optional browser setup')
    def test_browser_setup_uses_local_module_and_checks_discovery(self):
        self.installed_python()
        with patch.object(setup_ember, 'run') as run, patch.object(setup_ember, 'check_install'), \
                patch.object(setup_ember.shutil, 'which', side_effect=lambda name: 'C:/Node/' + name):
            setup_ember.install(self.root, browser=True)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn(["C:/Node/npm.cmd", 'install', '--prefix', self.root / '.harness/browser-tools', 'playwright'], commands)
        self.assertIn(['C:/Node/node', self.root / '.harness/browser-tools/node_modules/playwright/cli.js',
                       'install', 'chromium'], commands)
        self.assertIn('discover', commands[-1][-1])


if __name__ == '__main__':
    unittest.main()
