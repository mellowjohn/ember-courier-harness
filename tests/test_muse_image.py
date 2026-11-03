"""Synthetic image responses only; never call a provider or accept user artwork."""
from base64 import b64encode
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
from contextlib import redirect_stdout
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from PIL import Image, ImageDraw

from ember_harness import asset_2d, asset_library, chat_build, muse_image
from ember_harness.core import digest
from ember_harness.local_ui import App
from ember_harness.muse_chat import CreditLedger, IMAGE_MODEL

ROOT = Path(__file__).resolve().parents[1]


class MuseImageTests(unittest.TestCase):
    def setUp(self):
        quality=patch('ember_harness.proposal_quality.run',return_value=dict(status='unavailable',issues=['SYNTHETIC: verification tested separately']))
        quality.start();self.addCleanup(quality.stop)
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'examples').mkdir(); (self.root/'examples/product_demo.py').touch()
        self.folder = self.root/'session'; self.folder.mkdir()
        self.credential = patch('ember_harness.muse_image.credential', return_value='SYNTHETIC-key')
        self.credential.start(); self.addCleanup(self.credential.stop)
        self.spec = asset_2d.effect_spec()
        self.spec.update(frame_size=[64,64], grid=[2,2], frames=4)
        self.spec['production'] = dict(method='generated', tool='muse_image', prompt='Original amber burst', seed=None)
        self.request = asset_2d.generation_request(self.spec)
        image = Image.new('RGB', (256,256), '#FF00FF'); draw = ImageDraw.Draw(image)
        for x,y in [(0,0),(128,0),(0,128),(128,128)]:
            draw.ellipse((x+35,y+35,x+93,y+93), fill='#FFAA22')
        out=BytesIO(); image.save(out,format='PNG'); self.raw=out.getvalue()
        self.response = Mock()
        self.response.__enter__ = Mock(return_value=self.response)
        self.response.__exit__ = Mock(return_value=False)
        self.response.headers = {'x-request-id':'SYNTHETIC-response'}
        self.response.read.return_value = json.dumps(dict(data=[dict(b64_json=b64encode(self.raw).decode())],
            output_format='png',background='opaque')).encode()
        self.opener = Mock(); self.opener.open.return_value = self.response

    def cover(self, balance=150_000_000):
        return muse_image.verify_coverage(self.root, balance, no_paid_fallback=True)

    def generate(self, turn='synthetic-image-12345678', folder=None):
        return muse_image.generate(self.root, folder or self.folder, turn, self.request)

    def batch_specs(self):
        second = deepcopy(self.spec)
        second.update(id='second-burst', display_name='Second original burst')
        return [self.spec, second]

    def test_game_artwork_request_prepares_a_playable_plan_instead_of_detached_images(self):
        from ember_harness import project_plan
        app=App(self.root);app.start('SYNTHETIC snowball game',chat_only=True)
        sid=app.session['id'];folder=app.sessions_dir/sid
        app.save_brief(sid,dict(goal='A turn-based snowball duel',controls='Click to throw',
            visual_direction='Magical winter',constraints='One player versus a snowman'),0)
        document=project_plan.starter(folder)
        document['scope']['features']=['First playable duel with generated artwork, turns, throws, win/lose and restart']
        detached=dict(message='SYNTHETIC detached artwork',build=None,image_requests=self.batch_specs())
        planned=dict(message='SYNTHETIC integrated game plan',build=None,plan=document)
        with patch('ember_harness.session_chat.run_muse',side_effect=[dict(response=json.dumps(detached)),dict(response=json.dumps(planned))]) as spark,patch('ember_harness.muse_image.generate_batch') as images,redirect_stdout(StringIO()):
            app.chat('Love it, will you generate the art assets for this?','game-artwork-route-12345678')
        self.assertEqual(spark.call_count,2);images.assert_not_called()
        self.assertNotEqual(spark.call_args_list[0].args[3],spark.call_args_list[1].args[3])
        state=project_plan.status(self.root,folder)
        self.assertIsNotNone(state['pending']);self.assertFalse(state['active'])
        self.assertEqual(state['pending']['payload']['body']['project_plan']['document'],document)
        self.assertEqual(chat_build.context(self.root,folder)['manifest'],{})
        self.assertEqual(chat_build.list_requests(folder),[])

    def test_game_artwork_route_stops_after_one_failed_correction_without_generating(self):
        app=App(self.root);app.start('SYNTHETIC game design',chat_only=True)
        app.save_brief(app.session['id'],dict(goal='A snowball duel',controls='',visual_direction='',constraints=''),0)
        detached=dict(message='SYNTHETIC still detached',build=None,image_requests=self.batch_specs())
        with patch('ember_harness.session_chat.run_muse',return_value=dict(response=json.dumps(detached))) as spark,patch('ember_harness.muse_image.generate_batch') as images:
            with self.assertRaisesRegex(ValueError,'needs its project plan'):
                app.chat('Generate the game art','game-artwork-stopped-12345678')
        self.assertEqual(spark.call_count,2);images.assert_not_called()

    def test_explicit_standalone_artwork_remains_available_with_a_game_brief(self):
        self.cover();app=App(self.root);app.start('SYNTHETIC standalone art',chat_only=True)
        app.save_brief(app.session['id'],dict(goal='A snowball duel',controls='',visual_direction='',constraints=''),0)
        reply=dict(message='SYNTHETIC standalone effects',build=None,image_requests=self.batch_specs())
        with patch('ember_harness.muse_image.build_opener',return_value=self.opener),patch('ember_harness.session_chat.run_muse',return_value=dict(response=json.dumps(reply))) as spark:
            app.chat('Generate only two artwork assets for my library','game-standalone-art-12345678')
        self.assertEqual(spark.call_count,1)
        self.assertEqual(app.snapshot()['messages'][-1]['image_batch']['completed'],2)

    def test_bulk_artwork_chat_previews_each_result_without_applying_or_accepting(self):
        from ember_harness.muse_chat import structured_schema
        structured_schema(chat_build.CHAT_SCHEMA)
        self.cover(); app=App(self.root); app.start('SYNTHETIC bulk artwork',chat_only=True)
        turn='synthetic-bulk-chat-12345678'
        reply=dict(message='Prepare both original effects.',build=None,image_requests=self.batch_specs())
        names=[]
        def image_call(*args,**kwargs):
            from ember_harness import session_chat
            names.append(session_chat.activity(app.sessions_dir/app.session['id'])['generating_asset'])
            return self.response
        self.opener.open.side_effect=image_call
        with patch('ember_harness.muse_image.build_opener',return_value=self.opener),patch(
                'ember_harness.session_chat.run_muse',return_value=dict(response=json.dumps(reply))) as spark:
            app.chat('Generate two original burst variations',turn)
            app.chat('Generate two original burst variations',turn)
            app.generate_saved_image(app.session['id'],turn)
        self.assertEqual(spark.call_count,1)
        self.assertEqual(self.opener.open.call_count,2)
        self.assertEqual(names,[spec['display_name'] for spec in self.batch_specs()])
        message=app.snapshot()['messages'][-1]; batch=message['image_batch']
        self.assertEqual((batch['status'],batch['completed'],batch['total']),('generated',2,2))
        self.assertEqual(CreditLedger(self.root).summary()['estimated_spent_usd'],.02)
        folder=app.sessions_dir/app.session['id']
        self.assertEqual(chat_build.list_requests(folder),[])
        self.assertEqual(chat_build.context(self.root,folder)['manifest'],{})
        refs=[item['generation']['asset_ref'] for item in batch['items']]
        self.assertEqual(len(set(refs)),2)
        for ref in refs:
            self.assertTrue(app.generated_image_preview(app.session['id'],turn,ref))
            self.assertTrue(app.asset_image_preview(app.session['id'],ref))
        with self.assertRaises(ValueError):app.generated_image_preview(app.session['id'],'other-turn',refs[0])

    def test_bulk_artwork_waits_for_credits_and_resumes_without_spark_or_duplicate_images(self):
        app=App(self.root); app.start('SYNTHETIC deferred bulk',chat_only=True)
        turn='synthetic-bulk-deferred-12345678'
        reply=dict(message='Prepare both effects.',build=None,image_requests=self.batch_specs())
        with patch('ember_harness.session_chat.run_muse',return_value=dict(response=json.dumps(reply))) as spark:
            app.chat('Generate two effects',turn)
            self.assertEqual(app.snapshot()['messages'][-1]['image_batch']['status'],'blocked')
            self.cover(10_000)
            with patch('ember_harness.muse_image.build_opener',return_value=self.opener):
                app.generate_saved_image(app.session['id'],turn)
                batch=app.snapshot()['messages'][-1]['image_batch']
                self.assertEqual((batch['status'],batch['completed']),('partial',1))
                first=batch['items'][0]['generation']['asset_ref']
                # Resume the saved session with additional verified credit coverage.
                self.cover(); fresh=App(self.root); fresh.resume(app.session['id'])
                fresh.generate_saved_image(app.session['id'],turn)
                done=fresh.snapshot()['messages'][-1]['image_batch']
                self.assertEqual(done['completed'],2)
                self.assertEqual(done['items'][0]['generation']['asset_ref'],first)
        self.assertEqual(spark.call_count,1)
        self.assertEqual(self.opener.open.call_count,2)
        self.assertEqual(CreditLedger(self.root).summary()['estimated_spent_usd'],.02)

    def test_bulk_failure_retains_successful_siblings_and_never_resends_uncertain_call(self):
        self.cover()
        requests=[asset_2d.generation_request(s) for s in self.batch_specs()]
        self.opener.open.side_effect=[HTTPError(muse_image.ENDPOINT,503,'private',{},None),self.response]
        with patch('ember_harness.muse_image.build_opener',return_value=self.opener):
            first=muse_image.generate_batch(self.root,self.folder,'synthetic-bulk-failure-12345678',requests)
            again=muse_image.generate_batch(self.root,self.folder,'synthetic-bulk-failure-12345678',requests)
        self.assertEqual((first['status'],first['completed']),('partial',1))
        self.assertEqual(first['items'][1],again['items'][1])
        self.assertEqual(again['completed'],1)
        self.assertEqual(self.opener.open.call_count,2)
        self.assertEqual(CreditLedger(self.root).summary()['reserved_usd'],.01)
        self.assertEqual(CreditLedger(self.root).summary()['estimated_spent_usd'],.01)

    def test_bulk_interrupt_checkpoints_completed_images_and_locks_the_request(self):
        self.cover(); turn='synthetic-bulk-interrupt-12345678'
        requests=[asset_2d.generation_request(s) for s in self.batch_specs()]
        generate=muse_image.generate; calls=0
        def interrupt(*args,**kwargs):
            nonlocal calls
            calls+=1
            if calls==2:raise KeyboardInterrupt()
            return generate(*args,**kwargs)
        with patch('ember_harness.muse_image.build_opener',return_value=self.opener):
            with patch('ember_harness.muse_image.generate',side_effect=interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    muse_image.generate_batch(self.root,self.folder,turn,requests)
            saved=json.loads((self.folder/'image-batches'/(turn+'-results.json')).read_bytes())
            self.assertEqual(saved['completed'],1)
            with self.assertRaisesRegex(ValueError,'batch changed'):
                muse_image.generate_batch(self.root,self.folder,turn,list(reversed(requests)))
            done=muse_image.generate_batch(self.root,self.folder,turn,requests)
        self.assertEqual(done['completed'],2)
        self.assertEqual(self.opener.open.call_count,2)

    def test_invalid_bulk_items_or_mixed_operations_stop_before_any_dispatch(self):
        self.cover(); requests=[asset_2d.generation_request(s) for s in self.batch_specs()]
        invalid=deepcopy(requests);invalid[1]['parameters']['prompt']='tampered'
        with patch('ember_harness.muse_image.build_opener') as network:
            for rows in ([],requests*5,[requests[0],requests[0]],invalid):
                with self.assertRaises(ValueError):
                    muse_image.generate_batch(self.root,self.folder,'synthetic-bulk-invalid-12345678',rows)
            app=App(self.root);app.start('SYNTHETIC mixed bulk',chat_only=True)
            for index,extra in enumerate((dict(image_request=self.spec),dict(build=dict(title='Mixed',summary='No',
                    files=[dict(path='index.html',content='<html><body>Mixed</body></html>')])))):
                reply=dict(message='Invalid mixed operations',build=None,image_requests=self.batch_specs())
                reply.update(extra)
                with patch('ember_harness.session_chat.run_muse',return_value=dict(response=json.dumps(reply))):
                    with self.assertRaisesRegex(ValueError,'bulk artwork separately'):
                        app.chat('Generate artwork','synthetic-bulk-mixed-12345678-'+str(index))
            network.assert_not_called()
        self.assertEqual(CreditLedger(self.root).read()['requests'],{})

    def test_unverified_or_paid_billing_never_reserves_or_sends(self):
        with patch('ember_harness.muse_image.build_opener') as network:
            with self.assertRaises(muse_image.ImageUnavailable): self.generate()
            for value in [False,None,'true']:
                with self.assertRaises(ValueError):
                    muse_image.verify_coverage(self.root,150_000_000,no_paid_fallback=value)
            network.assert_not_called()
        self.assertEqual(CreditLedger(self.root).summary()['reserved_usd'],0)
        self.assertFalse(muse_image.status(self.root)['ready'])

    def test_expired_changed_credentials_and_changed_coverage_stop_before_dispatch(self):
        self.cover()
        path=muse_image.coverage_path(self.root)
        original=json.loads(path.read_bytes())
        for change in [dict(valid_until=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()),
                       dict(credential_sha256='a'*64),dict(no_paid_fallback=False),dict(price_micro_usd=1)]:
            data={**original,**change};data.pop('sha256');data['sha256']=digest(data)
            path.write_text(json.dumps(data))
            with patch('ember_harness.muse_image.build_opener') as network:
                with self.assertRaises(muse_image.ImageUnavailable):self.generate()
                network.assert_not_called()
        self.assertEqual(CreditLedger(self.root).read()['requests'],{})

    def test_shared_grant_authorization_survives_restart_without_repeated_billing_gates(self):
        ledger=CreditLedger(self.root);ledger.reserve('previous-spark-call')
        first=muse_image.use_shared_credit_budget(self.root,'SYNTHETIC owner: use the same active Model API grant as Spark for images')
        self.assertTrue(first['ready']);self.assertEqual(first['policy'],'shared-model-api-budget')
        self.assertFalse(first['billing_balance_verified'])
        # This policy records the shared grant authorization, not a fabricated
        # billing balance, a nonexistent card change, or a recurring 24h gate.
        record=json.loads(muse_image.coverage_path(self.root).read_bytes())
        self.assertNotIn('no_paid_fallback',record);self.assertNotIn('balance_micro_usd',record)
        self.assertNotIn('valid_until',record)
        self.assertTrue(muse_image.status(self.root)['ready'])
        self.assertEqual(ledger.summary()['reserved_usd'],5)
        self.assertEqual(ledger.summary()['limit_usd'],150)
        with patch('ember_harness.muse_image.build_opener',return_value=self.opener):self.generate()
        self.assertEqual(ledger.summary()['estimated_spent_usd'],.01)
        # Account changes and the original global ceiling remain real stops.
        with patch('ember_harness.muse_image.credential',return_value='different-key'):
            self.assertFalse(muse_image.status(self.root)['ready'])
        data=ledger.read();data['limit_micro_usd']=5_010_000;ledger.path.write_text(json.dumps(data))
        self.assertFalse(muse_image.status(self.root)['ready'])

    def test_direct_generation_preparation_capture_and_restart_do_not_repeat_call(self):
        self.cover(); phases=[]
        with patch('ember_harness.muse_image.build_opener',return_value=self.opener):
            first=muse_image.generate(self.root,self.folder,'synthetic-image-12345678',self.request,
                                      progress=phases.append)
            again=self.generate()
        self.assertEqual(first,again); self.assertEqual(self.opener.open.call_count,1)
        req=self.opener.open.call_args.args[0]; params=json.loads(req.data)
        self.assertEqual(params['model'],IMAGE_MODEL);self.assertEqual(params['n'],1)
        self.assertEqual(params['output_format'],'png');self.assertNotIn('background',params)
        self.assertEqual(set(params['tool_enablement'].values()),{False})
        self.assertIn('#FF00FF',params['prompt'])
        record,spec,report=asset_library.load(self.root,first['asset_ref'])
        prepared,_,_=asset_2d.unpack(record['package'])
        self.assertNotEqual(prepared,self.raw)
        self.assertEqual(report['dimensions_px'],[128,128]);self.assertTrue(report['transparency'])
        self.assertEqual(first['preparation']['source_dimensions'],[256,256])
        self.assertEqual(phases,['image_generating','image_preparing'])
        self.assertEqual(CreditLedger(self.root).summary()['estimated_spent_usd'],.01)
        self.assertEqual(CreditLedger(self.root).summary()['reserved_usd'],0)
        evidence=(self.folder/'image-captures/synthetic-image-12345678.json').read_text()
        self.assertNotIn('SYNTHETIC-key',evidence)

    def test_failure_retains_cent_and_replay_does_not_retry_or_expose_error_body(self):
        self.cover();self.opener.open.side_effect=HTTPError(muse_image.ENDPOINT,503,'SYNTHETIC-key',{},None)
        with patch('ember_harness.muse_image.build_opener',return_value=self.opener):
            for _ in range(2):
                with self.assertRaises(muse_image.ImageUnavailable) as failure:self.generate()
                self.assertNotIn('SYNTHETIC-key',str(failure.exception))
        self.assertEqual(self.opener.open.call_count,1)
        self.assertEqual(CreditLedger(self.root).summary()['reserved_usd'],.01)
        self.assertEqual(CreditLedger(self.root).summary()['estimated_spent_usd'],0)

    def test_changed_request_or_saved_pixels_never_send_again(self):
        self.cover()
        with patch('ember_harness.muse_image.build_opener',return_value=self.opener):self.generate()
        changed=deepcopy(self.request);changed['parameters']['prompt']+='different'
        with patch('ember_harness.muse_image.build_opener') as network:
            with self.assertRaisesRegex(ValueError,'changed'):
                muse_image.generate(self.root,self.folder,'synthetic-image-12345678',changed)
            (self.folder/'image-captures/synthetic-image-12345678.png').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'pixels changed'):self.generate()
            network.assert_not_called()

    def test_image_reservations_share_ceiling_with_spark_and_verified_balance(self):
        ledger=CreditLedger(self.root);ledger.reserve('spark')
        self.cover(10_000)
        with patch('ember_harness.muse_image.build_opener',return_value=self.opener):self.generate()
        self.assertEqual(ledger.summary()['reserved_usd'],5)
        self.assertEqual(ledger.summary()['estimated_spent_usd'],.01)
        self.assertFalse(muse_image.status(self.root)['ready'])
        with self.assertRaises(ValueError):
            ledger.reserve('image-too-many',model=IMAGE_MODEL,verified_ceiling_micro_usd=5_010_000)
        # A lower persisted global ceiling still wins over fresh credit confirmation.
        data=ledger.read();data['limit_micro_usd']=5_010_000;ledger.path.write_text(json.dumps(data))
        self.cover()
        with patch('ember_harness.muse_image.build_opener') as network:
            with self.assertRaises(muse_image.ImageUnavailable):self.generate('synthetic-second-12345678')
            network.assert_not_called()

    def test_chat_generates_real_asset_and_unapplied_review_without_owner_acceptance(self):
        self.cover();app=App(self.root);app.start('SYNTHETIC generated art',chat_only=True)
        folder=app.sessions_dir/app.session['id']
        reply=dict(message='Muse Image will generate this artwork for review.',build=None,image_request=self.spec)
        with patch('ember_harness.muse_image.build_opener',return_value=self.opener),patch(
                'ember_harness.session_chat.run_muse',return_value=dict(response=json.dumps(reply))):
            with redirect_stdout(StringIO()):app.chat('Generate an impact atlas','synthetic-chat-image-12345678')
        message=app.snapshot()['messages'][-1]
        self.assertEqual(message['image_generation']['status'],'generated')
        requests=chat_build.list_requests(folder)
        self.assertEqual(len(requests),1);self.assertFalse(requests[0]['decision'])
        self.assertEqual(len(requests[0]['payload']['body']['asset_actions']),1)
        self.assertEqual(chat_build.context(self.root,folder)['manifest'],{})
        self.assertTrue(app.generated_image_preview(app.session['id'],message['reply_to'],message['asset_ref']))
        self.assertEqual(app.asset_image_preview(app.session['id'],message['asset_ref']),
                         app.generated_image_preview(app.session['id'],message['reply_to'],message['asset_ref']))
        with self.assertRaises(ValueError):app.generated_image_preview('0'*24,message['reply_to'],message['asset_ref'])
        with self.assertRaises(ValueError):app.generated_image_preview(app.session['id'],'different-message',message['asset_ref'])

    def test_saved_request_can_generate_after_verification_without_another_spark_call(self):
        app=App(self.root);app.start('SYNTHETIC deferred image',chat_only=True)
        reply=dict(message='Artwork for review.',build=None,image_request=self.spec)
        turn='synthetic-deferred-12345678'
        with patch('ember_harness.session_chat.run_muse',return_value=dict(response=json.dumps(reply))) as spark:
            app.chat('Generate an impact atlas',turn)
            self.assertEqual(app.snapshot()['messages'][-1]['image_generation']['status'],'blocked')
            app.verify_image_credits(app.session['id'],'150',True)
            with patch('ember_harness.muse_image.build_opener',return_value=self.opener),redirect_stdout(StringIO()):
                app.generate_saved_image(app.session['id'],turn)
                app.generate_saved_image(app.session['id'],turn)
            self.assertEqual(spark.call_count,1)
        self.assertEqual(self.opener.open.call_count,1)
        self.assertEqual(app.snapshot()['messages'][-1]['image_generation']['status'],'generated')

    def test_chat_scene_implementation_receives_the_actual_generated_package(self):
        self.cover();app=App(self.root);app.start('SYNTHETIC sprite scene',chat_only=True)
        folder=app.sessions_dir/app.session['id']
        png,_=asset_2d.prepare_generated_png(self.raw,self.spec)
        scene=asset_2d.assemble(asset_2d.package(png,self.spec))
        build=dict(title='Original effect',summary='Render the real image',files=[
            dict(path=k,content=v) for k,v in scene.items() if k!='asset.js'])
        reply=dict(message='Generate and add this effect.',build=build,image_request=self.spec)
        with patch('ember_harness.muse_image.build_opener',return_value=self.opener),patch(
                'ember_harness.session_chat.run_muse',return_value=dict(response=json.dumps(reply))),redirect_stdout(StringIO()):
            app.chat('Generate and add the effect','synthetic-scene-image-12345678')
        request=chat_build.list_requests(folder)[-1]
        body=request['payload']['body']
        self.assertEqual(len(body['asset_actions']),1)
        self.assertEqual(body['build']['manifest']['asset.js'],
                         asset_library.summary(self.root,body['build']['asset_source']['ref'])['package_sha256'])
        self.assertFalse(chat_build.context(self.root,folder)['manifest'])

    def test_artwork_only_request_keeps_existing_ordinary_game_unchanged(self):
        self.cover();app=App(self.root);app.start('SYNTHETIC existing game',chat_only=True)
        folder=app.sessions_dir/app.session['id']
        build=dict(title='Existing game',summary='Synthetic fixture',files=[dict(
            path='index.html',content='<html><body><h1>Keep this game</h1></body></html>')])
        with redirect_stdout(StringIO()):
            ref=chat_build.propose_build(self.root,folder,'fixture-game','Synthetic game',build)
            app.respond(ref,'approve','SYNTHETIC TEST: approve isolated game fixture')
        before=chat_build.context(self.root,folder)['manifest']
        reply=dict(message='Generate artwork only.',build=None,image_request=self.spec)
        with patch('ember_harness.muse_image.build_opener',return_value=self.opener),patch(
                'ember_harness.session_chat.run_muse',return_value=dict(response=json.dumps(reply))):
            app.chat('Generate an atlas without changing my game','synthetic-art-only-12345678')
        self.assertEqual(chat_build.context(self.root,folder)['manifest'],before)
        self.assertEqual(len(chat_build.list_requests(folder)),1)
        self.assertEqual(app.snapshot()['messages'][-1]['asset_intent'],'discuss')

    def test_billing_verification_is_bound_to_selected_session_and_exact_amount(self):
        app=App(self.root);app.start('SYNTHETIC image credits',chat_only=True)
        for session,amount,paid in [('0'*24,'150',True),(app.session['id'],'150',False),
                                   (app.session['id'],'150.01',True),(app.session['id'],'1e3',True),
                                   (app.session['id'],True,True)]:
            with self.assertRaises(ValueError):app.verify_image_credits(session,amount,paid)
        self.assertFalse(muse_image.coverage_path(self.root).exists())

    def test_preparation_rejects_wrong_ratio_and_empty_or_opaque_atlas(self):
        for size,color in [((400,100),'#FF00FF'),((256,256),'#FF00FF'),((256,256),'#FFAA22')]:
            image=Image.new('RGB',size,color);out=BytesIO();image.save(out,format='PNG')
            with self.assertRaises(ValueError):asset_2d.prepare_generated_png(out.getvalue(),self.spec)


if __name__=='__main__':unittest.main()
