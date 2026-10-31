"""Versioned JSON checkpoints for the local sample workflow; no executable snapshots."""
from contextlib import contextmanager
from datetime import datetime
from hashlib import sha256
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

from .core import Harness, canonical, content_hash, digest


@contextmanager
def exclusive(path):
    """An OS-held lock is released on process death, including after a reboot."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError('Session worker is already active') from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def worker_active(folder):
    try:
        with exclusive(Path(folder) / 'worker.lock'):
            return False
    except ValueError:
        return True


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    with temp.open('wb') as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())
    # Windows readers can briefly hold a sharing lock while polling state.
    for attempt in range(100):
        try:
            os.replace(temp, path)
            break
        except PermissionError:
            if attempt == 99:
                raise
            time.sleep(.01)


def read_json(path):
    """Tolerate Windows sharing locks during an atomic state replacement."""
    for attempt in range(100):
        try:
            return json.loads(Path(path).read_bytes())
        except PermissionError:
            if attempt == 99:
                raise
            time.sleep(.01)


def encode(value):
    if value is None or type(value) in (str, int, bool, float):
        return value
    if isinstance(value, Path):
        return {'type': 'path', 'value': str(value)}
    if isinstance(value, datetime):
        return {'type': 'datetime', 'value': value.isoformat()}
    if isinstance(value, bytes):
        return {'type': 'bytes', 'value': value.hex()}
    if isinstance(value, (list, tuple)):
        return {'type': 'tuple' if isinstance(value, tuple) else 'list', 'value': [encode(v) for v in value]}
    if isinstance(value, dict):
        return {'type': 'dict', 'value': {k: encode(v) for k, v in value.items()}}
    if isinstance(value, SimpleNamespace):
        return {'type': 'state', 'value': encode(vars(value))}
    from .assets import Assets
    from .intake import Intake
    from .rounds import Rounds
    from .local_agent import LocalAgent
    from .owner_review import OwnerReview
    if isinstance(value, Harness):
        return {'type': 'harness', 'value': str(value.root)}
    if isinstance(value, (Assets, Rounds)):
        return {'type': type(value).__name__, 'value': encode(value.h)}
    if isinstance(value, Intake):
        return {'type': 'intake', 'value': [encode(value.h), str(value.root)]}
    if isinstance(value, LocalAgent):
        return {'type': 'local_agent', 'value': [str(value.binary), value.model, value.binary_hash]}
    if type(value) is OwnerReview:
        return {'type': 'owner', 'value': None}
    raise ValueError('Unsupported checkpoint value: ' + type(value).__name__)


def decode(value):
    if not isinstance(value, dict):
        return value
    kind, data = value['type'], value['value']
    if kind == 'path':
        return Path(data)
    if kind == 'datetime':
        return datetime.fromisoformat(data)
    if kind == 'bytes':
        return bytes.fromhex(data)
    if kind in ('list', 'tuple'):
        items = [decode(v) for v in data]
        return tuple(items) if kind == 'tuple' else items
    if kind == 'dict':
        return {k: decode(v) for k, v in data.items()}
    if kind == 'state':
        return SimpleNamespace(**decode(data))
    if kind == 'harness':
        return Harness(data)
    if kind == 'Assets':
        from .assets import Assets
        return Assets(decode(data))
    if kind == 'Rounds':
        from .rounds import Rounds
        return Rounds(decode(data))
    if kind == 'intake':
        from .intake import Intake
        return Intake(decode(data[0]), data[1])
    if kind == 'owner':
        from .owner_review import OwnerReview
        return OwnerReview()
    if kind == 'local_agent':
        from .local_agent import LocalAgent
        agent = LocalAgent(data[0], data[1])
        if agent.binary_hash != data[2]:
            raise ValueError('Local agent executable changed since checkpoint')
        return agent
    raise ValueError('Unknown checkpoint type')


class Recovery:
    def __init__(self, folder, root):
        self.path = Path(folder) / 'recovery.json'
        self.root = Path(root).resolve()
        sources = {str(p.relative_to(self.root)): sha256(p.read_bytes()).hexdigest()
                   for area in ('ember_harness', 'examples') for p in (self.root / area).rglob('*.py')}
        if self.path.exists():
            envelope = read_json(self.path)
            self.data = envelope['payload']
            if digest(self.data) != envelope['sha256'] or self.data['version'] != 1:
                raise ValueError('Recovery journal is damaged or unsupported')
            if self.data['sources'] != sources:
                raise ValueError('Workflow code changed since checkpoint; recovery needs inspection')
            self.validate()
        else:
            self.data = dict(version=1, sources=sources, steps={}, workspace=None, files={}, audit=None)
            self.save()

    def save(self):
        atomic_json(self.path, dict(payload=self.data, sha256=digest(self.data)))

    def check_ready(self):
        for name, record in self.data['steps'].items():
            if record['status'] == 'running' and not record.get('retry'):
                raise ValueError('Interrupted step needs inspection before retry: ' + name)

    def files(self):
        folder = self.data['workspace']
        if not folder:
            return {}
        root = Path(folder)
        return {p.relative_to(root).as_posix(): sha256(p.read_bytes()).hexdigest()
                for p in root.rglob('*') if p.is_file() and not p.is_symlink()
                and '__pycache__' not in p.parts and not p.is_relative_to(root / 'sample/control')}

    def validate(self):
        folder = self.data['workspace']
        if not folder:
            return
        if not Path(folder).resolve().is_relative_to(self.root / '.harness/demos'):
            raise ValueError('Checkpoint workspace outside local demo directory')
        if self.files() != self.data['files']:
            raise ValueError('Workflow files changed after checkpoint; recovery needs inspection')
        h = Harness(Path(folder) / 'sample/control')
        for _ in range(100):
            if not (h.root / '.writer.lock').exists():
                break
            time.sleep(.01)
        if (h.root / '.writer.lock').exists():
            raise ValueError('Interrupted audit write requires inspection')
        with h._lock():
            entries = h._entries()
            anchor = self.data.get('audit')
            if anchor and (len(entries) < anchor['entries'] or
                    (entries[anchor['entries'] - 1]['entry_hash'] if anchor['entries'] else '0' * 64) != anchor['head']):
                raise ValueError('Audit no longer matches checkpoint')
            allowed_tail = {'owner_request', 'owner_decision', 'approval'}
            choice = self.data['steps'].get('product.concept_choice', {})
            if choice.get('status') == 'running':
                allowed_tail.update(('decision', 'concept_selection'))
            if anchor and any(e['kind'] not in allowed_tail for e in entries[anchor['entries']:]):
                raise ValueError('Uncheckpointed workflow actions require inspection')
            from .owner_review import validate_history
            validate_history(h, entries)
            for event in entries:
                if event['kind'] == 'approval' and event.get('scope') == 'contract':
                    contract = json.loads(h._path(event['contract_id'], event['contract_version']).read_bytes())
                    if (contract.get('status') not in ('approved', 'superseded') or
                            contract.get('id') != event['contract_id'] or contract.get('version') != event['contract_version'] or
                            content_hash(contract) != event['content_hash'] or contract.get('content_hash') != event['content_hash']):
                        raise ValueError('Approved contract differs from checkpoint history')

    def run(self, name, state, function, *, retry=False, **kwargs):
        record = self.data['steps'].get(name)
        if record and record['status'] == 'complete':
            return decode(record['state'])
        if record and not retry:
            raise ValueError('Interrupted step needs inspection before retry: ' + name)
        self.data['steps'][name] = dict(status='running', retry=retry)
        self.data['current_step'] = name
        self.save()
        function(state, recovery=self, **kwargs)
        self.data['steps'][name] = dict(status='complete', state=encode(state))
        workspace = getattr(state, 'folder', None)
        if workspace:
            self.data['workspace'] = str(workspace)
        self.data['files'] = self.files()
        if self.data['workspace']:
            self.data['audit'] = Harness(Path(self.data['workspace']) / 'sample/control').audit_verify()
        self.save()
        return state


def step(recovery, name, state, function, *, retry=False, **kwargs):
    if recovery:
        return recovery.run(name, state, function, retry=retry, **kwargs)
    function(state, recovery=None, **kwargs)
    return state
