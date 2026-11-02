"""Human-selected project destinations; session records stay in the harness."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from .recovery import atomic_json, exclusive, read_json


def checked_path(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2048 or any(ord(c) < 32 for c in value):
        raise ValueError('Enter an absolute folder path')
    path = Path(value.strip()).expanduser()
    if not path.is_absolute():
        raise ValueError('Choose an absolute folder path')
    if path.resolve() != path or path.is_symlink():
        raise ValueError('Choose a direct folder path without symbolic links or junctions')
    return path


def settings_path(root):
    return Path(root).resolve() / '.harness/ui/project-settings.json'


def default_parent(root):
    path = settings_path(root)
    return read_json(path)['parent'] if path.exists() else str(Path(root).resolve() / '.harness/projects')


def parent_folder(root, value=None):
    path = checked_path(default_parent(root) if value is None else value)
    managed = Path(root).resolve() / '.harness/projects'
    if path != managed and not path.is_dir():
        raise ValueError('Choose an existing projects folder, or create it in the folder picker')
    if path.exists() and not path.is_dir():
        raise ValueError('The project location must be a folder')
    return path


def assign(root, folder, name, parent):
    """Bind a fresh session before any proposals; never retarget reviewed writes."""
    folder = Path(folder)
    path = folder / 'project-location.json'
    if path.exists() or (folder / 'build-authority').exists():
        raise ValueError('This session already has a project location')
    base = parent_folder(root, parent)
    managed = Path(root).resolve() / '.harness/projects'
    slug = re.sub('[^a-z0-9]+', '-', name.lower()).strip('-')[:48] or 'project'
    destination = base / (folder.name if base == managed else slug + '-' + folder.name)
    checked_path(str(destination))
    if destination.exists():
        raise ValueError('That project folder already exists; choose a new location')
    atomic_json(path, dict(version=1, session_id=folder.name, path=str(destination), parent=str(base)))
    return destination


def remember(root, parent):
    path = settings_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with exclusive(path.with_suffix('.lock')):
        atomic_json(path, dict(version=1, parent=str(parent)))


def destination(root, folder):
    folder = Path(folder)
    if not re.fullmatch('[0-9a-f]{24}', folder.name):
        raise ValueError('A saved session is required for building')
    binding = folder / 'project-location.json'
    if binding.exists():
        data = read_json(binding)
        if data.get('version') != 1 or data.get('session_id') != folder.name:
            raise ValueError('Project location record changed')
        path = checked_path(data['path'])
        base = checked_path(data['parent'])
        if path.parent != base or not path.name.endswith(folder.name):
            raise ValueError('Project location escaped its dedicated session folder')
        return path
    return checked_path(str(Path(root).resolve() / '.harness/projects' / folder.name))


def pick(parent):
    """Run a native dialog in its own UI process, outside request-handler threads."""
    try:
        result = subprocess.run([sys.executable, '-m', 'ember_harness.project_locations', '--pick', str(parent)],
            capture_output=True, text=True, timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode:
            raise ValueError('Folder picker unavailable. Enter the folder path instead.')
        return json.loads(result.stdout)['path']
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        raise ValueError('Folder picker unavailable. Enter the folder path instead.') from error


def native_picker(parent):
    import tkinter as tk
    from tkinter import filedialog
    window = tk.Tk()
    window.withdraw()
    window.attributes('-topmost', True)
    try:
        return filedialog.askdirectory(parent=window, title='Choose where Ember saves projects',
                                       initialdir=parent if Path(parent).is_dir() else str(Path.home()), mustexist=True) or None
    finally:
        window.destroy()


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '--pick':
        raise SystemExit('Use --pick with an initial folder')
    print(json.dumps(dict(path=native_picker(sys.argv[2]))))
