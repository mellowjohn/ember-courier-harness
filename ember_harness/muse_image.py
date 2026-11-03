"""Direct Muse Image calls with a shared credit budget and replay-safe captures."""
from base64 import b64decode
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener

from . import asset_2d, asset_library
from .core import canonical, digest
from .muse_chat import CreditLedger, IMAGE_MODEL, IMAGE_MICRO_USD
from .recovery import atomic_json, exclusive, read_json

ENDPOINT = 'https://api.meta.ai/v1/images/generations'
MAX_RESPONSE = 18 * 1024 * 1024
BILLING_URL = 'https://dev.meta.ai/billing'
TERMS_URL = 'https://dev.meta.ai/legal/terms-of-service'


class ImageUnavailable(ValueError):
    pass


def credential():
    """Reuse Muse's credential in memory; never return it in app state or captures."""
    key = os.environ.get('META_API_KEY') or os.environ.get('MODEL_API_KEY')
    if not key:
        path = Path.home() / '.config/muse/auth.json'
        try:
            data = json.loads(asset_library.limited(path, 1_048_576))
            provider = data['providers']['meta']
            if provider.get('api_base_url', 'https://api.meta.ai/v1').rstrip('/') != 'https://api.meta.ai/v1':
                raise ImageUnavailable('Muse Image requires the official Meta API connection')
            key = provider.get('api_key')
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise ImageUnavailable('Sign in to Muse Code with a Meta Model API credential to use Muse Image') from error
    if not isinstance(key, str) or not key or len(key) > 16384 or '\n' in key or '\r' in key:
        raise ImageUnavailable('A valid Meta Model API credential is required')
    return key


def coverage_path(root):
    return Path(root) / '.harness/muse-image-credits.json'


def verify_coverage(root, balance_micro_usd, *, no_paid_fallback, source=BILLING_URL):
    """Trusted owner confirmation of observed billing; no provider setting changes."""
    if (no_paid_fallback is not True or type(balance_micro_usd) is not int or
            not IMAGE_MICRO_USD <= balance_micro_usd <= 150_000_000 or
            not isinstance(source, str) or not source.startswith(BILLING_URL)):
        raise ValueError('Confirm active Model API promotional credits and that no payment method can be charged')
    now = datetime.now(timezone.utc)
    ledger = CreditLedger(root).read()
    baseline = sum(row.get('charged_micro_usd', row['reserved_micro_usd']) for row in ledger['requests'].values())
    body = dict(version=1, credential_sha256=sha256(credential().encode()).hexdigest(),
        balance_micro_usd=balance_micro_usd, ledger_baseline_micro_usd=baseline,
        no_paid_fallback=True, verified_at=now.isoformat(), valid_until=(now+timedelta(hours=24)).isoformat(),
        source=source, model=IMAGE_MODEL, price_micro_usd=IMAGE_MICRO_USD)
    atomic_json(coverage_path(root), {**body, 'sha256': digest(body)})
    return status(root)


def use_shared_credit_budget(root, authorization):
    """Owner-authorized use of the existing Model API grant; no budget reset.

    Meta's terms 13.3 describe credits for the Model API Services, rather than
    Spark-only credits. The owner confirms the grant already works with Spark.
    This does not claim a fresh billing balance or that a card was removed.
    """
    if not isinstance(authorization, str) or not 1 <= len(authorization.strip()) <= 2000:
        raise ValueError('Record the owner authorization for the shared Muse credit budget')
    ledger = CreditLedger(root)
    if ledger.summary()['blocked'] or ledger.summary()['available_usd'] < IMAGE_MICRO_USD/1_000_000:
        raise ImageUnavailable('The shared Muse credit budget cannot cover another image')
    body = dict(version=2, policy='shared-model-api-budget', model=IMAGE_MODEL,
        credential_sha256=sha256(credential().encode()).hexdigest(), price_micro_usd=IMAGE_MICRO_USD,
        authorization=authorization.strip(), authorized_at=datetime.now(timezone.utc).isoformat(),
        source=TERMS_URL, billing_balance_verified=False)
    atomic_json(coverage_path(root), {**body, 'sha256': digest(body)})
    return status(root)


def status(root):
    result = dict(ready=False, model=IMAGE_MODEL, price_usd=IMAGE_MICRO_USD/1_000_000,
                  billing_url=BILLING_URL, reason='Verify active Model API free credits before generating artwork')
    try:
        key_hash = sha256(credential().encode()).hexdigest()
        data = read_json(coverage_path(root))
        if data.get('version') == 2:
            if (data.get('sha256') != digest({k:v for k,v in data.items() if k != 'sha256'}) or
                    data.get('policy') != 'shared-model-api-budget' or data.get('credential_sha256') != key_hash or
                    data.get('model') != IMAGE_MODEL or data.get('price_micro_usd') != IMAGE_MICRO_USD or
                    not isinstance(data.get('authorization'), str) or not data['authorization'].strip() or
                    data.get('source') != TERMS_URL):
                raise ImageUnavailable('The Muse Image connection changed; reconnect the intended Meta account')
            summary = CreditLedger(root).summary()
            if summary['blocked'] or summary['available_usd'] < IMAGE_MICRO_USD/1_000_000:
                raise ImageUnavailable('The shared Muse credit budget cannot cover another image')
            result.update(ready=True, policy=data['policy'], reason='Muse Image connected · shared Muse credit budget',
                billing_balance_verified=False, authorized_at=data['authorized_at'],
                verified_ceiling_micro_usd=int(round(summary['limit_usd']*1_000_000)))
            return result
        if (data.get('sha256') != digest({k:v for k,v in data.items() if k != 'sha256'}) or
                data.get('version') != 1 or data.get('credential_sha256') != key_hash or
                data.get('no_paid_fallback') is not True or data.get('model') != IMAGE_MODEL or
                data.get('price_micro_usd') != IMAGE_MICRO_USD or
                type(data.get('balance_micro_usd')) is not int or
                not IMAGE_MICRO_USD <= data['balance_micro_usd'] <= 150_000_000 or
                type(data.get('ledger_baseline_micro_usd')) is not int or data['ledger_baseline_micro_usd'] < 0):
            raise ImageUnavailable('Muse Image credit verification changed; verify billing again')
        now = datetime.now(timezone.utc)
        verified, until = (datetime.fromisoformat(data[k]) for k in ('verified_at', 'valid_until'))
        if not verified <= now < until <= verified + timedelta(hours=24):
            raise ImageUnavailable('Muse Image credit verification expired; check Meta billing again')
        ledger = CreditLedger(root)
        rows = ledger.read()['requests'].values()
        spent = sum(row.get('charged_micro_usd', row['reserved_micro_usd']) for row in rows)
        remaining = data['balance_micro_usd'] - max(0, spent-data['ledger_baseline_micro_usd'])
        if ledger.summary()['blocked'] or ledger.summary()['available_usd'] < IMAGE_MICRO_USD/1_000_000 or remaining < IMAGE_MICRO_USD:
            raise ImageUnavailable('Verified Muse free credits cannot cover another image')
        result.update(ready=True, reason='Muse Image connected · verified free credits',
                      verified_at=data['verified_at'], valid_until=data['valid_until'],
                      verified_ceiling_micro_usd=data['ledger_baseline_micro_usd']+data['balance_micro_usd'])
    except FileNotFoundError:
        pass
    except ImageUnavailable as error:
        result['reason'] = str(error)
    except (OSError, ValueError, KeyError, TypeError):
        result['reason'] = 'Muse Image credit verification is unavailable; check Meta billing again'
    return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ImageUnavailable('Meta image request redirected; no credential was forwarded')


def parameters(request):
    spec = request['specification']
    if canonical(request) != canonical(asset_2d.generation_request(spec)):
        raise ValueError('Image request changed')
    width, height = asset_2d.describe(spec)['dimensions_px']
    prompt = (spec['production']['prompt'] + '\nArt direction: ' + spec['art_direction'] +
        f"\nOriginal game artwork in a uniform atlas: {spec['grid'][0]} columns and {spec['grid'][1]} rows. "
        f"Fill the first {spec['frames']} cells in row-major order. Consistent scale, lighting and pivot {spec['pivot']}. " +
        ('Fill terrain cells edge-to-edge. ' if 'tileset' in spec or spec['kind'] == 'tile' else
         'Keep each subject fully inside its cell, with generous empty margins. ') +
        'No labels, text, logos, borders or watermarks. ')
    if spec['require_alpha']:
        prompt += ('Use a perfectly flat solid #FF00FF magenta background in every cell, without shadows or gradients. '
                   'Do not use magenta anywhere on the subjects. The game pipeline removes this exact matte to make transparency. ')
    if spec['kind'] == 'vfx':
        prompt += 'Coherent anticipation, impact and dissipation sequence. No heat distortion. '
    prompt += asset_2d.animation_prompt(spec) + asset_2d.tile_prompt(spec)
    return dict(model=IMAGE_MODEL, prompt=prompt, n=1, size=f'{width}x{height}',
                output_format='png', response_format='b64_json', reasoning_strength='high',
                tool_enablement=dict(enable_image_search=False, enable_web_search=False, enable_shell=False))


def generate_batch(root, folder, turn_id, requests, *, budget=None, progress=None, item_progress=None):
    """Checkpoint a bounded artwork batch using the single-image replay and credit gate."""
    from .chat_build import MAX_IMAGE_REQUESTS
    if not isinstance(turn_id, str) or not re.fullmatch('[a-zA-Z0-9-]{16,64}', turn_id):
        raise ValueError('A stable artwork batch ID is required')
    if not isinstance(requests, list) or not 1 <= len(requests) <= MAX_IMAGE_REQUESTS:
        raise ValueError('Choose one to eight artwork requests per batch')
    # Validate the complete batch before the first reservation or dispatch.
    for request in requests:
        parameters(request)
        if request['specification']['production']['tool'] != 'muse_image':
            raise ValueError('Choose Muse Image for batch generation')
    ids = [request['specification']['id'] for request in requests]
    if len(set(ids)) != len(ids):
        raise ValueError('Give each artwork request a unique asset ID')
    directory = Path(folder) / 'image-batches'
    directory.mkdir(exist_ok=True)
    plan_path, result_path = directory / (turn_id+'.json'), directory / (turn_id+'-results.json')
    plan = dict(requests=requests, budget=budget)
    with exclusive(directory / (turn_id+'.lock')):
        if plan_path.exists() and canonical(read_json(plan_path)) != canonical(plan):
            raise ValueError('Saved artwork batch changed; prepare a new request')
        atomic_json(plan_path, plan)
        items = []
        for index, request in enumerate(requests):
            request_id = sha256((turn_id+':batch:'+str(index)).encode()).hexdigest()
            try:
                notify=(lambda phase,name=request['specification']['display_name']:item_progress(phase,name)) if item_progress else progress
                generation = generate(root, folder, request_id, request, budget=budget, progress=notify)
            except ValueError as error:
                # A failed item cannot discard successful siblings. The single-image
                # capture prevents resending any dispatch with an uncertain result.
                generation = dict(status='blocked', reason=str(error), model=IMAGE_MODEL)
            items.append(dict(request=request, request_id=request_id, generation=generation))
            completed = sum(item['generation']['status'] == 'generated' for item in items)
            result = dict(items=items, completed=completed, total=len(requests),
                          status='generated' if completed == len(requests) else 'partial' if completed else 'blocked')
            atomic_json(result_path, result)
        return result


def generate(root, folder, turn_id, request, *, budget=None, progress=None):
    """Return a known asset ref. Never accept art, write a game or retry a dispatch."""
    if not isinstance(turn_id, str) or not re.fullmatch('[a-zA-Z0-9-]{16,64}', turn_id):
        raise ValueError('A stable artwork request ID is required')
    # Older chat cards named the generic Codex handoff. Preserve that request in
    # the chat, but record the provider actually used in the generated source.
    if request.get('specification', {}).get('production', {}).get('tool') == 'image_gen':
        if canonical(request) != canonical(asset_2d.generation_request(request['specification'])):
            raise ValueError('Image request changed')
        spec = deepcopy(request['specification'])
        spec['production']['tool'] = 'muse_image'
        request = asset_2d.generation_request(spec)
    if request.get('specification', {}).get('production', {}).get('tool') != 'muse_image':
        raise ValueError('Choose Muse Image for direct image generation')
    params = parameters(request)
    folder = Path(folder)
    captures = folder / 'image-captures'; captures.mkdir(exist_ok=True)
    capture_path, raw_path = captures / (turn_id+'.json'), captures / (turn_id+'.png')
    binding = digest(dict(request=request, parameters=params, budget=budget))
    ledger = CreditLedger(root)
    ledger_id = sha256((str(folder.resolve())+':image:'+turn_id).encode()).hexdigest()
    with exclusive(captures / (turn_id+'.lock')):
        if capture_path.exists():
            saved = read_json(capture_path)
            if (saved.get('sha256') != digest({k:v for k,v in saved.items() if k != 'sha256'}) or
                    saved.get('binding') != binding):
                raise ValueError('Saved Muse Image request changed; no image was resent')
            if saved.get('status') != 'returned':
                raise ImageUnavailable('This image request did not complete. Its reservation remains held; ask for a new generation to try again')
            raw = asset_library.limited(raw_path, 12*1024*1024)
            if sha256(raw).hexdigest() != saved['source_sha256']:
                raise ValueError('Saved Muse Image pixels changed; no image was resent')
        else:
            connection = status(root)
            if not connection['ready']:
                raise ImageUnavailable(connection['reason'])
            key = credential()
            ledger.reserve(ledger_id, budget=budget, model=IMAGE_MODEL,
                           verified_ceiling_micro_usd=connection['verified_ceiling_micro_usd'])
            pending = dict(version=1, status='dispatching', binding=binding, model=IMAGE_MODEL,
                           ledger_request_id=ledger_id, request_sha256=request['request_sha256'])
            atomic_json(capture_path, {**pending, 'sha256': digest(pending)})
            if progress: progress('image_generating')
            req = Request(ENDPOINT, data=canonical(params), headers={
                'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'}, method='POST')
            try:
                with build_opener(NoRedirect()).open(req, timeout=180) as response:
                    response_bytes = response.read(MAX_RESPONSE+1)
                    response_id = response.headers.get('x-request-id', '')[:200]
                if len(response_bytes) > MAX_RESPONSE:
                    raise ImageUnavailable('Muse Image response exceeded its limit; the reservation remains held')
                payload = json.loads(response_bytes)
                rows = payload.get('data')
                if isinstance(rows, list) and len(rows) > 1:
                    ledger.freeze('Muse Image returned more images than reserved; inspect its credit usage')
                if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict) or not isinstance(rows[0].get('b64_json'), str):
                    raise ImageUnavailable('Muse Image did not return exactly one encoded image; the reservation remains held')
                raw = b64decode(rows[0]['b64_json'], validate=True)
                if not 1 <= len(raw) <= 12*1024*1024:
                    raise ImageUnavailable('Muse Image source exceeded its limit; the reservation remains held')
                raw_path.write_bytes(raw)
                saved = {**pending, 'status': 'returned', 'source_sha256': sha256(raw).hexdigest(),
                         'request_id': response_id, 'returned_images': 1, 'price_micro_usd': IMAGE_MICRO_USD}
                atomic_json(capture_path, {**saved, 'sha256': digest(saved)})
            except HTTPError as error:
                raise ImageUnavailable(f'Muse Image returned HTTP {error.code}. No automatic retry was sent; the one-cent reservation remains held') from None
            except (URLError, TimeoutError, OSError, ValueError, KeyError, TypeError) as error:
                if isinstance(error, ImageUnavailable): raise
                raise ImageUnavailable('Muse Image did not return a usable reply. No automatic retry was sent; the one-cent reservation remains held') from None
        ledger.settle_image(ledger_id)
        if progress: progress('image_preparing')
        prepared, report = asset_2d.prepare_generated_png(raw, request['specification'])
        source = Path(root).resolve() / '.harness/asset-source/muse-image' / folder.name / turn_id
        if source.exists():
            if (asset_library.limited(source/'asset.js', 524288).decode('utf-8') != asset_2d.package(prepared, request['specification']) or
                    canonical(read_json(source/'generation-request.json')) != canonical(request) or
                    canonical(read_json(source/'asset-spec.json')) != canonical(request['specification']) or
                    asset_library.limited(source/(request['specification']['id']+'.png'), asset_2d.MAX_PNG) != prepared):
                raise ValueError('Prepared Muse Image source changed')
        else:
            asset_2d.write_source(source, prepared, request['specification'], request)
            atomic_json(source/'preparation.json', report)
        ref = asset_library.register(root, source)
        return dict(status='generated', asset_ref=ref, model=IMAGE_MODEL,
                    price_usd=IMAGE_MICRO_USD/1_000_000, preparation=report)
