"""Exercise the real Windows batch file with an isolated, non-model application."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt', 'Windows desktop launcher')
class DesktopLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=scratch, prefix='desktop launcher ')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.folder = Path(cls.temp.name)
        cls.environment = cls.folder / 'active environment'
        subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(cls.environment)], check=True,
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def launch(self, name, *, project_environment=False, active_environment=False, bootstrap=False, no_browser=False):
        root = self.folder / name
        root.mkdir()
        shutil.copyfile(ROOT / 'Start Ember.cmd', root / 'Start Ember.cmd')
        package = root / 'ember_harness'
        package.mkdir()
        (package / '__init__.py').touch()
        # Dependency discovery must work without installing anything in these fake environments.
        (root / 'jsonschema.py').touch()
        (root / 'PIL.py').touch()
        (package / 'local_ui.py').write_text(
            'import json, sys\nprint("LAUNCH_PROBE="+json.dumps(dict(prefix=sys.prefix,args=sys.argv[1:])))\n'
            'raise SystemExit(7)\n', encoding='utf-8')
        if project_environment:
            subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(root / '.venv')],
                           check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if bootstrap:
            (root / 'Setup Ember.cmd').write_text(
                '@echo off\n"' + sys.executable + '" -m venv --without-pip "%~dp0.venv"\nexit /b %errorlevel%\n',
                encoding='utf-8')
        env = dict(os.environ, EMBER_NO_PAUSE='1')
        env.pop('EMBER_NO_BROWSER', None)
        if no_browser:
            env['EMBER_NO_BROWSER'] = '1'
        env.pop('VIRTUAL_ENV', None)
        if active_environment:
            env['VIRTUAL_ENV'] = str(self.environment)
        result = subprocess.run('cmd.exe /d /c call "' + str(root / 'Start Ember.cmd') + '" --port 0',
            cwd=self.folder, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertIn('Launch failed.', result.stdout)
        probe = next(line for line in result.stdout.splitlines() if line.startswith('LAUNCH_PROBE='))
        data = json.loads(probe.split('=', 1)[1])
        self.assertEqual(data['args'], ([] if no_browser else ['--open-browser']) + ['--port', '0'])
        return root, Path(data['prefix']).resolve()

    def test_project_environment_takes_precedence_over_active_environment(self):
        root, prefix = self.launch('project copy', project_environment=True, active_environment=True)
        self.assertEqual(prefix, (root / '.venv').resolve())

    def test_activated_environment_works_from_another_directory(self):
        _, prefix = self.launch('activated copy', active_environment=True)
        self.assertEqual(prefix, self.environment.resolve())

    def test_global_launcher_fallback_preserves_failure_and_arguments(self):
        if not shutil.which('py'):
            self.skipTest('Python launcher unavailable')
        _, prefix = self.launch('global copy')
        self.assertNotEqual(prefix, self.environment.resolve())

    def test_first_launch_runs_setup_then_uses_project_environment(self):
        root, prefix = self.launch('first launch', bootstrap=True)
        self.assertEqual(prefix, (root / '.venv').resolve())

    def test_scripted_launch_can_keep_browser_closed(self):
        self.launch('no browser', project_environment=True, no_browser=True)

    def test_failed_setup_stops_before_launch(self):
        root = self.folder / 'failed setup'
        root.mkdir()
        shutil.copyfile(ROOT / 'Start Ember.cmd', root / 'Start Ember.cmd')
        (root / 'Setup Ember.cmd').write_text('@echo off\nexit /b 23\n', encoding='utf-8')
        env = dict(os.environ, EMBER_NO_PAUSE='1')
        env.pop('VIRTUAL_ENV', None)
        result = subprocess.run('cmd.exe /d /c call "' + str(root / 'Start Ember.cmd') + '"',
            env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode, 23, result.stdout + result.stderr)
        self.assertIn('Launch failed.', result.stdout)
