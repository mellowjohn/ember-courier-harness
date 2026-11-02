"""Prepare image-tool requests, import PNG atlases, or build seeded VFX for review."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ember_harness import asset_2d
from ember_harness.asset_library import limited
from ember_harness.core import canonical


write_source = asset_2d.write_source


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    request = commands.add_parser('request', help='Write a tool-ready request; makes no provider call')
    request.add_argument('--spec', type=Path, required=True)
    request.add_argument('--output', type=Path, required=True)
    terrain = commands.add_parser('tileset-request', aliases=['tile-request'],
        help='Prepare a named tile or tileset image request; makes no provider call')
    terrain.add_argument('--id', required=True)
    terrain.add_argument('--tile', action='append', required=True, help='Tile name in row-major order; repeat per cell')
    terrain.add_argument('--solid', action='append', default=[], help='Tile name with a solid collision hint')
    terrain.add_argument('--tile-size', type=int, nargs=2, default=[32, 32], metavar=('WIDTH', 'HEIGHT'))
    terrain.add_argument('--columns', type=int, default=4)
    terrain.add_argument('--style', required=True)
    terrain.add_argument('--tool', choices=['image_gen', 'muse_image'], default='muse_image')
    terrain.add_argument('--no-seamless', action='store_true', help='Allow non-repeating edge and transition artwork')
    terrain.add_argument('--view', choices=['top-down', 'side-view'], help='Terrain camera view; side-view for platformers')
    terrain.add_argument('--output', type=Path, required=True)
    ingest = commands.add_parser('ingest', help='Check returned PNG against the saved image request')
    ingest.add_argument('--request', type=Path, required=True)
    ingest.add_argument('--image', type=Path, required=True)
    ingest.add_argument('--output', type=Path, required=True)
    effect = commands.add_parser('effect', help='Render the deterministic impact recipe locally')
    effect.add_argument('--output', type=Path, required=True)
    effect.add_argument('--spec', type=Path)
    effect.add_argument('--seed', type=int, default=7)
    prepare = commands.add_parser('prepare', help='Create an unapplied workshop proposal for human review')
    prepare.add_argument('--source', type=Path, required=True)
    prepare.add_argument('--session')
    args = parser.parse_args(argv)
    if args.command in ('request', 'tileset-request', 'tile-request'):
        spec = (json.loads(limited(args.spec, 16384)) if args.command == 'request' else
            asset_2d.tileset_spec(args.id, args.tile, style=args.style, tile_size=args.tile_size,
                columns=args.columns, solid=args.solid, seamless=not args.no_seamless, tool=args.tool, view=args.view))
        payload = asset_2d.generation_request(spec)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as stream:
            json.dump(payload, stream, indent=2)
        result = dict(request=str(args.output.resolve()), request_sha256=payload['request_sha256'], status='awaiting_image_tool')
    elif args.command == 'ingest':
        payload = json.loads(limited(args.request, 32768))
        spec = payload['specification']
        # Exact canonical reconstruction rejects edited parameters or mismatched specs.
        if canonical(payload) != canonical(asset_2d.generation_request(spec)):
            raise ValueError('Generation request changed; prepare a new request')
        result = write_source(args.output, limited(args.image, asset_2d.MAX_PNG), spec, payload)
    elif args.command == 'effect':
        spec = json.loads(limited(args.spec, 16384)) if args.spec else asset_2d.effect_spec(seed=args.seed)
        result = write_source(args.output, asset_2d.render_effect(spec), spec)
    else:
        result = asset_2d.prepare(ROOT, args.source, session_id=args.session)
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    main()
