"""Offline profile, exact acceptance, restoration and export regressions."""
from base64 import b64encode
from contextlib import redirect_stdout
from copy import deepcopy
from hashlib import sha256
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ember_harness import asset_pipeline as assets, chat_build, project_versions
from ember_harness.asset_workshop import plan
from ember_harness.gameplay import validate
from ember_harness.local_ui import App
from ember_harness.owner_review import decide

ROOT=Path(__file__).resolve().parents[1]
SPEC=dict(id='delivery-chest',dimensions_m=[1.2,.8,.8],dimension_tolerance_m=.01,
    required_nodes=['AssetRoot','LidPivot','COLLISION_Chest','Socket_Delivery'],art_direction='Original teal and brass chest')
HINGED_SPEC={**SPEC, 'profile':'hinged-prop-v1', 'id':'courier-waygate', 'display_name':'Courier waygate',
    'required_nodes':['AssetRoot','GateHinge','COLLISION_Gate','Socket_Latch'],
    'interaction':dict(pivot_node='GateHinge',axis='y',open_angle_rad=1.8,collision_node='COLLISION_Gate',
        socket_node='Socket_Latch',noun='gate',success_text='Passage open',passage=True)}


def gate_graph(doc):
    doc['nodes'][0]['children']=[2,4]
    doc['nodes'][2].update(name='GateHinge',children=[1,3])
    doc['nodes'][3]['name']='COLLISION_Gate'
    doc['nodes'][4]['name']='Socket_Latch'


def glb(mutate=None):
    blob=struct.pack('<18f3H',-.6,0,-.4,.6,.8,-.4,0,0,.4,0,1,0,0,1,0,0,1,0,0,1,2)
    doc=dict(asset=dict(version='2.0'),buffers=[dict(byteLength=len(blob))],
        bufferViews=[dict(buffer=0,byteOffset=0,byteLength=36),dict(buffer=0,byteOffset=36,byteLength=36),dict(buffer=0,byteOffset=72,byteLength=6)],
        accessors=[dict(bufferView=0,componentType=5126,count=3,type='VEC3'),dict(bufferView=1,componentType=5126,count=3,type='VEC3'),dict(bufferView=2,componentType=5123,count=3,type='SCALAR')],
        materials=[dict(pbrMetallicRoughness=dict(baseColorFactor=[.1,.4,.3,1]))],
        meshes=[dict(primitives=[dict(attributes=dict(POSITION=0,NORMAL=1),indices=2,material=0)])],
        nodes=[dict(name='AssetRoot',children=[1,2,3,4]),dict(name='SM_Chest',mesh=0),dict(name='LidPivot'),
               dict(name='COLLISION_Chest',mesh=0),dict(name='Socket_Delivery',translation=[0,.5,.4])],
        scenes=[dict(nodes=[0])],scene=0)
    if mutate: mutate(doc)
    text=json.dumps(doc,separators=(',',':')).encode();text+=b' '*((-len(text))%4)
    blob+=b'\0'*((-len(blob))%4)
    body=struct.pack('<II',len(text),0x4E4F534A)+text+struct.pack('<II',len(blob),0x004E4942)+blob
    return struct.pack('<4sII',b'glTF',2,len(body)+12)+body


class AssetProfileTests(unittest.TestCase):
    def test_declared_hinge_profile_roundtrip_and_rejects_immovable_proxy(self):
        raw=glb(gate_graph);content=assets.package(raw,HINGED_SPEC)
        decoded,spec,report=assets.unpack(content)
        self.assertEqual(raw,decoded);self.assertEqual(report['profile'],'ember-hinged-prop-v1')
        self.assertEqual(assets.describe(spec)['interaction']['axis'],'y');validate(plan(spec))
        def fixed_proxy(doc):
            gate_graph(doc);doc['nodes'][2]['children']=[1];doc['nodes'][0]['children'].append(3)
        with self.assertRaisesRegex(ValueError,'passage collider'):assets.package(glb(fixed_proxy),HINGED_SPEC)
        def empty_hinge(doc):
            gate_graph(doc);doc['nodes'][2]['children']=[3];doc['nodes'][0]['children'].append(1)
        with self.assertRaisesRegex(ValueError,'visible geometry'):assets.package(glb(empty_hinge),HINGED_SPEC)
        def moving_socket(doc):
            gate_graph(doc);doc['nodes'][0]['children']=[2];doc['nodes'][2]['children'].append(4)
        with self.assertRaisesRegex(ValueError,'interaction socket'):assets.package(glb(moving_socket),HINGED_SPEC)
        static_spec=deepcopy(HINGED_SPEC)
        static_spec['required_nodes'].append('COLLISION_Post')
        static_spec['interaction']['static_collision_nodes']=['COLLISION_Post']
        def static_frame(doc):
            gate_graph(doc);doc['nodes'].append(dict(name='COLLISION_Post',mesh=0));doc['nodes'][0]['children'].append(5)
        report=assets.inspect_glb(glb(static_frame),static_spec)
        self.assertIn('COLLISION_Post',report['static_collision_bounds_m'])
        def moving_frame(doc):
            static_frame(doc);doc['nodes'][0]['children'].remove(5);doc['nodes'][2]['children'].append(5)
        with self.assertRaisesRegex(ValueError,'Static collision'):assets.package(glb(moving_frame),static_spec)

    def test_profile_rejects_unsafe_ids_unsupported_motion_and_undeclared_nodes(self):
        for change in [dict(id='../outside'),dict(profile='unknown'),dict(display_name=''),
                       dict(interaction={**HINGED_SPEC['interaction'],'axis':'xy'}),
                       dict(interaction={**HINGED_SPEC['interaction'],'open_angle_rad':float('nan')}),
                       dict(interaction={**HINGED_SPEC['interaction'],'passage':'true'}),
                       dict(required_nodes=['AssetRoot','GateHinge','COLLISION_Gate','MissingSocket'])]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                assets.package(glb(gate_graph),{**HINGED_SPEC,**change})

    def test_package_roundtrip_and_measurements(self):
        raw=glb();package=assets.package(raw,SPEC)
        decoded,spec,report=assets.unpack(package)
        self.assertEqual(decoded,raw);self.assertEqual(spec,SPEC)
        self.assertEqual(report['sha256'],sha256(raw).hexdigest());self.assertEqual(report['triangles'],1)
        for a,b in zip(report['dimensions_m'],SPEC['dimensions_m']): self.assertAlmostEqual(a,b,places=6)
        validate(plan())

    def test_reject_resources_bad_accessors_repeated_graph_and_missing_pivot(self):
        mutations=[lambda d:d['buffers'][0].update(uri='https://example.invalid/model.bin'),
            lambda d:d['accessors'][0].update(count=1000),
            lambda d:d['nodes'][0]['children'].append(0),
            lambda d:d['nodes'][2].update(name='WrongPivot'),
            lambda d:d.update(extensionsRequired=['KHR_draco_mesh_compression']),
            lambda d:d['nodes'][1].update(translation=[100,0,0])]
        for mutation in mutations:
            with self.subTest(mutation=mutation),self.assertRaises((ValueError,KeyError)):
                assets.inspect_glb(glb(mutation),SPEC)

    def test_reject_header_and_package_tamper(self):
        raw=glb()
        with self.assertRaises(ValueError): assets.inspect_glb(raw[:-1],SPEC)
        package=assets.package(raw,SPEC)
        with self.assertRaises(ValueError): assets.unpack(package.replace('"triangles":1','"triangles":2'))
        with self.assertRaises(ValueError): assets.unpack(package+'alert(1)')
        with self.assertRaises(ValueError): chat_build.validate_files({'index.html':'<html><body></body></html>','asset.js':'alert(1)'})


class AssetAcceptanceTests(unittest.TestCase):
    def setUp(self):
        scratch=ROOT/'.harness/test-temp';scratch.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=scratch);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'examples').mkdir();(self.root/'examples/product_demo.py').touch()
        self.app=App(self.root);self.app.start('SYNTHETIC asset test',chat_only=True)
        self.folder=self.app.sessions_dir/self.app.session['id']
        self.files={'index.html':'<html><body><script src="engine.js"></script><script src="asset.js"></script></body></html>',
                    'engine.js':'/*'+('x'*70000)+'*/','asset.js':assets.package(glb(),SPEC)}

    def propose(self,files=None,turn='initial'):
        files=files or self.files
        with redirect_stdout(io.StringIO()):
            return chat_build.propose_build(self.root,self.folder,turn,'Synthetic GLB fixture',
                dict(title='Asset fixture',summary='Explicit acceptance',files=[dict(path=k,content=v) for k,v in files.items()]),
                expected_before=chat_build.context(self.root,self.folder)['sha256'])

    def test_preview_is_unapplied_then_exact_acceptance_export_and_restore(self):
        ref=self.propose();h=chat_build.harness(self.folder)
        before=h._entries();preview=chat_build.proposal_preview(self.root,self.folder,ref)
        self.assertIn('data:text/javascript;base64,',preview['html']);self.assertEqual(h._entries(),before)
        self.assertFalse(chat_build.project(self.root,self.folder).exists())
        with self.assertRaisesRegex(ValueError,'approval'):chat_build.resume(self.root,self.folder,ref)
        self.app.respond(ref,'approve','SYNTHETIC TEST: Accept asset & play')
        self.assertTrue(chat_build.verify(self.root,self.folder)['passed'])
        accepted=[e for e in h._entries() if e['kind']=='decision' and e.get('action',{}).get('tool')=='asset.accept' and e['decision']=='allow']
        self.assertEqual(len(accepted),1);self.assertEqual(accepted[0]['reason'],'one_time_approval_consumed')
        self.assertEqual(h._entries()[accepted[0]['approval_ref']-1]['scope'],'action')
        data,_=project_versions.export(self.root,self.folder,ref)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:self.assertEqual(archive.read('delivery-chest.glb'),glb())
        spec=deepcopy(SPEC);spec['art_direction']='Original aged teal chest'
        changed={**self.files,'asset.js':assets.package(glb(),spec)}
        second=self.propose(changed,'second');self.app.respond(second,'approve','SYNTHETIC TEST: accept revised asset')
        restore=project_versions.propose_restore(self.root,self.folder,ref,second,'restore-asset-0123456789')
        self.app.respond(restore,'approve','SYNTHETIC TEST: accept restored asset')
        self.assertEqual(project_versions.snapshot(self.root,self.folder,restore)['files'],self.files)
        self.assertTrue(chat_build.verify(self.root,self.folder)['passed'])
        self.assertEqual(len(project_versions.history(self.folder)),3)

    def test_code_revision_does_not_accept_unchanged_asset_and_tamper_blocks_preview(self):
        ref=self.propose();self.app.respond(ref,'approve','SYNTHETIC TEST: accept fixture')
        revised={**self.files,'index.html':self.files['index.html'].replace('<body>','<body>Revision')}
        second=self.propose(revised,'code-only')
        request=chat_build.list_requests(self.folder)[-1]
        self.assertNotIn('asset_actions',request['payload']['body'])
        self.assertEqual(request['payload']['body']['contracts'][0]['contract']['art_direction']['style'],SPEC['art_direction'])
        self.app.respond(second,'approve','SYNTHETIC TEST: code only')
        target=chat_build.project(self.root,self.folder)/'asset.js';target.write_text('changed')
        with self.assertRaisesRegex(ValueError,'changed'):chat_build.preview(self.root,self.folder)
        self.assertEqual(project_versions.snapshot(self.root,self.folder,ref)['files'],self.files)

    def test_a_different_profile_gets_its_own_acceptance_and_named_glb_export(self):
        first=self.propose();self.app.respond(first,'approve','SYNTHETIC TEST: accept chest')
        raw=glb(gate_graph)
        changed={**self.files,'asset.js':assets.package(raw,HINGED_SPEC)}
        second=self.propose(changed,'new-profile')
        packet=chat_build.list_requests(self.folder)[-1]['payload']['body']
        self.assertEqual(packet['build']['asset']['spec']['id'],'courier-waygate')
        self.assertEqual(len(packet['asset_actions']),1)
        self.assertEqual(project_versions.history(self.folder)[-1]['request_ref'],first)
        self.app.respond(second,'approve','SYNTHETIC TEST: accept gate independently')
        archive,_=project_versions.export(self.root,self.folder,second)
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            self.assertEqual(zipped.read('courier-waygate.glb'),raw)
            self.assertNotIn('delivery-chest.glb',zipped.namelist())
        self.assertEqual(project_versions.snapshot(self.root,self.folder,first)['files']['asset.js'],self.files['asset.js'])
        self.assertTrue(chat_build.verify(self.root,self.folder)['passed'])

    def test_missing_individual_receipt_cannot_complete_asset_build(self):
        ref=self.propose()
        # Interrupt between the reviewed contract batch and its individual asset approval.
        with patch('ember_harness.core.Harness.approve_action',side_effect=ValueError('interrupted')):
            with self.assertRaisesRegex(ValueError,'interrupted'):self.app.respond(ref,'approve','SYNTHETIC TEST: interrupted acceptance')
        self.assertFalse(chat_build.project(self.root,self.folder).exists())
        # Retrying the same explicit host response reconciles receipts; no AI approval.
        self.app.respond(ref,'approve','SYNTHETIC TEST: interrupted acceptance')
        self.assertTrue(chat_build.verify(self.root,self.folder)['passed'])


if __name__=='__main__':unittest.main()
