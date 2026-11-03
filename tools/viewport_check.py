"""Inspect an existing browser game's actual stage at common aspect ratios; no AI calls."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ember_harness import chat_build, polish_runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path)
    args = parser.parse_args()
    files = {p.name: p.read_text(encoding='utf-8') for p in args.project.iterdir()
             if p.is_file() and p.suffix in ('.html', '.css', '.js')}
    chat_build.validate_files(files)
    preview = chat_build.ResourcePreview(files)
    preview.feed(files['index.html']); preview.close()
    output = ROOT / '.harness/viewport-checks' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    source = output / 'input.json'
    source.write_text(json.dumps(dict(html=''.join(preview.output),
        aspect_ratios=polish_runtime.ASPECT_RATIOS, review_sheets=True)), encoding='utf-8')
    report = polish_runtime.inspect(polish_runtime.discover(ROOT), source, output/'output', check=lambda: None)
    issues = polish_runtime.aspect_failures(report)
    print(json.dumps(dict(output=str(output), captured=len(report['aspect_ratios']), issues=issues,
        basis='Real Chromium resize captures. Stage fit, artwork distortion and game-state correctness require source and visual review.')))
    return bool(issues)


if __name__ == '__main__':
    sys.exit(main())
