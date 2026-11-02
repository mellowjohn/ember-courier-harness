"""Bounded, offline GLB and PNG packages carried by reviewed JavaScript files.

This is an Ember static-prop profile, not a complete glTF conformance validator.
"""
from base64 import b64decode, b64encode
from hashlib import sha256
import json
import math
import re
import struct

from .core import canonical

MAX_GLB = 360_000
PREFIX = 'globalThis.EMBER_ASSET = Object.freeze('
SUFFIX = ');\n'


def describe(spec):
    """Resolve versioned interaction metadata; old chest packages stay byte-compatible."""
    if isinstance(spec, dict) and spec.get('profile') == 'sprite-atlas-v1':
        from . import asset_2d
        return asset_2d.describe(spec)
    common = {'id', 'dimensions_m', 'dimension_tolerance_m', 'required_nodes', 'art_direction'}
    if not isinstance(spec, dict): raise ValueError('A complete asset specification is required')
    legacy = 'profile' not in spec
    expected = common if legacy else common | {'profile', 'display_name', 'interaction'}
    if set(spec) != expected: raise ValueError('A complete asset specification is required')
    if not isinstance(spec['id'], str) or not re.fullmatch('[a-z][a-z0-9]*(?:-[a-z0-9]+)*', spec['id']) or len(spec['id']) > 64:
        raise ValueError('Use a bounded lowercase asset slug')
    if not isinstance(spec['art_direction'], str) or not 1 <= len(spec['art_direction']) <= 2000:
        raise ValueError('Invalid asset direction')
    if legacy:
        if spec['id'] != 'delivery-chest': raise ValueError('Other assets require an explicit hinged-prop-v1 profile')
        name = 'Delivery chest'
        interaction = dict(pivot_node='LidPivot', axis='x', open_angle_rad=-1.85,
            collision_node='COLLISION_Chest', socket_node='Socket_Delivery', noun='chest',
            success_text='Delivery complete', passage=False)
    else:
        if spec['profile'] != 'hinged-prop-v1': raise ValueError('Unsupported asset profile')
        name, interaction = spec['display_name'], spec['interaction']
        fields = {'pivot_node', 'axis', 'open_angle_rad', 'collision_node', 'socket_node', 'noun', 'success_text', 'passage'}
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError('Use a display name of 1–80 characters')
        if not isinstance(interaction, dict) or set(interaction) not in (fields, fields | {'static_collision_nodes'}):
            raise ValueError('Declare a complete hinged prop interaction')
        for field in ('pivot_node', 'collision_node', 'socket_node'):
            if not isinstance(interaction[field], str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_.-]{0,79}', interaction[field]):
                raise ValueError('Use exact bounded node names')
        if not interaction['collision_node'].startswith('COLLISION_') or not interaction['socket_node'].startswith('Socket_'):
            raise ValueError('Use separate COLLISION_ and Socket_ helper nodes')
        if interaction['axis'] not in ('x', 'y', 'z') or type(interaction['open_angle_rad']) not in (int, float) or not .25 <= abs(interaction['open_angle_rad']) <= 3:
            raise ValueError('Use a supported hinge axis and angle of 0.25–3 radians')
        if type(interaction['passage']) is not bool:
            raise ValueError('Declare whether opening creates a passage')
        for field, limit in [('noun', 24), ('success_text', 80)]:
            if not isinstance(interaction[field], str) or not 1 <= len(interaction[field].strip()) <= limit:
                raise ValueError('Invalid interaction wording')
    statics = interaction.get('static_collision_nodes', [])
    if (not isinstance(statics, list) or len(statics) > 8 or any(not isinstance(n,str) or
            not re.fullmatch('COLLISION_[A-Za-z0-9_.-]{1,69}',n) for n in statics)):
        raise ValueError('Declare at most eight named static collision proxies')
    required = spec['required_nodes']
    declared = {'AssetRoot', interaction['pivot_node'], interaction['collision_node'], interaction['socket_node'], *statics}
    if (len(declared) != 4 + len(statics) or not isinstance(required, list) or len(required) != len(declared) or
            not all(isinstance(n, str) for n in required) or set(required) != declared):
        raise ValueError('Declare distinct root, pivot, collision and socket nodes')
    dims, tolerance = spec['dimensions_m'], spec['dimension_tolerance_m']
    if not isinstance(dims, list) or len(dims) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 < v <= 10 for v in dims) or type(tolerance) not in (int, float) or not 0 < tolerance <= .05:
        raise ValueError('Invalid dimension specification')
    return dict(id=spec['id'], display_name=name, interaction=dict(interaction),
                profile='ember-static-prop-v1' if legacy else 'ember-hinged-prop-v1')


def inspect_glb(raw, spec):
    descriptor = describe(spec)
    interaction = descriptor['interaction']
    if not isinstance(raw, bytes) or not 28 <= len(raw) <= MAX_GLB:
        raise ValueError('GLB exceeds the bounded prop profile')
    magic, version, length = struct.unpack_from('<4sII', raw)
    if magic != b'glTF' or version != 2 or length != len(raw):
        raise ValueError('Invalid GLB header or length')
    chunks, offset = [], 12
    while offset < length:
        if offset + 8 > length:
            raise ValueError('Truncated GLB chunk')
        size, kind = struct.unpack_from('<II', raw, offset)
        offset += 8
        if size % 4 or offset + size > length:
            raise ValueError('Invalid GLB chunk bounds')
        chunks.append((kind, raw[offset:offset + size])); offset += size
    if [c[0] for c in chunks] != [0x4E4F534A, 0x004E4942]:
        raise ValueError('Use one JSON chunk and one embedded BIN chunk')
    try:
        doc = json.loads(chunks[0][1], parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('Invalid GLB JSON') from error
    blob = chunks[1][1]
    def no_resources(value):
        if isinstance(value, dict):
            if 'uri' in value or 'extensions' in value:
                raise ValueError('External resources and extensions are outside the offline prop profile')
            for v in value.values(): no_resources(v)
        elif isinstance(value, list):
            for v in value: no_resources(v)
    no_resources(doc)
    if doc.get('asset', {}).get('version') != '2.0' or any(doc.get(k) for k in ('skins', 'animations', 'images', 'textures', 'extensionsRequired')):
        raise ValueError('Use static glTF 2.0 meshes and factor materials without textures or clips')
    buffers = doc.get('buffers', [])
    if len(buffers) != 1 or type(buffers[0].get('byteLength')) is not int or not len(blob) - 3 <= buffers[0]['byteLength'] <= len(blob):
        raise ValueError('Invalid embedded buffer length')
    def integer(value, upper):
        if type(value) is not int or not 0 <= value < upper:
            raise ValueError('Invalid GLB reference')
        return value
    views, accessors = doc.get('bufferViews', []), doc.get('accessors', [])
    for view in views:
        if view.get('buffer') != 0:
            raise ValueError('Invalid GLB buffer reference')
        start, size = view.get('byteOffset', 0), view.get('byteLength')
        if type(start) is not int or type(size) is not int or min(start, size) < 0 or start + size > buffers[0]['byteLength']:
            raise ValueError('Buffer view escapes embedded bytes')
    decoded, decoded_count = {}, 0
    def values(index, expected=None):
        nonlocal decoded_count
        a = accessors[integer(index, len(accessors))]
        if 'sparse' in a or a.get('normalized'):
            raise ValueError('Sparse and normalized accessors are outside this profile')
        formats = {5121: ('B', 1), 5123: ('H', 2), 5125: ('I', 4), 5126: ('f', 4)}
        counts = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}
        if a.get('componentType') not in formats or a.get('type') not in counts or (expected and (a['componentType'], a['type']) != expected):
            raise ValueError('Unsupported GLB accessor format')
        if index in decoded: return decoded[index]
        fmt, size = formats[a['componentType']]; width = counts[a['type']]
        view = views[integer(a.get('bufferView'), len(views))]
        count, start, stride = a.get('count'), a.get('byteOffset', 0), view.get('byteStride', size * width)
        if type(count) is not int or not 1 <= count <= 100_000 or type(start) is not int or start < 0 or type(stride) is not int or stride < size * width or stride > 252:
            raise ValueError('Invalid GLB accessor bounds')
        if start % size or stride % size or start + (count - 1) * stride + size * width > view['byteLength']:
            raise ValueError('Accessor escapes buffer view')
        decoded_count += count
        if decoded_count > 150_000: raise ValueError('Prop exceeds decoded geometry budget')
        result = [struct.unpack_from('<' + fmt * width, blob, view.get('byteOffset', 0) + start + i * stride) for i in range(count)]
        if any(not math.isfinite(v) for row in result for v in row):
            raise ValueError('Nonfinite geometry')
        decoded[index] = result
        return result
    materials, meshes, nodes = doc.get('materials', []), doc.get('meshes', []), doc.get('nodes', [])
    if not 1 <= len(meshes) <= 128 or not 1 <= len(nodes) <= 160 or not 1 <= len(materials) <= 8:
        raise ValueError('Prop exceeds mesh, node or material budget')
    for mat in materials:
        pbr = mat.get('pbrMetallicRoughness', {})
        color = pbr.get('baseColorFactor', [1, 1, 1, 1])
        if len(color) != 4 or any(type(v) not in (int, float) or not 0 <= v <= 1 for v in color):
            raise ValueError('Invalid base color')
    positions, triangles = {}, 0
    for mi, mesh in enumerate(meshes):
        points = []
        for p in mesh.get('primitives', []):
            if p.get('mode', 4) != 4 or p.get('targets'):
                raise ValueError('Use triangle primitives without morph targets')
            integer(p.get('material'), len(materials))
            attrs = p.get('attributes', {})
            pos = values(attrs.get('POSITION'), (5126, 'VEC3'))
            normals = values(attrs.get('NORMAL'), (5126, 'VEC3'))
            if len(normals) != len(pos): raise ValueError('Normals do not match positions')
            indices = values(p['indices']) if 'indices' in p else [(i,) for i in range(len(pos))]
            if 'indices' in p and (accessors[p['indices']]['type'] != 'SCALAR' or accessors[p['indices']]['componentType'] not in (5121, 5123, 5125)):
                raise ValueError('Invalid index accessor')
            if len(indices) % 3 or any(i[0] >= len(pos) for i in indices):
                raise ValueError('Invalid triangle indices')
            triangles += len(indices) // 3; points.extend(pos)
            if triangles > 12_000 or len(points) > 100_000:
                raise ValueError('Prop exceeds triangle or vertex budget')
        if not points: raise ValueError('Empty mesh')
        positions[mi] = points
    if triangles > 12_000: raise ValueError('Prop exceeds 12000 triangles')
    names = [n.get('name', '') for n in nodes]
    if len(names) != len(set(names)) or any(not n for n in names):
        raise ValueError('Use unique named nodes')
    required = spec['required_nodes']
    if not set(required) <= set(names):
        raise ValueError('Required pivot, collision or socket nodes are missing')
    dims, tolerance = spec['dimensions_m'], spec['dimension_tolerance_m']
    def multiply(a, b):
        return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]
    identity = [[int(r == c) for c in range(4)] for r in range(4)]
    def transform(n):
        if 'matrix' in n:
            m = n['matrix']
            if len(m) != 16: raise ValueError('Invalid node matrix')
            result = [[m[c * 4 + r] for c in range(4)] for r in range(4)]
        else:
            t, s, q = n.get('translation', [0, 0, 0]), n.get('scale', [1, 1, 1]), n.get('rotation', [0, 0, 0, 1])
            if len(t) != 3 or len(s) != 3 or len(q) != 4: raise ValueError('Invalid node transform')
            x,y,z,w = q
            result = [[(1-2*y*y-2*z*z)*s[0], (2*x*y-2*z*w)*s[1], (2*x*z+2*y*w)*s[2], t[0]],
                      [(2*x*y+2*z*w)*s[0], (1-2*x*x-2*z*z)*s[1], (2*y*z-2*x*w)*s[2], t[1]],
                      [(2*x*z-2*y*w)*s[0], (2*y*z+2*x*w)*s[1], (1-2*x*x-2*y*y)*s[2], t[2]], [0,0,0,1]]
        if any(type(v) not in (int,float) or not math.isfinite(v) for row in result for v in row):
            raise ValueError('Nonfinite node transform')
        return result
    seen, visible, bounds, parents = set(), [], {}, {}
    world_vertices = 0
    def visit(index, parent, depth=0, helper=False):
        nonlocal world_vertices
        integer(index, len(nodes))
        if index in seen or depth > 32: raise ValueError('Node graph has repeated nodes or excessive depth')
        seen.add(index); n = nodes[index]; world = multiply(parent, transform(n))
        helper = helper or n['name'].startswith(('COLLISION_', 'Socket_'))
        pts = []
        if 'mesh' in n:
            local_points = positions[integer(n['mesh'], len(meshes))]
            world_vertices += len(local_points)
            if world_vertices > 100_000: raise ValueError('Prop exceeds world vertex budget')
            for p in local_points:
                pts.append([sum(world[r][c]*p[c] for c in range(3)) + world[r][3] for r in range(3)])
            bounds[n['name']] = [[min(p[a] for p in pts) for a in range(3)], [max(p[a] for p in pts) for a in range(3)]]
            if not helper: visible.extend(pts)
        for child in n.get('children', []):
            integer(child, len(nodes)); parents[child] = index
            visit(child, world, depth + 1, helper)
    scenes = doc.get('scenes', [])
    scene = scenes[integer(doc.get('scene', 0), len(scenes))]
    for root in scene.get('nodes', []): visit(root, identity)
    if len(seen) != len(nodes) or not visible or interaction['collision_node'] not in bounds:
        raise ValueError('Unreachable nodes, missing geometry or missing collision mesh')
    if descriptor['profile'] == 'ember-hinged-prop-v1':
        pivot = names.index(interaction['pivot_node'])
        def below(index, ancestor):
            while index in parents:
                index = parents[index]
                if index == ancestor: return True
            return False
        root = names.index('AssetRoot')
        if root in parents or any(not below(i, root) for i in seen if i != root):
            raise ValueError('All prop nodes must belong to AssetRoot')
        if not any(below(i, pivot) and 'mesh' in n and not n['name'].startswith(('COLLISION_', 'Socket_')) for i,n in enumerate(nodes)):
            raise ValueError('The declared hinge must move visible geometry')
        if interaction['passage'] and not below(names.index(interaction['collision_node']), pivot):
            raise ValueError('A passage collider must move with its hinge')
        if below(names.index(interaction['socket_node']), pivot):
            raise ValueError('Keep the interaction socket outside the moving hinge')
        for name in interaction.get('static_collision_nodes', []):
            if name not in bounds or below(names.index(name), pivot):
                raise ValueError('Static collision proxies need meshes outside the moving hinge')
    low = [min(p[a] for p in visible) for a in range(3)]; high = [max(p[a] for p in visible) for a in range(3)]
    actual = [high[a]-low[a] for a in range(3)]
    if (any(abs(a-b) > tolerance for a,b in zip(actual,dims)) or abs(low[1]) > tolerance or
            abs((high[0]+low[0])/2) > tolerance or abs((high[2]+low[2])/2) > .05):
        raise ValueError('Exported dimensions or floor alignment differ from the specification')
    report = dict(profile=descriptor['profile'], sha256=sha256(raw).hexdigest(), bytes=len(raw),
                triangles=triangles, materials=len(materials), nodes=names, dimensions_m=actual,
                bounds_m=[low, high], collision_bounds_m=bounds[interaction['collision_node']],
                basis='Structural and dimensional checks only; visual judgment and human acceptance remain separate')
    if interaction.get('static_collision_nodes'):
        report['static_collision_bounds_m'] = {name:bounds[name] for name in interaction['static_collision_nodes']}
    return report


def package(raw, spec):
    if isinstance(spec, dict) and spec.get('profile') == 'sprite-atlas-v1':
        from . import asset_2d
        return asset_2d.package(raw, spec)
    report = inspect_glb(raw, spec)
    data = dict(spec=spec, report=report, glb_base64=b64encode(raw).decode('ascii'))
    return PREFIX + canonical(data).decode('utf-8') + SUFFIX


def unpack(content):
    if not isinstance(content, str) or not content.startswith(PREFIX) or not content.endswith(SUFFIX):
        raise ValueError('asset.js must be a canonical Ember asset package')
    try:
        data = json.loads(content[len(PREFIX):-len(SUFFIX)])
        if not isinstance(data, dict): raise ValueError('Invalid asset package')
        if isinstance(data.get('spec'), dict) and data['spec'].get('profile') == 'sprite-atlas-v1':
            from . import asset_2d
            return asset_2d.unpack(content)
        raw = b64decode(data['glb_base64'], validate=True)
        report = inspect_glb(raw, data['spec'])
    except (KeyError, TypeError, UnicodeError) as error:
        raise ValueError('Invalid asset package') from error
    if data.get('report') != report or package(raw, data['spec']) != content:
        raise ValueError('Asset package measurements or bytes changed')
    return raw, data['spec'], report
