"""Human playtest observations tied to exact approved browser builds."""
import re
import secrets

from . import chat_build
from .recovery import exclusive

# Runs before generated scripts. Messages remain untrusted iframe observations.
DIAGNOSTICS = """<script>(()=>{const channel=CHANNEL;let count=0;
const report=(kind,message)=>{if(count++<5)parent.postMessage({emberPreview:channel,kind,message:String(message).slice(0,300)},'*')};
addEventListener('error',event=>report('error',event.message||'A preview resource failed to load'),true);
addEventListener('unhandledrejection',event=>{let text='Unhandled promise rejection';try{text=String(event.reason)}catch{}report('rejection',text)});
})();</script>"""


def preview(root, folder):
    html = chat_build.preview(root, folder)
    last = chat_build.status(root, folder)['completed'][-1]
    channel = secrets.token_hex(16)
    return dict(html=DIAGNOSTICS.replace('CHANNEL', '"' + channel + '"') + html,
                channel=channel, request_ref=last['request_ref'])


def reports(folder):
    if not (folder / 'build-authority').exists():
        return []
    return [e for e in chat_build.harness(folder)._entries() if e['kind'] == 'chat_playtest_recorded'][-20:]


def context(root, folder):
    state = chat_build.status(root, folder)
    if not state['completed'] or state['resumable']:
        return []
    latest = state['completed'][-1]
    if chat_build.context(root, folder)['manifest'] != latest.get('manifest', {'index.html': latest['sha256']}):
        return []
    return [dict(report_id=e['report_id'], outcome=e['outcome'], note=e['note'], observations=e['observations'],
                 basis='Human playtest and untrusted browser observations; not automated verification')
            for e in reports(folder) if e['request_ref'] == latest['request_ref']][-5:]


def record(root, folder, report_id, request_ref, outcome, note, observations):
    if not isinstance(report_id, str) or not re.fullmatch('[a-zA-Z0-9-]{16,64}', report_id):
        raise ValueError('A stable playtest report ID is required')
    if outcome not in ('works', 'problem') or not isinstance(note, str) or len(note) > 2000:
        raise ValueError('Choose a playtest outcome and a note of at most 2000 characters')
    note = note.strip()
    if outcome == 'problem' and not note:
        raise ValueError('Describe the problem and how to reproduce it')
    if not isinstance(observations, list) or len(observations) > 5:
        raise ValueError('At most five browser observations are allowed')
    for item in observations:
        if (not isinstance(item, dict) or set(item) != {'kind', 'message'} or
                item['kind'] not in ('error', 'rejection') or not isinstance(item['message'], str) or len(item['message']) > 300):
            raise ValueError('Invalid browser observation')
    body = dict(report_id=report_id, request_ref=request_ref, outcome=outcome, note=note, observations=observations)
    with exclusive(folder / 'build.lock'):
        h = chat_build.harness(folder)
        previous = next((e for e in h._entries() if e['kind'] == 'chat_playtest_recorded' and e['report_id'] == report_id), None)
        if previous:
            if any(previous[k] != value for k, value in body.items()):
                raise ValueError('Playtest ID already belongs to a different report')
            return previous
        verified = chat_build.verify(root, folder)
        latest = chat_build.status(root, folder)['completed'][-1]
        if request_ref != latest['request_ref']:
            raise ValueError('This preview is stale; open the current build before recording a playtest')
        with h._lock():
            return h._append('chat_playtest_recorded', **body, manifest=verified['manifest'],
                             basis='human_playtest', browser_observations_trusted=False)
