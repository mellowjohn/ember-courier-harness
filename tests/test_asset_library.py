"""Known source locations and exact asset selection through durable conversation."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ember_harness import asset_library, asset_pipeline, chat_build, gameplay, session_chat, project_versions, project_brief
from ember_harness.local_ui import App
from ember_harness.recovery import atomic_json
from test_asset_pipeline import SPEC, HINGED_SPEC, glb, gate_graph, ROOT


class AssetLibraryTests(unittest.TestCase):
    def setUp(self):
        quality=patch('ember_harness.proposal_quality.run',return_value=dict(status='unavailable',issues=['SYNTHETIC: verification tested separately']))
        quality.start();self.addCleanup(quality.stop)
        scratch=ROOT/'.harness/test-temp';scratch.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=scratch);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'examples').mkdir();(self.root/'examples/product_demo.py').touch()
        self.chest=self.source('chest',SPEC,glb())
        self.gate=self.source('gate',HINGED_SPEC,glb(gate_graph))
        runtime=self.root/'.harness/asset-tools/engine.js';runtime.parent.mkdir(parents=True)
        runtime.write_text('/* SYNTHETIC runtime, not executed by unit tests */',encoding='utf-8')
        self.app=App(self.root);self.app.start('SYNTHETIC asset conversation',chat_only=True)
        self.folder=self.app.sessions_dir/self.app.session['id'];self.prompts=[]

    def source(self,name,spec,raw):
        folder=self.root/'.harness/asset-source'/name;folder.mkdir(parents=True)
        (folder/'asset-spec.json').write_text(json.dumps(spec),encoding='utf-8')
        (folder/(spec['id']+'.glb')).write_bytes(raw)
        (folder/(spec['id']+'.blend')).write_bytes(b'SYNTHETIC native source; never executed')
        return folder

    def chat(self,text,reply,turn):
        def provider(root,folder,prompt,request_id,**kw):
            data=json.loads(prompt.split('\n',1)[1]);self.prompts.append(data)
            result=reply(data) if callable(reply) else reply
            return dict(response=json.dumps(result))
        with patch('ember_harness.session_chat.run_muse',side_effect=provider),redirect_stdout(io.StringIO()):
            self.app.chat(text,turn)
        return session_chat.transcript(self.folder)[-1]

    def discuss(self):
        def reply(data):
            row=next(a for a in data['asset_library']['assets'] if a['id']=='courier-waygate')
            self.assertEqual(row['sources']['blender']['path'],str(self.gate/'courier-waygate.blend'))
            return dict(message='The recorded gate source is '+row['sources']['blender']['path'],build=None,
                        asset=dict(ref=row['ref'],intent='discuss'))
        return self.chat('Where is the courier gate source?',reply,'discuss-gate-00001')

    def use_focused(self,turn='use-focused-00001'):
        return self.chat('Put it into the scene.',lambda d:dict(message='Review this recorded asset proposal.',build=None,
            asset=dict(ref=d['asset_library']['focus_ref'],intent='use')),turn)

    def approved_gate(self):
        self.discuss();used=self.use_focused()
        self.app.respond(used['proposal_ref'],'approve','SYNTHETIC TEST: initial gate acceptance')
        return used['asset_ref'],used['proposal_ref']

    def reexport_gate(self):
        raw=glb(lambda d:(gate_graph(d),d['materials'][0]['pbrMetallicRoughness'].update(baseColorFactor=[.2,.5,.3,1])))
        (self.gate/'courier-waygate.glb').write_bytes(raw)
        return raw

    def update(self,asset_ref,current_ref):
        with redirect_stdout(io.StringIO()):
            return self.app.review_asset_update(self.folder.name,asset_ref,current_ref)

    def test_updated_export_preserves_scene_plan_and_requires_separate_acceptance(self):
        asset_ref,current_ref=self.approved_gate()
        # Keep a real scene refinement when the geometry is re-exported.
        files=project_versions.snapshot(self.root,self.folder,current_ref)['files']
        files['style.css']+='\n/* SYNTHETIC approved custom lighting */'
        with redirect_stdout(io.StringIO()):
            current_ref=chat_build.propose_build(self.root,self.folder,'custom-scene-0001','SYNTHETIC scene edit',
                dict(title='Custom scene',summary='Preserve this scene',files=[dict(path=k,content=v) for k,v in files.items()]),
                expected_before=chat_build.context(self.root,self.folder)['sha256'])
        self.app.respond(current_ref,'approve','SYNTHETIC TEST: scene edit')
        before=chat_build.context(self.root,self.folder);plan=gameplay.load(self.folder);brief=project_brief.load(self.folder)
        raw=self.reexport_gate();result=self.update(asset_ref,current_ref)
        self.assertEqual(result['status'],'awaiting_review')
        proposed=chat_build.proposal_snapshot(self.root,self.folder,result['request_ref'])['files']
        self.assertEqual(asset_pipeline.unpack(proposed['asset.js'])[0],raw)
        self.assertEqual({k:v for k,v in proposed.items() if k!='asset.js'}, {k:v for k,v in files.items() if k!='asset.js'})
        self.assertEqual(chat_build.context(self.root,self.folder),before)
        request=chat_build.list_requests(self.folder)[-1]
        self.assertEqual([f['name'] for f in request['payload']['body']['build']['files']],['asset.js'])
        self.assertEqual(len(request['payload']['body']['asset_actions']),1)
        self.assertIsNone(request['decision'])
        self.assertEqual(gameplay.load(self.folder),plan);self.assertEqual(project_brief.load(self.folder),brief)
        self.assertEqual(self.app.snapshot()['asset_library']['focus_ref'],result['asset_ref'])
        fresh=App(self.root);fresh.resume(self.folder.name)
        with redirect_stdout(io.StringIO()):again=fresh.review_asset_update(self.folder.name,asset_ref,current_ref)
        self.assertEqual(again['request_ref'],result['request_ref'])
        self.assertEqual(len([m for m in session_chat.transcript(self.folder) if m['id'].startswith('asset-update-')]),1)
        fresh.respond(result['request_ref'],'approve','SYNTHETIC TEST: separate updated-asset acceptance')
        self.assertEqual(asset_pipeline.unpack(project_versions.snapshot(self.root,self.folder,result['request_ref'])['files']['asset.js'])[0],raw)
        self.assertEqual(asset_library.load(self.root,asset_ref)[0]['package'],files['asset.js'])
        receipts=[e for e in chat_build.harness(self.folder)._entries() if e['kind']=='decision' and e.get('decision')=='allow' and e.get('action',{}).get('tool')=='asset.accept']
        self.assertEqual(len(receipts),2)

    def test_native_only_changes_do_not_propose_an_unchanged_export(self):
        asset_ref,current_ref=self.approved_gate()
        (self.gate/'courier-waygate.blend').write_bytes(b'Changed native source, no GLB export')
        result=self.update(asset_ref,current_ref)
        self.assertEqual(result['status'],'unchanged');self.assertNotIn('request_ref',result)
        self.assertEqual(len(chat_build.list_requests(self.folder)),1)

    def test_current_source_stays_bound_when_an_identical_copy_is_registered(self):
        asset_ref,current_ref=self.approved_gate()
        duplicate=self.source('other-directory',HINGED_SPEC,glb(gate_graph))
        other=asset_library.register(self.root,duplicate)
        self.assertNotEqual(asset_ref,other)
        self.assertEqual(self.app.snapshot()['asset_library']['current_ref'],asset_ref)
        with self.assertRaisesRegex(ValueError,'asset used'):self.update(other,current_ref)
        self.reexport_gate();result=self.update(asset_ref,current_ref)
        self.assertEqual(asset_library.load(self.root,result['asset_ref'])[0]['sources']['export']['path'],str(self.gate/'courier-waygate.glb'))

    def test_invalid_missing_and_renamed_exports_preserve_approved_scene(self):
        asset_ref,current_ref=self.approved_gate();before=chat_build.context(self.root,self.folder)
        path=self.gate/'courier-waygate.glb';path.write_bytes(b'invalid export')
        with self.assertRaises(ValueError):self.update(asset_ref,current_ref)
        path.unlink()
        with self.assertRaises(OSError):self.update(asset_ref,current_ref)
        renamed=deepcopy(HINGED_SPEC);renamed['id']='different-gate'
        (self.gate/'asset-spec.json').write_text(json.dumps(renamed))
        (self.gate/'different-gate.glb').write_bytes(glb(gate_graph))
        with self.assertRaisesRegex(ValueError,'identity'):self.update(asset_ref,current_ref)
        self.assertEqual(chat_build.context(self.root,self.folder),before)
        self.assertEqual(len(chat_build.list_requests(self.folder)),1)

    def test_stale_session_version_wrong_asset_and_busy_chat_reject_updates(self):
        from ember_harness.recovery import exclusive
        asset_ref,current_ref=self.approved_gate();self.reexport_gate()
        with self.assertRaisesRegex(ValueError,'intended session'):
            self.app.review_asset_update('b'*24,asset_ref,current_ref)
        with self.assertRaisesRegex(ValueError,'latest completed'):self.update(asset_ref,'a'*64)
        other=asset_library.register(self.root,self.chest)
        with self.assertRaisesRegex(ValueError,'asset used'):self.update(other,current_ref)
        with exclusive(self.folder/'chat.lock'),self.assertRaises(ValueError):self.update(asset_ref,current_ref)
        self.assertEqual(len(chat_build.list_requests(self.folder)),1)

    def test_pending_update_keeps_frozen_bytes_and_decline_allows_a_fresh_review(self):
        asset_ref,current_ref=self.approved_gate();self.reexport_gate()
        result=self.update(asset_ref,current_ref)
        (self.gate/'courier-waygate.glb').write_bytes(b'invalid subsequent export')
        self.assertEqual(self.update(asset_ref,current_ref)['request_ref'],result['request_ref'])
        self.app.respond(result['request_ref'],'decline','SYNTHETIC TEST: request another review')
        self.reexport_gate();retry=self.update(asset_ref,current_ref)
        self.assertNotEqual(retry['request_ref'],result['request_ref'])
        self.assertIsNone(chat_build.list_requests(self.folder)[-1]['decision'])

    def test_other_pending_review_and_external_project_edits_block_update(self):
        asset_ref,current_ref=self.approved_gate()
        self.chat('Change color',dict(message='SYNTHETIC review',build=dict(title='Color',summary='Pending scene',
            files=[dict(path=k,content=v+'\n/* pending */' if k=='style.css' else v) for k,v in project_versions.snapshot(self.root,self.folder,current_ref)['files'].items()])),
            'pending-color-0001')
        self.reexport_gate()
        with self.assertRaisesRegex(ValueError,'pending build'):self.update(asset_ref,current_ref)
        self.app.respond(chat_build.list_requests(self.folder)[-1]['ref'],'decline','SYNTHETIC TEST: decline scene edit')
        path=chat_build.project(self.root,self.folder)/'style.css';path.write_bytes(path.read_bytes()+b'/* external */')
        with self.assertRaisesRegex(ValueError,'Project changed'):self.update(asset_ref,current_ref)

    def test_locations_focus_survive_restart_and_prose_truncation(self):
        reply=self.discuss();ref=reply['asset_ref']
        self.assertFalse(chat_build.list_requests(self.folder));self.assertFalse(chat_build.project(self.root,self.folder).exists())
        messages=session_chat.transcript(self.folder)
        for i in range(22):messages.append(dict(id='old-'+str(i),role='assistant',text='Other design discussion',provider='muse',created_at='2026-10-31T00:00:00+00:00'))
        atomic_json(self.folder/'chat.json',messages)
        self.app=App(self.root);self.app.resume(self.folder.name)
        used=self.use_focused()
        self.assertEqual(used['asset_ref'],ref);self.assertEqual(len(self.prompts[-1]['conversation']),20)
        self.assertNotIn('Where is the courier gate',json.dumps(self.prompts[-1]['conversation']))
        packet=chat_build.list_requests(self.folder)[0]['payload']['body']
        self.assertEqual(packet['build']['asset']['report']['sha256'],asset_pipeline.inspect_glb(glb(gate_graph),HINGED_SPEC)['sha256'])
        self.assertEqual(len(packet['asset_actions']),1)
        self.assertEqual(packet['build']['asset_source']['ref'],ref)
        self.assertEqual(packet['build']['asset_source']['sources']['blender']['path'],str(self.gate/'courier-waygate.blend'))
        self.assertFalse(chat_build.project(self.root,self.folder).exists())
        self.assertFalse(any(e['kind']=='approval' for e in chat_build.harness(self.folder)._entries()))
        self.assertEqual(len(gameplay.load(self.folder)['plan']['scenarios']),4)

    def test_native_source_changes_do_not_silently_replace_the_frozen_glb(self):
        ref=self.discuss()['asset_ref']
        (self.gate/'courier-waygate.glb').write_bytes(b'not a valid new export')
        row=asset_library.summary(self.root,ref)
        self.assertEqual(row['sources']['export']['status'],'changed')
        used=self.use_focused();packet=chat_build.list_requests(self.folder)[0]['payload']['body']
        content=next(a['args_constraints']['content']['equals'] for a in packet['contracts'][1]['contract']['allowed_actions'] if a['tool']=='fs.write' and a['args_constraints']['path']['equals'].endswith('/asset.js'))
        self.assertEqual(asset_pipeline.unpack(content)[0],glb(gate_graph))
        self.assertEqual(used['asset_ref'],ref)

    def test_same_asset_request_reuses_matching_pending_review(self):
        self.discuss();first=self.use_focused()
        second=self.use_focused('reuse-pending-0001')
        self.assertEqual(first['proposal_ref'],second['proposal_ref'])
        self.assertEqual(len(chat_build.list_requests(self.folder)),1)
        self.assertFalse(chat_build.project(self.root,self.folder).exists())
        self.assertFalse(any(e['kind']=='approval' for e in chat_build.harness(self.folder)._entries()))

    def test_cli_workshop_and_chat_share_canonical_windows_runtime_bytes(self):
        from ember_harness.asset_workshop import prepare
        engine=self.root/'.harness/asset-tools/engine.js'
        engine.write_bytes(b'/* SYNTHETIC runtime */\r\n/* second line */\r\n')
        with redirect_stdout(io.StringIO()):
            initial=prepare(self.root,self.gate,engine,session_id=self.folder.name)
        self.discuss();used=self.use_focused()
        self.assertEqual(initial['request_ref'],used['proposal_ref'])
        self.assertEqual(len(chat_build.list_requests(self.folder)),1)

    def test_unseen_reference_and_corrupt_record_never_create_proposal(self):
        self.discuss()
        with self.assertRaisesRegex(ValueError,'supplied in this conversation'):
            self.chat('Use a made up asset',dict(message='Invalid fixture',build=None,asset=dict(ref='f'*64,intent='use')),'forged-asset-0001')
        self.assertFalse(chat_build.list_requests(self.folder))
        ref=self.prompts[0]['asset_library']['assets'][0]['ref']
        path=asset_library.home(self.root)/(ref+'.json');record=json.loads(path.read_text());record['display_name']='Tampered'
        path.write_text(json.dumps(record),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'changed'):asset_library.load(self.root,ref)

    def test_scene_edits_receive_compact_asset_context_and_preserve_binary_files(self):
        self.discuss();used=self.use_focused()
        self.app.respond(used['proposal_ref'],'approve','SYNTHETIC TEST: accept known gate fixture')
        current=chat_build.context(self.root,self.folder);files={r['path']:r['content'] for r in current['files']}
        def revise(data):
            protected={r['path']:r for r in data['project']['files'] if r['path'] in ('asset.js','engine.js')}
            self.assertTrue(all('content' not in row and row['retained_by_host'] for row in protected.values()))
            self.assertEqual(protected['asset.js']['asset']['specification']['id'],'courier-waygate')
            source=[dict(path=k,content=v+'\n/* SYNTHETIC scene refinement */' if k=='app.js' else v) for k,v in files.items() if k not in ('engine.js','asset.js')]
            return dict(message='Review the scene refinement.',build=dict(title='Scene refinement',summary='Keep the real GLB',files=source))
        revised=self.chat('Refine the scene lighting.',revise,'scene-revision-0001')
        snapshot=chat_build.proposal_snapshot(self.root,self.folder,revised['proposal_ref'])
        self.assertEqual(snapshot['files']['asset.js'],files['asset.js']);self.assertEqual(snapshot['files']['engine.js'],files['engine.js'])
        self.assertNotIn('asset_actions',chat_build.list_requests(self.folder)[-1]['payload']['body'])
        state=self.app.snapshot()['asset_library']
        self.assertEqual(state['current_ref'],used['asset_ref'])

    def test_newest_export_is_chosen_independently_of_registration_order(self):
        ref1=asset_library.register(self.root,self.gate)
        newer=self.source('newer',HINGED_SPEC,glb(lambda d:(gate_graph(d),d['materials'][0]['pbrMetallicRoughness'].update(baseColorFactor=[.2,.5,.3,1]))))
        new_glb=newer/'courier-waygate.glb';stamp=new_glb.stat()
        os.utime(new_glb,ns=(stamp.st_atime_ns,(self.gate/'courier-waygate.glb').stat().st_mtime_ns+1_000_000_000))
        ref2=asset_library.register(self.root,newer)
        # Simulate startup discovering the older folder last.
        asset_library.register(self.root,self.gate)
        rows=asset_library.context(self.root,self.folder)['assets']
        self.assertEqual(next(r['ref'] for r in rows if r['id']=='courier-waygate'),ref2)
        self.assertNotEqual(ref1,ref2)

    def test_existing_game_requires_scene_code_and_keeps_current_files_until_review(self):
        original='<html><body><h1>Existing game</h1></body></html>'
        first=self.chat('Build a starting game',dict(message='Review this fixture.',build=dict(title='Existing game',summary='Initial fixture',
            files=[dict(path='index.html',content=original)])),'ordinary-game-0001')
        self.app.respond(first['proposal_ref'],'approve','SYNTHETIC TEST: accept existing game')
        self.discuss()
        with self.assertRaisesRegex(ValueError,'Propose scene code'):self.use_focused()
        from ember_harness.asset_workshop import TEMPLATES
        def integrate(data):
            source=[dict(path=n,content=(TEMPLATES/n).read_text(encoding='utf-8')) for n in ('index.html','style.css','app.js')]
            return dict(message='Review this asset integration.',asset=dict(ref=data['asset_library']['focus_ref'],intent='use'),
                build=dict(title='Asset in existing game',summary='Use the recorded GLB',files=source))
        reply=self.chat('Add the gate with a scene implementation.',integrate,'integrate-gate-0001')
        snapshot=chat_build.proposal_snapshot(self.root,self.folder,reply['proposal_ref'])
        self.assertEqual(asset_pipeline.unpack(snapshot['files']['asset.js'])[0],glb(gate_graph))
        self.assertEqual((chat_build.project(self.root,self.folder)/'index.html').read_text(),original)

    def test_workspace_asset_folder_is_discovered_without_unrelated_directories(self):
        for base in ('assets','unrelated'):
            source=self.root/base/'another-gate';source.mkdir(parents=True)
            (source/'asset-spec.json').write_text(json.dumps(HINGED_SPEC),encoding='utf-8')
            (source/'courier-waygate.glb').write_bytes(glb(gate_graph))
        asset_library.discover(self.root)
        paths=[asset_library.load(self.root,p.stem)[0]['sources']['export']['path'] for p in asset_library.home(self.root).glob('*.json')]
        self.assertIn(str(self.root/'assets/another-gate/courier-waygate.glb'),paths)
        self.assertNotIn(str(self.root/'unrelated/another-gate/courier-waygate.glb'),paths)


if __name__=='__main__':unittest.main()
