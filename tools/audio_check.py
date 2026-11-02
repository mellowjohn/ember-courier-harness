"""Build an offline sound demo and optionally verify real Chromium audio signals."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ember_harness import chat_build, game_audio, polish_runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo-only', action='store_true', help='Write the playable demo without Chromium checks')
    args = parser.parse_args()
    output = ROOT / '.harness/audio-checks' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    files = game_audio.demo_files(); chat_build.validate_files(files)
    for name, content in files.items(): (output/name).write_text(content, encoding='utf-8')
    # One shareable local HTML file also exercises Ember's actual preview embedding.
    preview = chat_build.ResourcePreview(files); preview.feed(files['index.html']); preview.close()
    (output/'sound-garden.html').write_text(''.join(preview.output),encoding='utf-8')
    if not args.demo_only:
        runtime = polish_runtime.discover(ROOT, fingerprints=False)
        env = dict(os.environ, EMBER_PLAYWRIGHT_MODULE=runtime['module'], EMBER_BROWSER_EXECUTABLE=runtime['browser'])
        result = subprocess.run([runtime['node'], str(ROOT/'tools/audio_check.js'), str(output)],env=env,
                                capture_output=True,text=True,timeout=90)
        (output/'browser.log').write_text(result.stdout+result.stderr,encoding='utf-8')
        if result.returncode: raise RuntimeError(result.stdout+result.stderr)
        print(result.stdout.strip())
    print(json.dumps(dict(demo=str(output/'sound-garden.html'),output=str(output)),indent=2))


if __name__ == '__main__':main()
