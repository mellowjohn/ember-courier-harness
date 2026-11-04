"""Local billing choice for the current computer's Muse Code account."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess

from .recovery import atomic_json, exclusive, read_json

SUBSCRIPTION = 'subscription'
API_CREDITS = 'api_credits'
API_BASE_URL = 'https://api.meta.ai/v1'


def load(root):
    try:
        settings = read_json(Path(root) / '.harness/muse-settings.json')
    except FileNotFoundError:
        return {'mode': SUBSCRIPTION}
    if settings == {'mode': SUBSCRIPTION}:
        return settings
    if (isinstance(settings, dict) and set(settings) == {'mode', 'credential_sha256'} and
            settings['mode'] == API_CREDITS and isinstance(settings['credential_sha256'], str) and
            re.fullmatch('[0-9a-f]{64}', settings['credential_sha256'])):
        return settings
    raise ValueError('Invalid local Muse settings')


def mode(root):
    return load(root)['mode']


def api_credential():
    key = os.environ.get('META_API_KEY') or os.environ.get('MODEL_API_KEY')
    if not key:
        config = os.environ.get('XDG_CONFIG_HOME')
        path = (Path(config) if config else Path.home() / '.config') / 'muse/auth.json'
        try:
            with path.open('rb') as auth:
                provider = json.loads(auth.read(1_048_577))['providers']['meta']
            if provider.get('api_base_url', API_BASE_URL).rstrip('/') != API_BASE_URL:
                raise ValueError('Unexpected API endpoint')
            key = provider.get('api_key')
        except (OSError, KeyError, AttributeError, TypeError, ValueError):
            raise ValueError('Set up your Meta Model API credential in Muse Code first') from None
    if (not isinstance(key, str) or not key or len(key) > 16384 or
            any(not 33 <= ord(char) <= 126 for char in key)):
        raise ValueError('A valid Meta Model API credential is required')
    return key


def authorized_api_credential(settings):
    key = api_credential()
    if sha256(key.encode()).hexdigest() != settings.get('credential_sha256'):
        raise ValueError('The Model API credential changed. Confirm promotional credits in Muse settings again.')
    return key


def save(root, selected, *, no_paid_fallback=False):
    if selected not in (SUBSCRIPTION, API_CREDITS):
        raise ValueError('Choose a Muse connection')
    settings = {'mode': selected}
    if selected == API_CREDITS:
        if no_paid_fallback is not True:
            raise ValueError('Confirm your own promotional credits and that no payment method can be charged')
        settings['credential_sha256'] = sha256(api_credential().encode()).hexdigest()
    path = Path(root) / '.harness/muse-settings.json'
    with exclusive(path.with_suffix('.lock')):
        atomic_json(path, settings)
    return {'mode': selected}


def request_environment(root, binary, cwd):
    settings = load(root)
    if settings['mode'] == SUBSCRIPTION:
        return subscription_environment(binary, cwd)
    env = os.environ.copy()
    env.pop('MODEL_API_KEY', None)
    env['META_API_KEY'] = authorized_api_credential(settings)
    return env


def subscription_environment(binary, cwd):
    # An environment API key overrides the CLI sign-in and can incur token charges.
    env = {name: value for name, value in os.environ.items()
           if name.upper() not in ('META_API_KEY', 'MODEL_API_KEY')}
    try:
        result = subprocess.run([str(binary), 'usage', '--json'], cwd=cwd, env=env,
            stdin=subprocess.DEVNULL, capture_output=True, timeout=20, check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        usage = json.loads(result.stdout)
        allowance = usage.get('allowance', usage)
        periods = [allowance.get(name) for name in ('window', 'weekly') if allowance.get(name) is not None]
        if not periods or any(type(period.get('used_percent')) not in (int, float) or
                              not 0 <= period['used_percent'] <= 100 for period in periods):
            raise ValueError('Subscription allowance unavailable')
    except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
        raise ValueError('Muse Code could not confirm available subscription usage. Sign in with your '
                         'subscribed Meta account and check `muse usage` before retrying.') from None
    if any(period['used_percent'] == 100 for period in periods):
        raise ValueError('Your Muse Code subscription allowance is exhausted. Check `muse usage` for its reset time.')
    return env
