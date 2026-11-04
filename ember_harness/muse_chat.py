"""Muse-only conversation transport and a shared, crash-safe free-credit ledger."""
from hashlib import sha256
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from .recovery import atomic_json, exclusive, read_json
from .core import digest
from . import muse_settings
from jsonschema import Draft202012Validator, ValidationError
from jsonschema.exceptions import best_match

MODEL = 'muse-spark-1.3'
BUDGET_MICRO_USD = 150_000_000
# Spark's 1,048,576-token shared context at the higher $4.25/M output
# rate is $4.456448. Reserve $5 before a single model step, with no tools.
# Sources and the rate-verification date are recorded in MODELS_AND_CREDITS.md.
RESERVATION_MICRO_USD = 5_000_000
IMAGE_MODEL = 'muse-image-1.0'
IMAGE_MICRO_USD = 10_000  # One returned image; official rate verified November 1, 2026.
MAX_CAPTURE = 4 * 1024 * 1024
MAX_SCHEMA_DEPTH = 10
UNEXPECTED_USAGE = 'Unexpected model calls or retries in saved Muse usage'

# These are maximum call durations, never target durations or quality scores.
EXECUTION_PROFILES = {
    'conversation': dict(label='Conversation', reasoning_effort='medium', timeout_seconds=300),
    'build': dict(label='Implementation', reasoning_effort='high', timeout_seconds=900),
    'deep': dict(label='Extended investigation and implementation', reasoning_effort='high', timeout_seconds=1800),
    'verify': dict(label='Independent verification', reasoning_effort='high', timeout_seconds=900),
}


def execution_policy(workload, *, source_bytes=0, compound=False, repair=False):
    """Host-selected effort, pinned by callers before a request or run starts."""
    if workload not in ('conversation', 'build', 'investigate', 'verify'):
        raise ValueError('Unknown Muse workload')
    profile = 'build' if workload == 'investigate' else workload
    reason = {'conversation': 'Discussion and planning', 'build': 'Creating or changing game code',
              'investigate': 'Tracing a reported failure', 'verify': 'Checking the candidate independently'}[workload]
    if workload != 'conversation' and (repair or compound or source_bytes >= 48 * 1024):
        profile = 'deep'
        reason = ('A previous attempt failed verification' if repair else
                  'Several implementation specialties are involved' if compound else
                  'The editable source is large')
    return dict(profile=profile, **EXECUTION_PROFILES[profile], reason=reason)


def validate_execution(execution):
    if not isinstance(execution, dict) or execution.get('profile') not in EXECUTION_PROFILES:
        raise ValueError('Choose a supported Muse execution profile')
    expected = dict(profile=execution['profile'], **EXECUTION_PROFILES[execution['profile']],
                    reason=execution.get('reason'))
    if execution != expected or not isinstance(expected['reason'], str) or not 1 <= len(expected['reason']) <= 200:
        raise ValueError('Muse execution limits do not match the supported profile')


def provider_schema(schema):
    """Inline local refs before dispatch; callers retain full local validation."""
    unsupported = {'uniqueItems', 'propertyNames'}
    maps = {'properties', 'patternProperties', 'dependentSchemas'}
    children = {'items', 'additionalProperties', 'unevaluatedProperties', 'contains',
                'not', 'if', 'then', 'else', 'unevaluatedItems', 'contentSchema'}
    arrays = {'anyOf', 'allOf', 'oneOf', 'prefixItems'}

    def convert(node, trail=()):
        if not isinstance(node, dict):
            return deepcopy(node)
        if '$ref' in node:
            ref = node['$ref']
            if not isinstance(ref, str) or not ref.startswith('#/') or ref in trail:
                raise ValueError('Muse response schema needs a non-recursive local reference: ' + str(ref))
            target = schema
            try:
                for part in ref[2:].split('/'):
                    part = part.replace('~1', '/').replace('~0', '~')
                    target = target[int(part)] if isinstance(target, list) else target[part]
            except (KeyError, IndexError, TypeError, ValueError) as error:
                raise ValueError('Muse response schema has an unresolved reference: ' + ref) from error
            resolved = convert(target, (*trail, ref))
            siblings = {key: value for key, value in node.items() if key != '$ref'}
            return {'allOf': [resolved, convert(siblings, trail)]} if siblings else resolved
        result = {}
        dynamic_map = node.get('type') == 'object' and isinstance(node.get('additionalProperties'), dict)
        for key, value in node.items():
            if key in unsupported or key in ('$defs', 'definitions') or (key in ('minProperties', 'maxProperties') and not dynamic_map):
                continue
            if key in maps:
                result[key] = {name: convert(child, trail) for name, child in value.items()}
            elif key in children:
                result[key] = convert(value, trail)
            elif key in arrays:
                result[key] = [convert(child, trail) for child in value]
            else:
                result[key] = deepcopy(value)
        return result

    return convert(schema)


def flat_map_value(schema):
    """Object map values can share their row with the key, saving one level."""
    return (schema.get('type') == 'object' and schema.get('additionalProperties') is False
            and 'key' not in schema.get('properties', {})
            and not any(key in schema for key in ('anyOf', 'oneOf', 'allOf')))


def structured_depth(schema):
    """Count nested response objects/arrays, not schema keyword dictionaries."""
    if not isinstance(schema, dict):
        return 0
    kind = schema.get('type', [])
    kinds = [kind] if isinstance(kind, str) else kind
    children = list(schema.get('properties', {}).values())
    children += [schema[key] for key in ('items', 'additionalProperties') if isinstance(schema.get(key), dict)]
    for key in ('anyOf', 'oneOf', 'allOf', 'prefixItems'):
        children += schema.get(key, [])
    return int(any(kind in ('object', 'array') for kind in kinds)) + max(map(structured_depth, children), default=0)


def structured_schema(schema):
    """Use native structured output, with closed objects and explicit optional slots.

    Dynamic maps travel as key/value rows because the provider requires closed
    object fields. The original schema remains authoritative after decoding.
    """
    schema = provider_schema(schema)

    def convert(node):
        if not isinstance(node, dict):
            return deepcopy(node)
        result = deepcopy(node)
        for key in ('anyOf', 'oneOf', 'allOf'):
            if key in node:
                result[key] = [convert(child) for child in node[key]]
        if node.get('type') == 'object':
            properties = node.get('properties', {})
            extra = node.get('additionalProperties', False)
            if isinstance(extra, dict):
                if properties:
                    raise ValueError('Muse response schema cannot mix named fields and dynamic map entries')
                bounds = {target: node[source] for source, target in
                          [('minProperties', 'minItems'), ('maxProperties', 'maxItems')] if source in node}
                if flat_map_value(extra):
                    row = convert(extra)
                    row['properties'] = {'key': dict(type='string'), **row['properties']}
                    row['required'] = ['key', *row['required']]
                    return dict(type='array', items=row, **bounds)
                return dict(type='array', items=dict(type='object', additionalProperties=False,
                    required=['key', 'value'], properties=dict(key=dict(type='string'), value=convert(extra))), **bounds)
            if extra is not False:
                raise ValueError('Muse response schema requires bounded object fields')
            required = node.get('required', [])
            result['properties'] = {name: convert(child) if name in required or Draft202012Validator(child).is_valid(None) else
                {'anyOf': [convert(child), {'type': 'null'}]} for name, child in properties.items()}
            result['required'] = list(properties)
            result['additionalProperties'] = False
        if 'items' in node:
            result['items'] = convert(node['items'])
        return result

    result = convert(schema)
    depth = structured_depth(result)
    if depth > MAX_SCHEMA_DEPTH:
        raise ValueError(f'Muse response schema needs {depth} nesting levels; the limit is {MAX_SCHEMA_DEPTH}. '
                         'No request was sent or credits reserved. Simplify the response format first.')
    return result


def decode_structured(value, schema):
    """Undo transport-only optional slots and maps without repairing model text."""
    schema = provider_schema(schema)
    for key in ('anyOf', 'oneOf'):
        if key in schema and 'type' not in schema:
            for child in schema[key]:
                if Draft202012Validator(structured_schema(child)).is_valid(value):
                    return decode_structured(value, child)
            raise ValueError('Muse reply does not match a structured response variant')
    if schema.get('type') == 'object':
        extra = schema.get('additionalProperties', False)
        if isinstance(extra, dict):
            result = {}
            for row in value:
                if row['key'] in result:
                    raise ValueError('Muse returned a duplicate map key')
                item = {key: item for key, item in row.items() if key != 'key'} if flat_map_value(extra) else row['value']
                result[row['key']] = decode_structured(item, extra)
            return result
        required = schema.get('required', [])
        return {key: decode_structured(item, schema['properties'][key]) for key, item in value.items()
                if key in required or item is not None or
                Draft202012Validator(schema['properties'][key]).is_valid(None)}
    if schema.get('type') == 'array':
        return [decode_structured(item, schema['items']) for item in value]
    return value


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
            bound = IMAGE_MICRO_USD if row.get('model') == IMAGE_MODEL else RESERVATION_MICRO_USD
            if row.get('model') not in (None, MODEL, IMAGE_MODEL):
                raise ValueError('Invalid Muse ledger model')
            if row.get('status') not in ('reserved', 'settled') or row.get('reserved_micro_usd') != bound:
                raise ValueError('Invalid Muse credit reservation')
            if row['status'] == 'reserved' and 'charged_micro_usd' in row:
                raise ValueError('An uncertain credit reservation cannot report a settled charge')
            if row['status'] == 'settled' and (type(row.get('charged_micro_usd')) is not int or not 0 <= row['charged_micro_usd'] <= bound):
                raise ValueError('Invalid Muse credit settlement')
            if row.get('budget_id') is not None and row['budget_id'] not in budgets:
                raise ValueError('Credit request has no approved run budget')
        for key, limit in budgets.items():
            if sum(row.get('charged_micro_usd', row['reserved_micro_usd']) for row in data['requests'].values()
                   if row.get('budget_id') == key) > limit:
                raise ValueError('Run credit ledger exceeds its ceiling')
        return data

    def reserve(self, request_id, *, budget=None, model=MODEL, verified_ceiling_micro_usd=None):
        if model not in (MODEL, IMAGE_MODEL):
            raise ValueError('Unsupported Muse reservation model')
        bound = IMAGE_MICRO_USD if model == IMAGE_MODEL else RESERVATION_MICRO_USD
        if verified_ceiling_micro_usd is not None and (type(verified_ceiling_micro_usd) is not int or verified_ceiling_micro_usd < 0):
            raise ValueError('Invalid verified credit ceiling')
        with exclusive(self.folder / 'muse-credits.lock'):
            data = self.read()
            self.retire_usage_inspection(data)
            if data.get('blocked'):
                raise ValueError('Further Muse calls are stopped: ' + data['blocked'])
            if request_id in data['requests']:
                raise ValueError('This Muse request already has a credit reservation; inspect its saved outcome before retrying')
            used = sum(row.get('charged_micro_usd', row['reserved_micro_usd']) for row in data['requests'].values())
            if used + bound > min(data['limit_micro_usd'], BUDGET_MICRO_USD):
                raise ValueError('Muse free-credit budget cannot cover another request')
            if verified_ceiling_micro_usd is not None and used + bound > verified_ceiling_micro_usd:
                raise ValueError('Verified promotional balance cannot cover another image')
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
                local_used = sum(row.get('charged_micro_usd', row['reserved_micro_usd'])
                                 for row in data['requests'].values() if row.get('budget_id') == budget['id'])
                if local_used + bound > budget['limit_micro_usd']:
                    raise ValueError('Polish run credit budget cannot cover another request')
                budgets[budget['id']] = budget['limit_micro_usd']
            data['requests'][request_id] = dict(status='reserved', reserved_micro_usd=bound)
            if model == IMAGE_MODEL:
                data['requests'][request_id]['model'] = model
            if budget is not None:
                data['requests'][request_id]['budget_id'] = budget['id']
            atomic_json(self.path, data)

    @staticmethod
    def retire_usage_inspection(data):
        """Retire the old metadata-only block without releasing any reservation."""
        if data.get('blocked') == UNEXPECTED_USAGE:
            data.setdefault('retired_usage_inspections', []).append(data.pop('blocked'))

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
        limit = min(data['limit_micro_usd'], BUDGET_MICRO_USD)
        return dict(limit_usd=limit / 1_000_000, estimated_spent_usd=spent / 1_000_000,
                    reserved_usd=held / 1_000_000, available_usd=max(0, limit - spent - held) / 1_000_000,
                    blocked=None if data.get('blocked') == UNEXPECTED_USAGE else data.get('blocked'))

    def settle(self, request_id, input_tokens, output_tokens):
        if any(type(v) is not int or v < 0 for v in (input_tokens, output_tokens)):
            raise ValueError('Valid Muse usage counters required')
        charge = (5 * input_tokens + 17 * output_tokens + 3) // 4
        if input_tokens + output_tokens > 1_048_576 or charge > RESERVATION_MICRO_USD:
            self.freeze('Usage exceeded the one-step context or price bound')
            raise ValueError('Muse reported usage beyond the request budget; further calls are stopped')
        with exclusive(self.folder / 'muse-credits.lock'):
            data = self.read()
            row = data['requests'][request_id]
            if row.get('model') == IMAGE_MODEL:
                raise ValueError('Image requests settle by returned image count, not tokens')
            row.update(status='settled', charged_micro_usd=charge, input_tokens=input_tokens, output_tokens=output_tokens)
            atomic_json(self.path, data)

    def settle_image(self, request_id):
        """Only a captured successful one-image response may settle this hold."""
        with exclusive(self.folder / 'muse-credits.lock'):
            data = self.read()
            row = data['requests'][request_id]
            if row.get('model') != IMAGE_MODEL:
                raise ValueError('Image settlement requires an image reservation')
            row.update(status='settled', charged_micro_usd=IMAGE_MICRO_USD, returned_images=1)
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
        return  # Uncertain metadata retains the full hold without interrupting chat.
    if any(type(models[0].get(key)) is not int or models[0][key] < 0
           for key in ('input_tokens', 'output_tokens')):
        return
    ledger.settle(capture.get('ledger_request_id', request_id), models[0]['input_tokens'], models[0]['output_tokens'])


def completed_capture(capture, ledger=None):
    if capture.get('exit_code') != 0 or not isinstance(capture.get('response'), str) or not capture['response'].strip():
        failed = [e.get('payload', {}) for e in capture.get('events', []) if e.get('payload_type') == 'run.terminal.failed']
        reason = failed[-1].get('reason') if failed else None
        reason = capture.get('response_error') or reason
        detail = ' ' + reason[:500] if isinstance(reason, str) else ''
        row = ledger.read()['requests'].get(capture.get('ledger_request_id'), {}) if ledger else {}
        accounting = (' Reported credit usage has been recorded.' if row.get('status') == 'settled' else
                      ' The previous credit reservation remains counted.')
        raise ValueError('Muse did not complete a reply.' + detail + ' Send a new message to try again.' + accounting)
    return capture


def structured_reply_error(error):
    if not isinstance(error, ValidationError):
        return str(error)[:400]
    issue = best_match([error])
    field = '.'.join(map(str, issue.absolute_path)) or 'reply'
    return f'The {field} field did not meet the {issue.validator} requirement.'


def save_capture(path, metadata, events, code, prepared_schema, output_schema):
    terminal = [e.get('payload', {}) for e in events if e.get('payload_type') == 'run.terminal.completed']
    capture = dict(metadata, events=events, exit_code=code, response=None)
    if len(terminal) == 1 and terminal[0].get('terminal') == 'completed':
        capture['response'] = terminal[0].get('text')
        if output_schema is not None:
            try:
                wire = json.loads(capture['response'])
                Draft202012Validator(prepared_schema).validate(wire)
                decoded = decode_structured(wire, output_schema)
                Draft202012Validator(output_schema).validate(decoded)
                capture['response'] = json.dumps(decoded, ensure_ascii=False)
            except (TypeError, ValueError, ValidationError) as error:
                capture['response'] = None
                capture['response_error'] = 'Muse returned an invalid structured reply. ' + structured_reply_error(error)
    capture['capture_sha256'] = digest(capture)
    atomic_json(path, capture)
    return capture


def provider_events(path):
    with path.open('rb') as stream:
        raw = stream.read(MAX_CAPTURE + 1)
    if len(raw) > MAX_CAPTURE:
        raise ValueError('Muse response exceeded the capture limit; reservation remains held')
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def recover_capture(path, pending, ledger_id, binding, prepared_schema, output_schema):
    metadata_path = pending.with_suffix('.json')
    if not metadata_path.is_file():
        raise ValueError('Muse has a credit reservation but no recoverable reply for this request. '
                         'The previous credit reservation remains counted. Start a new request to try again.')
    metadata = read_json(metadata_path)
    if (metadata.get('ledger_request_id') != ledger_id or metadata.get('request_binding') != binding
            or metadata.get('model') != MODEL):
        raise ValueError('Saved Muse request context changed; no retry was sent')
    try:
        events = provider_events(pending)
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        events = []  # An orphaned provider may still be writing its final event.
    terminals = [e['payload_type'] for e in events if e.get('payload_type') in
                 ('run.terminal.completed', 'run.terminal.failed')]
    if len(terminals) != 1:
        raise ValueError('No finished Muse reply is saved yet. Check for the saved reply again. '
                         'The previous credit reservation remains counted.')
    return save_capture(path, metadata, events, 0 if terminals[0] == 'run.terminal.completed' else 1,
                        prepared_schema, output_schema)


def run(root, folder, prompt, request_id, *, binary=None, output_schema=None, progress=None, images=None, budget=None,
        check=None, execution=None, stream_preview=None):
    captures = Path(folder) / 'muse-captures'
    captures.mkdir(exist_ok=True)
    with exclusive(captures / (request_id + '.lock')):
        return run_request(root, folder, captures, prompt, request_id, binary=binary, output_schema=output_schema,
                           progress=progress, images=images, budget=budget, check=check, execution=execution,
                           stream_preview=stream_preview)


def run_request(root, folder, captures, prompt, request_id, *, binary, output_schema, progress, images, budget,
                check, execution, stream_preview):
    if execution is not None:
        validate_execution(execution)
    prepared_schema = structured_schema(output_schema) if output_schema is not None else None
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
    request_context = dict(prompt=prompt, schema=output_schema,
                           images=[sha256(raw).hexdigest() for raw in pictures], budget=budget)
    if execution is not None:
        request_context['execution'] = execution
    binding = digest(request_context)
    capture_path = captures / (request_id + '.json')
    pending_path = captures / (request_id + '.pending.jsonl')
    ledger_id = sha256((str(Path(folder).resolve()) + ':' + request_id).encode()).hexdigest()
    if capture_path.is_file():
        capture = read_json(capture_path)
        if capture.get('capture_sha256') != digest({k: v for k, v in capture.items() if k != 'capture_sha256'}):
            raise ValueError('Saved Muse capture changed; no retry was sent')
        if ((capture.get('request_binding') is not None or pictures or budget is not None or execution is not None) and
                capture.get('request_binding') != binding):
            raise ValueError('Saved Muse request context changed; no retry was sent')
    elif ledger_id in ledger.read()['requests']:
        capture = recover_capture(capture_path, pending_path, ledger_id, binding, prepared_schema, output_schema)
    else:
        capture = None
    if capture is not None:
        settle_capture(ledger, request_id, capture)
        if progress:
            progress('cached_reply')
        return completed_capture(capture, ledger)
    binary = Path(binary) if binary else installed_binary()
    if not binary or not binary.is_file():
        raise ValueError('Muse Code is not installed. Install and sign in to Muse before sending a message.')
    with tempfile.TemporaryDirectory(dir=captures) as scratch:
        scratch = Path(scratch)
        prompt_path = scratch / 'prompt.txt'
        transport_prompt = prompt
        if prepared_schema is not None:
            transport_prompt = ('Return the JSON response directly, following this transport schema. '
                'Do not wrap it in a string or Markdown fences. Every field is required on the wire; '
                'use null for optional fields you are not supplying. Dynamic maps such as asset_budget '
                'are arrays of rows with key and either value or the object fields beside key. '
                'Follow the transport schema exactly; the host restores the maps to objects. '
                'The transport schema takes precedence over response format examples in the request:\n' +
                json.dumps(prepared_schema, ensure_ascii=False) + '\nRequest:\n' + prompt)
        prompt_path.write_text(transport_prompt, encoding='utf-8')
        args = [str(binary), 'exec', '--provider', 'meta', '--model', MODEL,
                '--base-url', muse_settings.API_BASE_URL,
                '--config', 'provider_retry.max_retries=0',
                '--reasoning-effort', execution['reasoning_effort'] if execution else 'low',
                '--contributor-mode', 'off', '--preset', 'empty',
                '--disable-write', '--disable-shell', '--disable-web-tools', '--disable-reminders',
                '--disable-request-user-input', '--no-foreign-personal-context', '--no-session-log',
                '--max-model-steps', '1', '--json', '--prompt-file', str(prompt_path)]
        if output_schema is not None:
            schema_path = scratch / 'response-schema.json'
            atomic_json(schema_path, prepared_schema)
            args += ['--output-schema', str(schema_path)]
        for index, raw in enumerate(pictures):
            image_path = scratch / ('screenshot-' + str(index) + '.png')
            image_path.write_bytes(raw)
            args += ['--image', str(image_path)]
        metadata = dict(model=MODEL, binary_sha256=sha256(binary.read_bytes()).hexdigest(), ledger_request_id=ledger_id,
                        reservation_micro_usd=RESERVATION_MICRO_USD, request_binding=binding)
        if execution is not None:
            metadata['execution'] = execution
        env = muse_settings.request_environment(root, binary, scratch)
        if check:
            check()
        metadata_path = pending_path.with_suffix('.json')
        atomic_json(metadata_path, metadata)
        ledger.reserve(ledger_id, budget=budget)
        with pending_path.open('wb') as output, (scratch / 'stderr.log').open('wb') as errors:
            process = subprocess.Popen(args, cwd=scratch, env=env, stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            timeout_seconds = execution['timeout_seconds'] if execution else 180
            started = time.monotonic()
            deadline, offset, pending = started + timeout_seconds, 0, b''
            phase, response_chars, last_report, reported_phase = 'provider_starting', 0, 0, None
            deltas = []
            previewed_chars = 0
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
                    path = pending_path
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
                                if stream_preview:
                                    deltas.append(value)
                                phase = 'receiving'
                        elif kind == 'run.terminal.completed':
                            phase = 'provider_finished'
                    now = time.monotonic()
                    if progress and (phase != reported_phase or chunk and now - last_report >= 1 or now - last_report >= 5):
                        preview = {}
                        if stream_preview and response_chars != previewed_chars:
                            preview['file_changes'] = stream_preview(''.join(deltas))
                            previewed_chars = response_chars
                        progress(phase, response_chars=response_chars, elapsed_seconds=int(now - started),
                                 execution=execution, timeout_seconds=timeout_seconds, **preview)
                        last_report, reported_phase = now, phase
                    if finished:
                        break
                    if time.monotonic() >= deadline:
                        raise ValueError(f'Muse reached its {timeout_seconds // 60}-minute request limit. '
                            'The work is incomplete. Its credit reservation remains held; no automatic retry was sent.')
            finally:
                if not finished:
                    process.kill()
                    process.wait(timeout=10)
        events = provider_events(pending_path)
        if execution is not None:
            metadata['elapsed_seconds'] = round(time.monotonic() - started, 3)
        capture = save_capture(capture_path, metadata, events, code, prepared_schema, output_schema)
        pending_path.unlink()
        metadata_path.unlink()
        settle_capture(ledger, ledger_id, capture)
        return completed_capture(capture, ledger)
