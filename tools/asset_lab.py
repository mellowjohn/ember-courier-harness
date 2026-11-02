"""Bundle the optional offline runtime or prepare a Blender export for review."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ember_harness import asset_workshop


def bundle(output, modules):
    modules, output = modules.resolve(), output.resolve()
    for name, version in [('three', '0.187.0'), ('esbuild', '0.28.2')]:
        if json.loads((modules/name/'package.json').read_text())['version'] != version:
            raise ValueError('Install the pinned optional asset tools from docs/ASSET_PIPELINE.md')
    if output.exists(): raise ValueError('Choose a new runtime output; existing artifacts are preserved')
    output.parent.mkdir(parents=True, exist_ok=True)
    script = "require(process.argv[1]).buildSync({entryPoints:[process.argv[2]],outfile:process.argv[3],bundle:true,minify:true,format:'iife',legalComments:'inline',nodePaths:[process.argv[4]]})"
    subprocess.run([shutil.which('node') or 'node', '-e', script, str(modules/'esbuild'),
        str(asset_workshop.TEMPLATES/'engine_entry.js'), str(output), str(modules)], check=True)
    # Retain the full upstream licence with the distributed runtime.
    license_text=(modules/'three'/'LICENSE').read_text(encoding='utf-8')
    output.write_text('/*\n'+license_text+'\n*/\n'+output.read_text(encoding='utf-8'), encoding='utf-8')
    print('Bundled offline engine: '+str(output))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--session')
    parser.add_argument('--bundle-runtime', action='store_true')
    parser.add_argument('--modules', type=Path, default=ROOT/'.harness/asset-tools/node_modules')
    args=parser.parse_args()
    if args.bundle_runtime: bundle(args.engine,args.modules)
    if args.source: print(json.dumps(asset_workshop.prepare(ROOT,args.source,args.engine,session_id=args.session),indent=2))
    elif not args.bundle_runtime: parser.error('--source or --bundle-runtime is required')


if __name__=='__main__': main()
