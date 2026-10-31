"""Bounded browser smoke observations; never gameplay proof or action authority."""
import re
import secrets

from . import chat_build
from .recovery import exclusive

METRICS = ('loaded', 'animation_frame', 'inputs_sent', 'button_clicked', 'completed')
OBSERVATION_KINDS = ('error', 'rejection', 'policy', 'runner')
PLAN = 'startup-inputs-v1'
LIMIT = ('Browser observations can be influenced by generated code. Synthetic inputs do not '
         'prove controls work, game rules are correct, or a human playtest passed.')

# Installed before generated scripts, inside the same opaque-origin sandbox as the game.
# The parent checks the source frame/channel and enforces its own timeout.
RUNNER = """<script>(()=>{
const channel=CHANNEL,send=parent.postMessage.bind(parent),later=setTimeout.bind(window),raf=requestAnimationFrame.bind(window);
const metrics={loaded:false,animation_frame:false,inputs_sent:false,button_clicked:false,completed:false};
let count=0;
const post=(kind,extra={})=>send({emberSmoke:channel,kind,...extra},'*');
const observe=(kind,message)=>{if(count++<5)post(kind,{message:String(message).slice(0,300)})};
addEventListener('error',e=>observe('error',e.message||'A resource failed to load'),true);
addEventListener('unhandledrejection',e=>{let text='Unhandled promise rejection';try{text=String(e.reason)}catch{}observe('rejection',text)});
addEventListener('securitypolicyviolation',e=>observe('policy','Blocked by preview policy: '+e.effectiveDirective));
const progress=()=>post('progress',{metrics:{...metrics}});
const pause=ms=>new Promise(resolve=>later(resolve,ms));
addEventListener('load',async()=>{try{
  metrics.loaded=true;progress();
  await new Promise(resolve=>raf(resolve));metrics.animation_frame=true;progress();
  const button=document.querySelector('button:not(:disabled)');
  if(button){button.click();metrics.button_clicked=true;progress()}
  for(const [key,code] of [['ArrowLeft','ArrowLeft'],['ArrowUp','ArrowUp'],['ArrowRight','ArrowRight'],['ArrowDown','ArrowDown'],[' ','Space']]){
    const target=document.activeElement||document.body;
    target.dispatchEvent(new KeyboardEvent('keydown',{key,code,bubbles:true}));
    await pause(100);
    target.dispatchEvent(new KeyboardEvent('keyup',{key,code,bubbles:true}));
  }
  metrics.inputs_sent=true;progress();await pause(750);
  metrics.completed=true;post('done',{metrics:{...metrics}});
}catch(error){observe('runner',error);post('done',{metrics:{...metrics}})}},{once:true});
})();</script>"""


def preview(root, folder):
    with exclusive(folder / 'build.lock'):
        chat_build.verify(root, folder)
        html = chat_build.preview(root, folder)
        last = chat_build.status(root, folder)['completed'][-1]
        channel = secrets.token_hex(16)
        return dict(html=RUNNER.replace('CHANNEL', '"' + channel + '"') + html,
                    channel=channel, request_ref=last['request_ref'], plan=PLAN)


def reports(folder):
    if not (folder / 'build-authority').exists():
        return []
    return [e for e in chat_build.harness(folder)._entries() if e['kind'] == 'chat_smoke_recorded'][-20:]


def record(root, folder, report_id, request_ref, metrics, observations):
    if not isinstance(report_id, str) or not re.fullmatch('[a-zA-Z0-9-]{16,64}', report_id):
        raise ValueError('A stable browser check ID is required')
    if (not isinstance(metrics, dict) or set(metrics) != set(METRICS) or
            any(type(value) is not bool for value in metrics.values())):
        raise ValueError('Invalid browser check measurements')
    if not isinstance(observations, list) or len(observations) > 5:
        raise ValueError('At most five browser observations are allowed')
    for item in observations:
        if (not isinstance(item, dict) or set(item) != {'kind', 'message'} or
                item['kind'] not in OBSERVATION_KINDS or not isinstance(item['message'], str) or len(item['message']) > 300):
            raise ValueError('Invalid browser observation')
    complete = all(metrics[key] for key in METRICS if key != 'button_clicked')
    outcome = 'issues_observed' if observations else 'no_errors_observed' if complete else 'incomplete'
    body = dict(report_id=report_id, request_ref=request_ref, plan=PLAN, metrics=metrics,
                observations=observations, outcome=outcome)
    with exclusive(folder / 'build.lock'):
        h = chat_build.harness(folder)
        previous = next((e for e in h._entries() if e['kind'] == 'chat_smoke_recorded' and e['report_id'] == report_id), None)
        if previous:
            if any(previous[key] != value for key, value in body.items()):
                raise ValueError('Browser check ID already belongs to a different report')
            return previous
        verified = chat_build.verify(root, folder)
        last = chat_build.status(root, folder)['completed'][-1]
        if request_ref != last['request_ref']:
            raise ValueError('This browser check is stale; run it against the current build')
        with h._lock():
            return h._append('chat_smoke_recorded', **body, manifest=verified['manifest'],
                             basis='untrusted_browser_smoke', observations_trusted=False, limit=LIMIT)


def context(root, folder):
    state = chat_build.status(root, folder)
    if not state['completed'] or state['resumable']:
        return []
    last = state['completed'][-1]
    if chat_build.context(root, folder)['manifest'] != last.get('manifest', {'index.html': last['sha256']}):
        return []
    return [dict(report_id=e['report_id'], plan=e['plan'], outcome=e['outcome'], metrics=e['metrics'],
                 observations=e['observations'], basis=e['basis'], limit=LIMIT)
            for e in reports(folder) if e['request_ref'] == last['request_ref']][-5:]
