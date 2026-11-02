"""Audio review, retention, preview/export and offline player regression checks."""
from contextlib import redirect_stdout
from io import BytesIO, StringIO
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ember_harness import asset_library, chat_build, game_audio, project_versions, task_run
from ember_harness.local_ui import App

ROOT = Path(__file__).resolve().parents[1]


class GameAudioTests(unittest.TestCase):
    def test_runtime_lifecycle(self):
        node = shutil.which('node')
        if not node: self.skipTest('Optional Node runtime unavailable')
        runtime = Path(game_audio.__file__).with_name('asset_lab') / 'ember-audio.js'
        result = subprocess.run([node, str(ROOT / 'tests/audio_player_test.js'), str(runtime)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_injection_order_comments_duplicates_and_preservation(self):
        plain = {'index.html':'<html><body>Hello</body></html>'}
        self.assertEqual(game_audio.attach(plain, {}), plain)
        html = '<html><body><!-- <script src="ember-audio.js"></script> --><script src="game.js"></script><script defer src="./ember-audio.js"></script></body></html>'
        files = game_audio.attach({'index.html':html, 'game.js':'const audio=EmberAudio.create();'}, {})
        self.assertIn('--><script src="ember-audio.js"></script><script src="game.js">',files['index.html'])
        self.assertNotIn('defer',files['index.html'])
        self.assertEqual(game_audio.attach(files,files),files)
        with self.assertRaises(ValueError):game_audio.attach({**files,game_audio.RUNTIME:'spoofed'},files)
        with self.assertRaises(ValueError):chat_build.materialize_build(dict(title='Tamper',summary='Bad edit',edits=[
            dict(path=game_audio.RUNTIME,before='EmberAudio',after='Spoof')]),files)
        retained=asset_library.preserve_files(dict(title='Retain',summary='Runtime stays',files=[
            dict(path='index.html',content='<html><body><script src="game.js"></script></body></html>'),
            dict(path='game.js',content='const audio=EmberAudio.create();')]),files)
        self.assertEqual(next(row['content'] for row in retained['files'] if row['path']==game_audio.RUNTIME),files[game_audio.RUNTIME])
        model=task_run.model_context(files,files)
        self.assertNotIn(game_audio.RUNTIME,model['files']);self.assertIn(game_audio.RUNTIME,model['immutable_files'])
        self.assertIn('startMusic',model['audio_api'])
        view=asset_library.prompt_project(dict(files=retained['files']))
        self.assertNotIn('content',next(row for row in view['files'] if row['path']==game_audio.RUNTIME))

    def test_chat_proposal_review_revision_restore_and_zip(self):
        scratch=ROOT/'.harness/test-temp';scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            root=Path(temporary);(root/'examples').mkdir();(root/'examples/product_demo.py').touch()
            app=App(root)
            with redirect_stdout(StringIO()):app.start('SYNTHETIC sound demo',chat_only=True)
            folder=app.sessions_dir/app.session['id']
            files=game_audio.demo_files();chat_build.validate_files(files)
            reply=dict(message='Review this original sound demo.',build=dict(title='Sound demo',summary='Original offline audio',files=[
                dict(path=name,content=value) for name,value in files.items() if name!=game_audio.RUNTIME]))
            with patch('ember_harness.session_chat.run_muse',return_value=dict(response=json.dumps(reply))) as model, \
                    patch('ember_harness.proposal_quality.run',return_value=dict(status='unavailable',issues=['SYNTHETIC audio checks run separately'])), redirect_stdout(StringIO()):
                app.chat('Add game effects, music and ambience','audio-game-demo-12345678')
            self.assertIn('startAmbience',model.call_args.args[2])
            request=chat_build.list_requests(folder)[-1]['ref']
            proposed=chat_build.proposal_snapshot(root,folder,request)['files']
            self.assertEqual(proposed,files)
            self.assertEqual(chat_build.context(root,folder)['files'],[],'Proposal must not apply itself')
            preview=chat_build.proposal_preview(root,folder,request)['html']
            self.assertIn('data:text/javascript',preview)
            with redirect_stdout(StringIO()):app.respond(request,'approve','SYNTHETIC TEST: exact audio demo review')
            self.assertTrue(chat_build.verify(root,folder)['passed'])
            archive,_=project_versions.export(root,folder,request)
            with zipfile.ZipFile(BytesIO(archive)) as zipped:
                self.assertEqual(zipped.read(game_audio.RUNTIME).decode(),files[game_audio.RUNTIME])
            current=chat_build.context(root,folder)
            revision=dict(title='Revised label',summary='Keep audio',edits=[dict(path='index.html',before='<h1>Sound garden</h1>',after='<h1>Courier sounds</h1>')])
            build=chat_build.materialize_build(revision,files)
            with redirect_stdout(StringIO()):
                revised=chat_build.propose_build(root,folder,'audio-revision-12345678','Revise label',build,expected_before=current['sha256'])
                app.respond(revised,'approve','SYNTHETIC TEST: label revision')
                restored=project_versions.propose_restore(root,folder,request,revised,'audio-restore-12345678')
                app.respond(restored,'approve','SYNTHETIC TEST: restore audio version')
            self.assertEqual(project_versions.snapshot(root,folder,restored)['files'],files)

    def test_task_worker_adds_audio_with_pinned_inputs_and_separate_build_review(self):
        from test_task_run import TaskRunTests
        fixture=TaskRunTests();fixture.setUp();self.addCleanup(fixture.doCleanups)

        def model(root,folder,prompt,phase,**kwargs):
            result=fixture.model(root,folder,prompt,phase,**kwargs)
            if phase.startswith('generate'):
                reply=json.loads(result['response'])
                for row in reply['files']:
                    if row['path']=='app.js':row['content']+='\nconst audio=EmberAudio.create();'
                result['response']=json.dumps(reply)
            return result

        run=fixture.prepare();fixture.approve(run)
        work,h,packet,plan=task_run.load(fixture.folder,run)
        self.assertTrue(any(row['path'].endswith('asset_lab/ember-audio.js')
                            for row in packet['body']['contracts'][0]['contract']['inputs']))
        state=fixture.run_worker(run,model=model)
        self.assertEqual(state['status'],'ready_review',state.get('error'))
        self.assertEqual((work/'candidates/1'/game_audio.RUNTIME).read_text(encoding='utf-8'),game_audio.source())
        self.assertNotIn(game_audio.RUNTIME,chat_build.context(fixture.root,fixture.folder)['manifest'])
        ref=task_run.promote(fixture.root,fixture.folder,run)['request_ref']
        self.assertIsNone(chat_build.list_requests(fixture.folder)[-1]['decision'])
        fixture.app.respond(ref,'approve','SYNTHETIC TEST: exact audio task candidate')
        self.assertTrue(chat_build.verify(fixture.root,fixture.folder)['passed'])


if __name__ == '__main__':unittest.main()
