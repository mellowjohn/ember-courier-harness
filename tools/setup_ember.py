"""Install Ember into a private .venv, or check an existing installation.

Uses only the Python standard library so it works before dependencies are installed.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def environment_python(root):
    return root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def run(command, root):
    subprocess.run(list(map(str, command)), cwd=root, check=True)


def check_install(root):
    python = environment_python(root)
    if not python.is_file():
        raise ValueError('Ember is not installed in .venv. Run setup without --check first.')
    run([python, '-c', 'import sys; assert sys.version_info >= (3, 12), "Python 3.12+ is required"'], root)
    run([python, '-m', 'pip', 'check'], root)
    # Import the actual app and packaged resources, without creating sessions or calling Muse.
    run([python, '-c',
         'from ember_harness.local_ui import App, server; '
         'from importlib.resources import files; '
         'assert files("ember_harness").joinpath("ui.html").is_file(); '
         'print("Ember app: ready")'], root)
    run([python, '-c',
         'from ember_harness.muse_chat import installed_binary; '
         'print("Muse CLI: detected (sign-in and credits not checked)" if installed_binary() '
         'else "Muse CLI: not detected; install and sign in to Muse Code for AI chat")'], root)
    # Optional tools must not turn a working basic installation into a failure.
    run([python, '-c',
         'from ember_harness.polish_runtime import discover\n'
         'try:\n discover(".", fingerprints=False); print("Browser checks: tooling detected")\n'
         'except (ValueError, OSError):\n print("Browser checks: not configured; see docs/INSTALL.md")'], root)


def install(root, *, browser=False, wheelhouse=None):
    if not (root / 'pyproject.toml').is_file() or not (root / 'examples/product_demo.py').is_file():
        raise ValueError('Keep tools/setup_ember.py inside the fully extracted Ember repository.')
    python = environment_python(root)
    if not python.is_file():
        if (root / '.venv').exists():
            raise ValueError('The existing .venv is incomplete. Rename it, then rerun setup. Your .harness data stays in place.')
        print('Step 1/3: Creating Ember\'s private Python environment...', flush=True)
        run([sys.executable, '-m', 'venv', root / '.venv'], root)
    else:
        print('Step 1/3: Reusing Ember\'s private Python environment.', flush=True)
    run([python, '-c', 'import sys; assert sys.version_info >= (3, 12), "Rename .venv and rerun setup with Python 3.12+"'], root)
    print('Step 2/3: Installing Ember and its dependencies...', flush=True)
    options = ['--no-index', '--find-links', str(wheelhouse)] if wheelhouse else []
    run([python, '-m', 'pip', 'install', *options, '-e', root], root)
    if browser:
        if os.name != 'nt':
            raise ValueError('The full browser/Muse workflow currently targets Windows. Basic Ember installation is complete.')
        npm = shutil.which('npm.cmd') or shutil.which('npm')
        if not npm or not shutil.which('node'):
            raise ValueError('Install Node.js LTS from https://nodejs.org/en/download, reopen your terminal, then rerun setup with --browser.')
        print('Installing optional Playwright and Chromium (this can take a few minutes)...', flush=True)
        browser_tools = root / '.harness/browser-tools'
        run([npm, 'install', '--prefix', browser_tools, 'playwright'], root)
        cli = browser_tools / 'node_modules/playwright/cli.js'
        run([shutil.which('node'), cli, 'install', 'chromium'], root)
    print('Step 3/3: Checking the installation...', flush=True)
    check_install(root)
    if browser:
        run([python, '-c', 'from ember_harness.polish_runtime import discover; discover(".", fingerprints=False)'], root)
    print('\nSetup complete. Double-click Start Ember.cmd to open Ember.' if os.name == 'nt' else
          '\nSetup complete. Run .venv/bin/python -m ember_harness.local_ui from this folder.', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='check the private installation without installing or calling Muse')
    mode.add_argument('--browser', action='store_true', help='also install optional Playwright and Chromium (Windows; requires Node.js)')
    parser.add_argument('--wheelhouse', type=Path, help='install Python dependencies from local wheels without contacting a package index')
    args = parser.parse_args(argv)
    try:
        if sys.version_info < (3, 12):
            raise ValueError('Python 3.12 or newer is required. See https://www.python.org/downloads/')
        if args.wheelhouse and (not args.wheelhouse.is_dir() or args.browser):
            raise ValueError('--wheelhouse needs an existing directory and cannot be combined with --browser (which downloads tooling).')
        if args.check:
            check_install(ROOT)
        else:
            install(ROOT, browser=args.browser, wheelhouse=args.wheelhouse.resolve() if args.wheelhouse else None)
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('\nSetup could not finish: ' + str(error), file=sys.stderr, flush=True)
        print('See the message above and docs/INSTALL.md. You can rerun setup after fixing the issue.', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\nSetup cancelled. Rerun setup to continue.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
