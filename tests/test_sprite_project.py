"""Entity plans, source replacements, per-atlas acceptance and recovery with synthetic providers."""
from contextlib import redirect_stdout
from copy import deepcopy
from io import BytesIO,StringIO
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile

from jsonschema import Draft202012Validator,ValidationError
from ember_harness import asset_2d,asset_library,asset_workshop,chat_build,muse_image,project_plan,project_versions,sprite_project,task_run
from ember_harness.local_ui import App, server
from ember_harness.muse_chat import decode_structured,structured_schema
from tools.sprite_scene_check import character,machine,plan,game_files,integration_edits
from test_muse_chat import wire_reply

ROOT=Path(__file__).resolve().parents[1]


class SpriteProjectTests(unittest.TestCase):
    def setUp(self):
        quality=patch('ember_harness.proposal_quality.run',return_value=dict(status='unavailable',issues=['SYNTHETIC: verification tested separately']))
        quality.start();self.addCleanup(quality.stop)
        scratch=ROOT/'.harness/test-temp';scratch.mkdir(parents=True,exist_ok=True)
        temp=tempfile.TemporaryDirectory(dir=scratch);self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        (self.root/'examples').mkdir();(self.root/'examples/product_demo.py').touch()
        self.spec,self.raw=character();self.effect=asset_2d.effect_spec();self.effect_raw=asset_2d.render_effect(self.effect)
        self.hero=self.source('hero',self.spec,self.raw);self.impact=self.source('impact',self.effect,self.effect_raw)
        self.app=App(self.root);self.app.start('SYNTHETIC entity sprite game',chat_only=True);self.folder=self.app.sessions_dir/self.app.session['id']

    def source(self,name,spec,raw):
        source=self.root/'.harness/asset-source'/name
        asset_2d.write_source(source,raw,spec,asset_2d.generation_request(spec) if spec['production']['method']=='generated' else None)
        return asset_library.register(self.root,source)

    def baseline(self):
        files=game_files()
        with redirect_stdout(StringIO()):
            ref=chat_build.propose_build(self.root,self.folder,'baseline','Synthetic existing game',dict(title='Original game',summary='Fixture',files=[dict(path=k,content=v) for k,v in files.items()]))
            self.app.respond(ref,'approve','SYNTHETIC TEST: isolated original game')
        return files

    def send(self,document=None,build=None,revision=0,turn='sprite-entities-chat-12345678',intent='implement'):
        response=dict(message='Synthetic entity artwork proposal.',build=build if build is not None else integration_edits(),
            sprite_project=dict(intent=intent,expected_revision=revision,plan=document or plan(self.hero,self.impact)))
        with patch('ember_harness.session_chat.run_muse',return_value=dict(response=json.dumps(response))) as provider,redirect_stdout(StringIO()):
            self.app.chat('Integrate the character and impact; retain gameplay',turn)
        return provider

    def approve(self,ref):
        with redirect_stdout(StringIO()):self.app.respond(ref,'approve','SYNTHETIC TEST: individually accept the listed exact fixture atlases')

    def test_graph_validation_catches_missing_clips_bad_signals_and_terminal_errors(self):
        sprite_project.validate_machine(machine(),self.spec)
        mutations=[]
        for target,value in [('initial','missing')]:
            changed=machine();changed[target]=value;mutations.append(changed)
        changed=machine();changed['states']['attack']['clip']='missing';mutations.append(changed)
        changed=machine();changed['states']['death']['on_complete']='idle';mutations.append(changed)
        changed=machine();changed['states']['idle']['on_complete']='walk';mutations.append(changed)
        changed=machine();changed['states']['attack']['markers']=[dict(event='hit',frame=63)];mutations.append(changed)
        changed=machine();changed['states']['attack']['markers']=[dict(event='hit',frame=1),dict(event='hit',frame=2)];mutations.append(changed)
        changed=machine();changed['transitions'][0]['when'][0]['signal']='unknown';mutations.append(changed)
        changed=machine();changed['transitions'][0]['when'][0]['value']=1;mutations.append(changed)
        changed=machine();changed['transitions'][0]['when'][0]['op']='gt';mutations.append(changed)
        changed=machine();changed['transitions'][0]['from']=['death'];changed['transitions'][0]['to']='idle';mutations.append(changed)
        changed=machine();changed['signals']['vy']['default']=float('nan');mutations.append(changed)
        for changed in mutations:
            with self.subTest(machine=changed),self.assertRaises((ValueError,ValidationError)):
                sprite_project.validate_machine(changed,self.spec)
        entity=plan(self.hero,self.impact)['entities'][0]
        with self.assertRaisesRegex(ValueError,'kind'):
            sprite_project.validate_entity_asset(entity,self.effect)

    def test_native_schema_keeps_entity_bindings_guards_markers_and_maps(self):
        response=dict(message='Plan entity art',build=None,sprite_project=dict(intent='plan',expected_revision=0,plan=plan(self.hero,self.impact)))
        wire=wire_reply(response,chat_build.CHAT_SCHEMA)
        Draft202012Validator(structured_schema(chat_build.CHAT_SCHEMA)).validate(wire)
        decoded=decode_structured(wire,chat_build.CHAT_SCHEMA)
        self.assertEqual(decoded['sprite_project'],response['sprite_project'])
        sprite_project.validate_plan(decoded['sprite_project']['plan'])

    def test_exact_existing_game_replacement_two_acceptances_and_exports(self):
        original=self.baseline();provider=self.send()
        self.assertIn('sprite_project',provider.call_args.args[2]);self.assertIn('createScene',provider.call_args.args[2])
        request=chat_build.list_requests(self.folder)[-1];body=request['payload']['body']
        self.assertEqual(len(body['asset_actions']),2);self.assertNotIn('asset',body['build'])
        self.assertEqual(len(body['build']['sprite_assets']),2)
        self.assertEqual(body['contracts'][0]['contract']['extensions']['scope']['asset_budget'],{'sprite_atlases':2})
        files=chat_build.proposal_snapshot(self.root,self.folder,request['ref'])['files']
        self.assertNotIn('ctx.fillRect(x-12,y-40,24,40);',files['game.js'])
        self.assertIn('score=7,health=3',files['game.js']);self.assertIn('vy+=600*dt',files['game.js'])
        self.assertEqual({r['path']:r['content'] for r in chat_build.context(self.root,self.folder)['files']},original)
        self.assertLess(files['index.html'].index('sprite-assets.js'),files['index.html'].index('sprite-player.js'))
        self.assertLess(files['index.html'].index('sprite-player.js'),files['index.html'].index('game.js'))
        with self.assertRaises(ValueError):chat_build.resume(self.root,self.folder,request['ref'])
        self.approve(request['ref']);self.assertTrue(chat_build.verify(self.root,self.folder)['passed'])
        entries=chat_build.harness(self.folder)._entries()
        accepted=[e for e in entries if e['kind']=='decision' and e.get('action',{}).get('tool')=='asset.accept' and e.get('decision')=='allow']
        self.assertEqual(len(accepted),2);self.assertTrue(all(e['reason']=='one_time_approval_consumed' for e in accepted))
        archive,_=project_versions.export(self.root,self.folder,request['ref'])
        with zipfile.ZipFile(BytesIO(archive)) as zipped:
            self.assertEqual(json.loads(zipped.read('sprite-plan.json'))['entities'][0]['asset_ref'],self.hero)
            self.assertEqual(zipped.read('sprites/'+self.hero+'/'+self.spec['id']+'.png'),self.raw)
            self.assertEqual(zipped.read('sprites/'+self.impact+'/'+self.effect['id']+'.png'),self.effect_raw)
        metadata=task_run.model_context(files,files)
        self.assertNotIn('sprite-assets.js',metadata['files']);self.assertIn('sprite_plan',metadata)
        self.assertNotIn('png_base64',json.dumps(metadata))
        fresh=App(self.root);fresh.resume(self.app.session['id'])
        self.assertEqual(fresh.snapshot()['sprite_project']['applied_plan']['entities'][0]['asset_ref'],self.hero)

    def test_replace_one_atlas_preserves_other_entities_and_restore(self):
        self.baseline();self.send();first=chat_build.list_requests(self.folder)[-1]['ref'];self.approve(first)
        old=project_versions.snapshot(self.root,self.folder,first)['files']
        spec=asset_2d.effect_spec(seed=99);new_ref=self.source('impact-v2',spec,asset_2d.render_effect(spec))
        updated=sprite_project.unpack_plan(old['sprite-plan.js']);updated['entities'][1]['asset_ref']=new_ref
        build=dict(title='Replace impact only',summary='Keep character and gameplay',files=[dict(path=k,content=v) for k,v in old.items() if k not in chat_build.PROTECTED_FILES])
        self.send(updated,build,revision=1,turn='sprite-replace-impact-12345678')
        request=chat_build.list_requests(self.folder)[-1]
        self.assertEqual(len(request['payload']['body']['asset_actions']),1)
        self.assertEqual(request['payload']['body']['build']['sprite_changes'],['impact'])
        files=chat_build.proposal_snapshot(self.root,self.folder,request['ref'])['files']
        self.assertEqual(files['game.js'],old['game.js'])
        self.assertEqual(sprite_project.unpack_assets(files['sprite-assets.js'])[self.hero],sprite_project.unpack_assets(old['sprite-assets.js'])[self.hero])
        self.approve(request['ref'])
        with redirect_stdout(StringIO()):restored=project_versions.propose_restore(self.root,self.folder,first,request['ref'],'sprite-restore-entities-12345678')
        self.approve(restored);self.assertEqual(project_versions.snapshot(self.root,self.folder,restored)['files'],old)

    def test_invalid_bindings_fail_before_generation_or_project_changes(self):
        original=self.baseline();document=plan(self.hero,self.impact)
        spec=deepcopy(self.spec);spec['production']=dict(method='generated',tool='muse_image',prompt='Original courier animation',seed=None)
        document['entities'][0].update(asset_ref=None,generation=spec)
        document['entities'][0]['binding']['replace']='a draw snippet that does not exist'
        with patch('ember_harness.muse_image.generate') as generate:
            with self.assertRaisesRegex(ValueError,'Replacement'):
                self.send(document,turn='sprite-invalid-binding-12345678')
            generate.assert_not_called()
        self.assertEqual({r['path']:r['content'] for r in chat_build.context(self.root,self.folder)['files']},original)
        self.assertEqual(len(chat_build.list_requests(self.folder)),1)

    def test_full_file_artwork_reply_retains_an_omitted_previous_entry_script(self):
        before=self.baseline()
        expanded=chat_build.materialize_build(integration_edits(),before)
        files={row['path']:row['content'] for row in expanded['files']}
        supplied={'index.html':files['index.html'].replace('game.js','app.js'), 'app.js':files['game.js']}
        document=plan(self.hero,self.impact)
        for entity in document['entities']:
            entity['binding']=dict(file='app.js',replace='')
        build=dict(title='New artwork entry script',summary='Keep the prior source while integrating artwork',
            files=[dict(path=k,content=v) for k,v in supplied.items()])
        self.send(document,build,turn='sprite-new-entry-script-12345678')
        request=chat_build.list_requests(self.folder)[-1]
        candidate=chat_build.proposal_snapshot(self.root,self.folder,request['ref'])['files']
        self.assertEqual(candidate['game.js'],before['game.js'])
        self.assertEqual(candidate['app.js'],supplied['app.js'])
        sprite_project.validate_files(candidate,before)
        self.assertIsNone(request['decision'])

    def test_missing_bindings_get_one_correction_before_generation_and_exact_review(self):
        before=self.baseline();good=plan(self.hero,self.impact);bad=deepcopy(good)
        for entity in bad['entities']: entity['binding']=None
        original=dict(message='SYNTHETIC initial code',build=integration_edits(),
            sprite_project=dict(intent='implement',expected_revision=0,plan=bad))
        fixed=dict(message='SYNTHETIC corrected code bindings',build=integration_edits(),
            sprite_project=dict(intent='implement',expected_revision=0,plan=good))
        def provider(root,folder,prompt,turn,**kwargs):
            if 'Correct this unapproved artwork implementation.' in prompt:
                self.assertIn('has no draw binding',prompt)
                self.assertEqual(len(chat_build.list_requests(folder)),1)
                return dict(response=json.dumps(fixed))
            return dict(response=json.dumps(original))
        with patch('ember_harness.session_chat.run_muse',side_effect=provider) as muse,patch('ember_harness.muse_image.generate') as images,redirect_stdout(StringIO()):
            self.app.chat('Use the planned character and effect artwork','sprite-binding-repair-12345678')
        self.assertEqual(muse.call_count,2);images.assert_not_called()
        self.assertNotEqual(muse.call_args_list[0].args[3],muse.call_args_list[1].args[3])
        request=chat_build.list_requests(self.folder)[-1]
        self.assertIsNone(request['decision'])
        candidate=chat_build.proposal_snapshot(self.root,self.folder,request['ref'])['files']
        sprite_project.validate_files(candidate,before)
        self.assertEqual({r['path']:r['content'] for r in chat_build.context(self.root,self.folder)['files']},before)

    def test_correction_cannot_drop_unbound_entities_or_switch_artwork(self):
        self.baseline();document=plan(self.hero,self.impact)
        document['entities'][1]['binding']=None
        original=dict(message='SYNTHETIC missing effect binding',build=integration_edits(),
            sprite_project=dict(intent='implement',expected_revision=0,plan=document))
        for change in ('drop','switch'):
            corrected=deepcopy(original)
            if change=='drop':corrected['sprite_project']['plan']['entities'].pop()
            else:corrected['sprite_project']['plan']['entities'][0]['asset_ref']=self.impact
            with patch('ember_harness.session_chat.run_muse',side_effect=[dict(response=json.dumps(original)),dict(response=json.dumps(corrected))]) as muse,patch('ember_harness.muse_image.generate') as images:
                with self.assertRaisesRegex(sprite_project.BindingError,'preserve every entity'):
                    self.app.chat('Fix the missing entity binding','sprite-binding-'+change+'-12345678')
                self.assertEqual(muse.call_count,2);images.assert_not_called()
        self.assertEqual(len(chat_build.list_requests(self.folder)),1)

    def test_repeated_invalid_binding_stops_after_one_correction_without_images(self):
        self.baseline();document=plan(self.hero,self.impact)
        document['entities'][0]['binding']=None
        with patch('ember_harness.muse_image.generate') as images:
            response=dict(message='SYNTHETIC still invalid',build=integration_edits(),
                sprite_project=dict(intent='implement',expected_revision=0,plan=document))
            with patch('ember_harness.session_chat.run_muse',return_value=dict(response=json.dumps(response))) as muse:
                with self.assertRaisesRegex(sprite_project.BindingError,'has no draw binding'):
                    self.app.chat('Connect the artwork','sprite-binding-repeated-12345678')
                self.assertEqual(muse.call_count,2)
            images.assert_not_called()
        self.assertEqual(len(chat_build.list_requests(self.folder)),1)

    def test_reexport_of_a_bound_sheet_keeps_other_art_and_syncs_the_applied_inventory(self):
        self.baseline();self.send();first=chat_build.list_requests(self.folder)[-1]['ref'];self.approve(first)
        before=project_versions.snapshot(self.root,self.folder,first)['files']
        source=self.root/'.harness/asset-source/impact';changed=asset_2d.effect_spec(seed=41)
        raw=asset_2d.render_effect(changed);(source/(changed['id']+'.png')).write_bytes(raw)
        (source/'asset-spec.json').write_text(json.dumps(changed))
        with redirect_stdout(StringIO()):updated=asset_workshop.review_updated_export(self.root,self.folder,self.impact,first)
        request=chat_build.list_requests(self.folder)[-1]
        self.assertEqual(len(request['payload']['body']['asset_actions']),1)
        after=chat_build.proposal_snapshot(self.root,self.folder,request['ref'])['files']
        self.assertEqual(after['game.js'],before['game.js']);self.assertEqual(after['sprite-player.js'],before['sprite-player.js'])
        self.assertEqual(sprite_project.unpack_assets(after['sprite-assets.js'])[self.hero],sprite_project.unpack_assets(before['sprite-assets.js'])[self.hero])
        self.approve(updated['request_ref'])
        self.assertEqual(sprite_project.load_draft(self.folder)['plan'],sprite_project.unpack_plan(after['sprite-plan.js']))

    def test_missing_state_machine_stops_before_provider_calls(self):
        self.baseline();document=plan(self.hero,self.impact)
        document['entities'][0]['machine']=None
        with patch('ember_harness.muse_image.generate') as generate:
            with self.assertRaisesRegex(ValueError,'state machine'):self.send(document,turn='sprite-no-machine-12345678')
            generate.assert_not_called()

    def test_plan_asset_estimates_do_not_block_generation_or_skip_review(self):
        self.baseline();document=plan(self.hero,self.impact)
        spec=deepcopy(self.spec);spec['production']=dict(method='generated',tool='muse_image',prompt='Original courier',seed=None)
        document['entities'][0].update(asset_ref=None,generation=spec)
        generated=self.source('generated-courier',spec,self.raw)
        scope=project_plan.starter(self.folder);scope['scope']['asset_budget']={'artwork':0}
        with redirect_stdout(StringIO()):
            ref=project_plan.prepare(self.root,self.folder,scope,None)['request_ref']
            self.app.respond(ref,'approve','SYNTHETIC TEST: plan counts are estimates')
        before=chat_build.context(self.root,self.folder)['manifest']
        with patch('ember_harness.muse_image.generate',return_value=dict(status='generated',asset_ref=generated)) as generate:
            self.send(document,turn='sprite-over-estimate-12345678')
            generate.assert_called_once()
        request=chat_build.list_requests(self.folder)[-1]
        self.assertIsNone(request['decision'])
        self.assertEqual(len(request['payload']['body']['asset_actions']),2)
        self.assertEqual(request['payload']['body']['build']['project_scope']['ref'],ref)
        self.assertEqual(chat_build.context(self.root,self.folder)['manifest'],before)

    def test_inactive_scope_still_stops_before_generation(self):
        self.baseline();document=plan(self.hero,self.impact)
        spec=deepcopy(self.spec);spec['production']=dict(method='generated',tool='muse_image',prompt='Original courier',seed=None)
        document['entities'][0].update(asset_ref=None,generation=spec)
        with patch('ember_harness.project_plan.check_binding',side_effect=ValueError('Inactive project scope')),patch('ember_harness.muse_image.generate') as generate:
            with self.assertRaisesRegex(ValueError,'Inactive project scope'):self.send(document,turn='sprite-inactive-scope-12345678')
            generate.assert_not_called()

    def test_ordinary_chat_cannot_invent_registry_data_or_bypass_entity_bindings(self):
        self.baseline()
        build=dict(title='Invalid route',summary='Do not accept invented registry data',files=[
            *[dict(path=k,content=v) for k,v in game_files().items()],dict(path='sprite-assets.js',content='invented')])
        response=dict(message='Synthetic invalid registry',build=build)
        with patch('ember_harness.session_chat.run_muse',return_value=dict(response=json.dumps(response))):
            with self.assertRaisesRegex(ValueError,'entity plan'):self.app.chat('Invalid fixture route','sprite-invalid-route-12345678')
        self.send();request=chat_build.list_requests(self.folder)[-1]['ref'];self.approve(request)
        response=dict(message='Synthetic ambiguous replacement',build=None,asset=dict(ref=self.hero,intent='use'))
        with patch('ember_harness.session_chat.run_muse',return_value=dict(response=json.dumps(response))):
            with self.assertRaisesRegex(ValueError,'which entity'):self.app.chat('Invalid fixture shortcut','sprite-invalid-shortcut-12345678')

    def test_atlas_cap_is_checked_before_generation(self):
        self.baseline()
        original=plan(self.hero,self.impact)['entities'][0];document=dict(version=1,entities=[])
        for index in range(9):
            entity=deepcopy(original);entity['id']='actor'+str(index)
            spec=deepcopy(self.spec);spec['id']='actor-'+str(index);spec['production']=dict(method='generated',tool='muse_image',prompt='Original actor',seed=None)
            entity.update(asset_ref=None,generation=spec);document['entities'].append(entity)
        with patch('ember_harness.muse_image.generate') as generate:
            with self.assertRaisesRegex(ValueError,'eight'):self.send(document,turn='sprite-atlas-cap-12345678')
            generate.assert_not_called()

    def test_plan_only_is_durable_and_does_not_generate_or_change_game(self):
        document=plan(self.hero,self.impact);document['entities'][0].update(asset_ref=None,binding=None)
        response=dict(message='Inventory saved',build=None,sprite_project=dict(intent='plan',expected_revision=0,plan=document))
        with patch('ember_harness.session_chat.run_muse',return_value=dict(response=json.dumps(response))),patch('ember_harness.muse_image.generate') as generate:
            self.app.chat('Plan the artwork first','sprite-inventory-plan-12345678');generate.assert_not_called()
        self.assertFalse(chat_build.context(self.root,self.folder)['manifest'])
        fresh=App(self.root);fresh.resume(self.app.session['id'])
        inventory=fresh.snapshot()['sprite_project'];self.assertEqual(inventory['revision'],1)
        self.assertEqual(inventory['inventory'][0]['status'],'needs_artwork')
        self.assertEqual(sprite_project.requirements('Movement and jumping combat')[0]['clips'],['idle','walk'])

    def test_known_artwork_preview_serves_exact_reused_png_without_changing_game(self):
        self.baseline(); self.send()
        before=chat_build.context(self.root,self.folder)['manifest']
        http=server(self.app);worker=threading.Thread(target=http.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{http.server_port}/api/asset-image?'
        query=dict(session_id=self.app.session['id'],ref=self.hero)
        try:
            with self.assertRaises(HTTPError) as denied:urlopen(base+urlencode(query))
            self.assertEqual(denied.exception.code,403)
            with patch('ember_harness.muse_image.generate') as generate:
                with urlopen(Request(base+urlencode(query),headers={'X-Ember-Token':self.app.token})) as response:
                    self.assertEqual(response.headers.get_content_type(),'image/png')
                    self.assertEqual(response.read(),self.raw)
                generate.assert_not_called()
            for invalid in (dict(query,session_id='0'*24),dict(query,ref='0'*64),dict(query,ref='../asset-spec.json')):
                with self.assertRaises(HTTPError) as denied:
                    urlopen(Request(base+urlencode(invalid),headers={'X-Ember-Token':self.app.token}))
                self.assertEqual(denied.exception.code,400)
        finally:http.shutdown();http.server_close();worker.join(timeout=5)
        self.assertEqual(chat_build.context(self.root,self.folder)['manifest'],before)
        self.assertFalse(chat_build.list_requests(self.folder)[-1]['decision'])

    def test_historical_plan_preview_retains_exact_snapshot_after_library_deduplication(self):
        self.baseline();self.send()
        newer=deepcopy(self.spec);newer['display_name']='Revised courier artwork'
        self.source('revised-hero',newer,self.raw)
        self.assertNotIn(self.hero,{a['ref'] for a in self.app.snapshot()['asset_library']['assets']})
        self.assertEqual(self.app.asset_image_preview(self.app.session['id'],self.hero),self.raw)
        record=asset_library.home(self.root)/(self.hero+'.json')
        data=json.loads(record.read_text());data['display_name']='Tampered artwork';record.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'changed'):
            self.app.asset_image_preview(self.app.session['id'],self.hero)

    def test_partial_generation_saves_resolved_refs_and_resumes_without_recreating_them(self):
        self.baseline();document=plan(self.hero,self.impact)
        specs=[];refs=[]
        for index,(original,raw) in enumerate([(self.spec,self.raw),(self.effect,self.effect_raw)]):
            spec=deepcopy(original);spec['production']=dict(method='generated',tool='muse_image',prompt='Original fixture '+str(index),seed=None)
            specs.append(spec);refs.append(self.source('generated-'+str(index),spec,raw))
            document['entities'][index].update(asset_ref=None,generation=spec)
        with patch('ember_harness.muse_image.generate',side_effect=[dict(status='generated',asset_ref=refs[0]),muse_image.ImageUnavailable('Synthetic unavailable')]) as generate:
            self.send(document,turn='sprite-partial-generation-12345678')
            self.assertEqual(generate.call_count,2)
        saved=sprite_project.load_draft(self.folder)
        self.assertEqual(saved['plan']['entities'][0]['asset_ref'],refs[0]);self.assertIsNone(saved['plan']['entities'][0]['generation'])
        self.assertIsNotNone(saved['plan']['entities'][1]['generation']);self.assertEqual(len(chat_build.list_requests(self.folder)),1)
        self.assertEqual(self.app.generated_image_preview(self.app.session['id'],'sprite-partial-generation-12345678',refs[0]),self.raw)
        with self.assertRaises(ValueError):self.app.generated_image_preview(self.app.session['id'],'sprite-partial-generation-12345678',self.impact)
        with patch('ember_harness.muse_image.generate',return_value=dict(status='generated',asset_ref=refs[1])) as generate:
            self.send(saved['plan'],revision=1,turn='sprite-resume-generation-12345678');self.assertEqual(generate.call_count,1)
        self.assertEqual(len(chat_build.list_requests(self.folder)),2)
        self.assertEqual(len(chat_build.list_requests(self.folder)[-1]['payload']['body']['asset_actions']),2)

    def test_state_machine_runtime(self):
        node=shutil.which('node')
        if not node:self.skipTest('Optional Node runtime is unavailable')
        runtime=Path(asset_2d.__file__).with_name('asset_lab')/'sprite-player.js'
        result=subprocess.run([node,str(ROOT/'tests/sprite_machine_test.js'),str(runtime)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
