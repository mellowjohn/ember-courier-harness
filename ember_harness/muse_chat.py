"""Muse-only conversation transport and a shared, crash-safe free-credit ledger."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from .recovery import atomic_json, exclusive, read_json
from .core import digest

MODEL = 'muse-spark-1.3'
BUDGET_MICRO_USD = 150_000_000
# Spark's 1,048,576-token shared context at the higher $4.25/M output
# rate is $4.456448. Reserve $5 before a single model step, with no tools.
# Sources and the rate-verification date are recorded in MODELS_AND_CREDITS.md.
RESERVATION_MICRO_USD = 5_000_000
MAX_CAPTURE = 4 * 1024 * 1024
UNEXPECTED_USAGE = 'Unexpected model calls or retries in saved Muse usage'


def inspected_retry_bound(capture):
    """Bound one historical failed attempt plus its completed Spark response."""
    if (capture.get('capture_sha256') != digest({k: v for k, v in capture.items() if k != 'capture_sha256'}) or
            capture.get('model') != MODEL or capture.get('exit_code') != 0 or
            capture.get('reservation_micro_usd') != RESERVATION_MICRO_USD or not capture.get('response')):
        raise ValueError('A complete unchanged Muse capture is required for inspection')
    usage = [e.get('payload', {}) for e in capture['events'] if e.get('payload_type') == 'run.usage']
    configured = [e.get('payload', {}) for e in capture['events'] if e.get('payload_type') == 'run.model.configured']
    terminal = [e.get('payload', {}) for e in capture['events'] if e.get('payload_type') == 'run.terminal.completed']
    if (len(usage) != 1 or len(configured) != 1 or configured[0].get('model_id') != MODEL or
            configured[0].get('provider_id') != 'meta' or len(terminal) != 1 or terminal[0].get('terminal') != 'completed'):
        raise ValueError('Historical retry cannot be bounded from this capture')
    row = usage[0]
    models = row.get('models', [])
    if (row.get('calls') != 2 or row.get('failed_calls') != 1 or row.get('completed_calls') != 1 or
            row.get('cancelled_calls', 0) != 0 or row.get('children_included', False) or
            len(models) != 1 or models[0].get('model') != MODEL or models[0].get('calls') != 1):
        raise ValueError('Only one failed attempt and one completed pinned-model call can be inspected')
    incoming, outgoing = models[0].get('input_tokens'), models[0].get('output_tokens')
    if any(type(v) is not int or v < 0 for v in (incoming, outgoing)) or incoming + outgoing > 1_048_576:
        raise ValueError('Invalid inspected usage counters')
    known = (5 * incoming + 17 * outgoing + 3) // 4
    failed_bound = (17 * 1_048_576 + 3) // 4
    if known + failed_bound > RESERVATION_MICRO_USD:
        raise ValueError('Historical retry exceeds its reserved budget bound')
    return dict(capture_sha256=capture['capture_sha256'], known_usage_micro_usd=known,
                failed_attempt_bound_micro_usd=failed_bound, total_bound_micro_usd=known + failed_bound,
                disposition='Full reservation retained; failed-attempt usage is uncertain')


def installed_binary():
    folder = Path.home() / 'AppData/Local/Programs/muse'
    version = folder / '.muse-version'
    if version.is_file():
        path = folder / ('muse-bin-' + version.read_text(encoding='utf-8').strip() + '.exe')
        if path.is_file():
            return path
    return None


class CreditLedger:
    def __init__(self, root):
        self.folder = Path(root) / '.harness'
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / 'muse-credits.json'

    def read(self):
        data = read_json(self.path) if self.path.exists() else dict(version=1, limit_micro_usd=BUDGET_MICRO_USD, requests={})
        if data.get('version') != 1 or type(data.get('limit_micro_usd')) is not int or not 0 <= data['limit_micro_usd'] <= BUDGET_MICRO_USD:
            raise ValueError('Invalid Muse credit ledger')
        budgets = data.get('budgets', {})
        if (not isinstance(budgets, dict) or any(not isinstance(key, str) or len(key) != 64 or
                any(c not in '0123456789abcdef' for c in key) or type(value) is not int or
                not RESERVATION_MICRO_USD <= value <= BUDGET_MICRO_USD for key, value in budgets.items())):
            raise ValueError('Invalid run credit ledger')
        for row in data['requests'].values():
            if row.get('status') not in ('reserved', 'settled') or row.get('reserved_micro_usd') != RESERVATION_MICRO_USD:
                raise ValueError('Invalid Muse credit reservation')
            if row['status'] == 'reserved' and 'charged_micro_usd' in row:
                raise ValueError('An uncertain credit reservation cannot report a settled charge')
            if row['status'] == 'settled' and (type(row.get('charged_micro_usd')) is not int or not 0 <= row['charged_micro_usd'] <= RESERVATION_MICRO_USD):
                raise ValueError('Invalid Muse credit settlement')
            if row.get('budget_id') is not None and row['budget_id'] not in budgets:
                raise ValueError('Credit request has no approved run budget')
        for key, limit in budgets.items():
            if sum(row.get('charged_micro_usd', RESERVATION_MICRO_USD) for row in data['requests'].values()
                   if row.get('budget_id') == key) > limit:
                raise ValueError('Run credit ledger exceeds its ceiling')
        return data

    def reserve(self, request_id, *, budget=None):
        with exclusive(self.folder / 'muse-credits.lock'):
            data = self.read()
            if data.get('blocked'):
                raise ValueError('Muse credit ledger requires inspection: ' + data['blocked'])
            if request_id in data['requests']:
                raise ValueError('This Muse request already has a credit reservation; inspect its saved outcome before retrying')
            used = sum(row.get('charged_micro_usd', RESERVATION_MICRO_USD) for row in data['requests'].values())
            if used + RESERVATION_MICRO_USD > min(data['limit_micro_usd'], BUDGET_MICRO_USD):
                raise ValueError('Muse free-credit budget cannot cover another request')
            if budget is not None:
                if (not isinstance(budget, dict) or set(budget) != {'id', 'limit_micro_usd'} or
                        not isinstance(budget['id'], str) or len(budget['id']) != 64 or
                        any(c not in '0123456789abcdef' for c in budget['id']) or
                        type(budget['limit_micro_usd']) is not int or
                        not RESERVATION_MICRO_USD <= budget['limit_micro_usd'] <= BUDGET_MICRO_USD):
                    raise ValueError('Invalid run credit budget')
                budgets = data.setdefault('budgets', {})
                previous = budgets.get(budget['id'])
                if previous is not None and previous != budget['limit_micro_usd']:
                    raise ValueError('An approved run budget cannot be changed')
                local_used = sum(row.get('charged_micro_usd', RESERVATION_MICRO_USD)
                                 for row in data['requests'].values() if row.get('budget_id') == budget['id'])
                if local_used + RESERVATION_MICRO_USD > budget['limit_micro_usd']:
                    raise ValueError('Polish run credit budget cannot cover another request')
                budgets[budget['id']] = budget['limit_micro_usd']
            data['requests'][request_id] = dict(status='reserved', reserved_micro_usd=RESERVATION_MICRO_USD)
            if budget is not None:
                data['requests'][request_id]['budget_id'] = budget['id']
            atomic_json(self.path, data)

    def budget_summary(self, budget_id):
        data = self.read()
        rows = [r for r in data['requests'].values() if r.get('budget_id') == budget_id]
        return dict(estimated_spent_usd=sum(r.get('charged_micro_usd', 0) for r in rows) / 1_000_000,
                    reserved_usd=sum(r['reserved_micro_usd'] for r in rows if r['status'] == 'reserved') / 1_000_000,
                    calls=len(rows))

    def freeze(self, reason):
        with exclusive(self.folder / 'muse-credits.lock'):
            data = self.read()
            data['blocked'] = reason
            atomic_json(self.path, data)

    def retain_inspected_retry(self, capture):
        """Trusted repair only: retain all funds and clear this specific isolated freeze."""
        inspection = inspected_retry_bound(capture)
        request_id = capture.get('ledger_request_id')
        with exclusive(self.folder / 'muse-credits.lock'):
            data = self.read()
            if data.get('blocked') != UNEXPECTED_USAGE:
                raise ValueError('This repair applies only to the unexpected-call inspection freeze')
            unresolved = {key for key, row in data['requests'].items() if row['status'] == 'reserved'}
            if unresolved != {request_id}:
                raise ValueError('Other unresolved reservations require separate inspection')
            row = data['requests'][request_id]
            if row.get('inspection'):
                raise ValueError('Reservation already inspected')
            row['inspection'] = inspection
            data.pop('blocked')
            atomic_json(self.path, data)
        return inspection

    def capture_is_inspected(self, capture):
        row = self.read()['requests'].get(capture.get('ledger_request_id'), {})
        inspection = row.get('inspection')
        if not inspection:
            return False
        try:
            unchanged = inspection == inspected_retry_bound(capture)
        except ValueError:
            unchanged = False
        if row['status'] != 'reserved' or not unchanged:
            self.freeze('Inspected Muse capture changed')
            raise ValueError('Inspected Muse capture changed; its reservation remains held')
        return True

    def summary(self):
        data = self.read()
        spent = sum(r.get('charged_micro_usd', 0) for r in data['requests'].values())
        held = sum(r['reserved_micro_usd'] for r in data['requests'].values() if r['status'] == 'reserved')
        return dict(limit_usd=BUDGET_MICRO_USD / 1_000_000, estimated_spent_usd=spent / 1_000_000,
                    reserved_usd=held / 1_000_000, available_usd=(BUDGET_MICRO_USD - spent - held) / 1_000_000,
                    blocked=data.get('blocked'))

    def settle(self, request_id, input_tokens, output_tokens):
        if any(type(v) is not int or v < 0 for v in (input_tokens, output_tokens)):
            raise ValueError('Valid Muse usage counters required')
        charge = (5 * input_tokens + 17 * output_tokens + 3) // 4
        if input_tokens + output_tokens > 1_048_576 or charge > RESERVATION_MICRO_USD:
            self.freeze('Usage exceeded the one-step context or price bound')
            raise ValueError('Muse usage exceeded the reserved bound; credit inspection required')
        with exclusive(self.folder / 'muse-credits.lock'):
            data = self.read()
            row = data['requests'][request_id]
            row.update(status='settled', charged_micro_usd=charge, input_tokens=input_tokens, output_tokens=output_tokens)
            atomic_json(self.path, data)


def settle_capture(ledger, request_id, capture):
    if ledger.capture_is_inspected(capture):
        return  # A reviewed historical response never releases uncertain-attempt funds.
    usage = [e.get('payload', {}) for e in capture['events'] if e.get('payload_type') == 'run.usage']
    if not usage:
        return  # Unknown cost stays reserved, including after a crash.
    latest = usage[-1]
    models = latest.get('models', [])
    if (latest.get('calls') != 1 or latest.get('failed_calls', 0) or len(models) != 1 or
            models[0].get('calls') != 1 or models[0].get('model') != MODEL):
        ledger.freeze(UNEXPECTED_USAGE)
        raise ValueError('Muse usage needs credit inspection before another request')
    ledger.settle(capture.get('ledger_request_id', request_id), models[0]['input_tokens'], models[0]['output_tokens'])


def run(root, folder, prompt, request_id, *, binary=None, output_schema=None, progress=None, images=None, budget=None, check=None):
    binary = Path(binary) if binary else installed_binary()
    if not binary or not binary.is_file():
        raise ValueError('Muse Code is not installed. Install and sign in to Muse before sending a message.')
    ledger = CreditLedger(root)
    pictures = []
    for value in images or []:
        from PIL import Image
        import io
        raw = Path(value).read_bytes()
        if len(pictures) >= 4 or len(raw) > 4 * 1024 * 1024:
            raise ValueError('At most four bounded PNG screenshots may be attached')
        with Image.open(io.BytesIO(raw)) as picture:
            if picture.format != 'PNG' or picture.width * picture.height > 4_000_000:
                raise ValueError('A bounded PNG screenshot is required')
            picture.verify()
        pictures.append(raw)
    binding = digest(dict(prompt=prompt, schema=output_schema,
                          images=[sha256(raw).hexdigest() for raw in pictures], budget=budget))
    captures = Path(folder) / 'muse-captures'
    captures.mkdir(exist_ok=True)
    capture_path = captures / (request_id + '.json')
    if capture_path.is_file():
        capture = read_json(capture_path)
        if capture.get('capture_sha256') != digest({k: v for k, v in capture.items() if k != 'capture_sha256'}):
            raise ValueError('Saved Muse capture changed; no retry was sent')
        if ((capture.get('request_binding') is not None or pictures or budget is not None) and
                capture.get('request_binding') != binding):
            raise ValueError('Saved Muse request context changed; no retry was sent')
        settle_capture(ledger, request_id, capture)
        if progress:
            progress('cached_reply')
        return capture
    ledger_id = sha256((str(Path(folder).resolve()) + ':' + request_id).encode()).hexdigest()
    ledger.reserve(ledger_id, budget=budget)
    with tempfile.TemporaryDirectory(dir=captures) as scratch:
        scratch = Path(scratch)
        prompt_path = scratch / 'prompt.txt'
        prompt_path.write_text(prompt, encoding='utf-8')
        args = [str(binary), 'exec', '--provider', 'meta', '--model', MODEL,
                '--config', 'provider_retry.max_retries=0',
                '--reasoning-effort', 'low', '--contributor-mode', 'off', '--preset', 'empty',
                '--disable-write', '--disable-shell', '--disable-web-tools', '--disable-reminders',
                '--disable-request-user-input', '--no-foreign-personal-context', '--no-session-log',
                '--max-model-steps', '1', '--json', '--prompt-file', str(prompt_path)]
        if output_schema is not None:
            schema_path = scratch / 'response-schema.json'
            atomic_json(schema_path, output_schema)
            args += ['--output-schema', str(schema_path)]
        for index, raw in enumerate(pictures):
            image_path = scratch / ('screenshot-' + str(index) + '.png')
            image_path.write_bytes(raw)
            args += ['--image', str(image_path)]
        with (scratch / 'stdout.jsonl').open('wb') as output, (scratch / 'stderr.log').open('wb') as errors:
            process = subprocess.Popen(args, cwd=scratch, stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            deadline, offset, pending = time.monotonic() + 180, 0, b''
            phase, response_chars, last_report, reported_phase = 'provider_starting', 0, 0, None
            finished = False
            try:
                while True:
                    if check:
                        check()
                    try:
                        code = process.wait(timeout=.25)
                        finished = True
                    except subprocess.TimeoutExpired:
                        pass
                    path = scratch / 'stdout.jsonl'
                    if path.stat().st_size > MAX_CAPTURE:
                        raise ValueError('Muse response exceeded the capture limit; reservation remains held')
                    with path.open('rb') as live:
                        live.seek(offset)
                        chunk = live.read(MAX_CAPTURE + 1)
                    offset += len(chunk)
                    lines = (pending + chunk).split(b'\n')
                    pending = lines.pop()
                    if finished and pending:
                        lines.append(pending)
                        pending = b''
                    for line in lines:
                        try:
                            event = json.loads(line)
                        except (ValueError, UnicodeDecodeError):
                            continue  # Final capture parsing remains strict.
                        kind = event.get('payload_type')
                        if kind == 'run.lifecycle.started':
                            phase = 'muse_working'
                        elif kind == 'run.output.delta':
                            value = event.get('payload', {}).get('text')
                            if isinstance(value, str):
                                response_chars += len(value)
                                phase = 'receiving'
                        elif kind == 'run.terminal.completed':
                            phase = 'provider_finished'
                    if progress and (phase != reported_phase or chunk and time.monotonic() - last_report >= 1):
                        progress(phase, response_chars=response_chars)
                        last_report, reported_phase = time.monotonic(), phase
                    if finished:
                        break
                    if time.monotonic() >= deadline:
                        raise ValueError('Muse reply timed out. Its credit reservation remains held; no automatic retry was sent.')
            finally:
                if not finished:
                    process.kill()
                    process.wait(timeout=10)
        if (scratch / 'stdout.jsonl').stat().st_size > MAX_CAPTURE:
            raise ValueError('Muse response exceeded the capture limit; reservation remains held')
        raw = (scratch / 'stdout.jsonl').read_bytes()
        events = [json.loads(line) for line in raw.splitlines() if line.strip()]
        terminal = [e.get('payload', {}) for e in events if e.get('payload_type') == 'run.terminal.completed']
        capture = dict(model=MODEL, binary_sha256=sha256(binary.read_bytes()).hexdigest(), events=events,
                       exit_code=code, response=None, ledger_request_id=ledger_id,
                       reservation_micro_usd=RESERVATION_MICRO_USD, request_binding=binding)
        if len(terminal) == 1 and terminal[0].get('terminal') == 'completed':
            capture['response'] = terminal[0].get('text')
        capture['capture_sha256'] = digest(capture)
        atomic_json(capture_path, capture)
        settle_capture(ledger, ledger_id, capture)
        if code != 0 or not isinstance(capture['response'], str) or not capture['response'].strip():
            raise ValueError('Muse did not complete a reply. Saved diagnostics and credit reservation were retained.')
        return capture
