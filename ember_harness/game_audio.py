"""Offline game audio bundled into the same exact review as game code."""
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
import re

RUNTIME = 'ember-audio.js'
INSTRUCTION = (
    'Offline game audio is available through EmberAudio.create(). The host bundles ember-audio.js '
    'ahead of game scripts when source uses EmberAudio; omit this protected file from returned code. '
    'Use one mixer per game. In a Start/click/touch handler, await audio.unlock(); then trigger '
    'audio.play("jump"|"land"|"pickup"|"hit"|"attack"|"footstep"|"win"|"lose"|"ui") '
    'once per actual gameplay event, not every frame. audio.startMusic("courier"|"explore"|"tension") '
    'and audio.startAmbience("wind"|"embers") loop until stopped. '
    'audio.stopMusic(), stopAmbience(), stopAll(), setPaused(boolean), setMuted(boolean), '
    'setVolume("master"|"sfx"|"music"|"ambience",0..1), and dispose() manage lifecycle. '
    'audio.mountControls(element) adds accessible enable, mute and four volume controls. '
    'Custom music: startMusic({bpm:100,steps:[[60,64,67],null,[67],null]}); each step is an eighth note, '
    'null is a rest, up to 64 steps and three MIDI notes (24..96) per step. '
    'Custom effects: tone({frequency:440,endFrequency:220,duration:0.2,type:"sine",gain:0.2,pan:0}). '
    'Never autoplay, require a microphone or fetch audio URLs. Audio is optional; an unsupported or '
    'blocked context returns false and gameplay must continue. Expose mute and volume controls. '
    'Pause audio with gameplay, stop loops at game over/restart, and dispose when leaving the game. '
    'Existing sounds and music should be preserved unless the request changes them. '
)


def source():
    return (Path(__file__).with_name('asset_lab') / RUNTIME).read_text(encoding='utf-8')


def attach(files, basis):
    """Retain approved bytes, adding the runtime only when explicitly used."""
    result = dict(files)
    if not (RUNTIME in basis or RUNTIME in files or any(
            re.search(r'\bEmberAudio\b', value) for name, value in files.items() if name.endswith(('.html', '.js')))):
        return result
    runtime = basis.get(RUNTIME, source())
    if RUNTIME in result and result[RUNTIME] != runtime:
        raise ValueError('Keep the prepared Ember audio runtime unchanged')
    result[RUNTIME] = runtime

    class Scripts(HTMLParser):
        def __init__(self, html):
            super().__init__(); self.html = html; self.first = None; self.start = None; self.spans = []

        def index(self):
            line, col = self.getpos()
            return sum(map(len, self.html.splitlines(keepends=True)[:line - 1])) + col

        def handle_starttag(self, tag, attrs):
            if tag == 'script':
                if self.first is None: self.first = self.index()
                if (dict(attrs).get('src') or '').removeprefix('./') == RUNTIME: self.start = self.index()

        def handle_endtag(self, tag):
            if tag == 'script' and self.start is not None:
                self.spans.append((self.start, self.html.index('>', self.index()) + 1)); self.start = None

    for name, html in list(result.items()):
        if not name.endswith('.html'): continue
        parser = Scripts(html); parser.feed(html); parser.close()
        if parser.start is not None: raise ValueError('Close the audio script tag before game code')
        for start, end in reversed(parser.spans): html = html[:start] + html[end:]
        parser = Scripts(html); parser.feed(html); parser.close()
        index = parser.first
        if index is None:
            end = re.search(r'</body\s*>', html, re.I)
            index = end.start() if end else len(html)
        result[name] = html[:index] + '<script src="'+RUNTIME+'"></script>' + html[index:]
    return result


def prepare_build(build, basis):
    result = deepcopy(build)
    files = {row['path']: row['content'] for row in result['files']}
    if len(files) != len(result['files']): raise ValueError('Duplicate proposed file paths')
    result['files'] = [dict(path=name, content=value) for name, value in attach(files, basis).items()]
    return result


def demo_files():
    folder = Path(__file__).with_name('asset_lab')
    return attach({name: (folder / ('audio_' + name)).read_text(encoding='utf-8')
                   for name in ('index.html', 'app.js')}, {})
