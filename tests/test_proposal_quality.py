"""Synthetic providers and captures test automatic verification without live credits."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import unittest
from unittest.mock import patch

from PIL import Image

import test_chat_build as builds
from test_gameplay import PLAN, result as gameplay_result
from quality_fixture import assessments
from ember_harness import chat_build, gameplay, polish_runtime, project_brief, proposal_quality
from ember_harness.recovery import atomic_json, read_json


class ProposalQualityTests(unittest.TestCase):
    def setUp(self):
        quiet=redirect_stdout(io.StringIO());quiet.__enter__();self.addCleanup(quiet.__exit__,None,None,None)
        self.fixture=builds.ChatBuildTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.fixture.quality_patch.stop()
        self.root,self.folder,self.app=self.fixture.root,self.fixture.folder,self.fixture.app
        self.sid=self.app.session['id'];self.failed=False;self.visual=False;self.calls=[]
        self.runtime=patch('ember_harness.polish_runtime.discover',return_value={})
        self.browser=patch('ember_harness.polish_runtime.inspect',side_effect=self.capture)
        self.model=patch('ember_harness.proposal_quality.run_muse',side_effect=self.review)
        for item in (self.runtime,self.browser,self.model):item.start();self.addCleanup(item.stop)

    def propose(self):
        return chat_build.propose_build(self.root,self.folder,'quality-fixture-turn-01','Build a playable counter',
            dict(title='Counter',summary='SYNTHETIC original',files=[dict(path=k,content=v) for k,v in builds.PROJECT.items()]))

    def capture(self,runtime,source,output,**kwargs):
        output.mkdir(parents=True,exist_ok=True);data=read_json(source);rows=[]
        for name in ('desktop','mobile'):
            for suffix in ('','-before','-action'):Image.new('RGB',(32,24),'green').save(output/(name+suffix+'.png'))
            rows.append(dict(name=name,loaded=True,observations=[],before=dict(overflow=False),after=dict(overflow=False),
                screenshot=name+'.png',sha256=polish_runtime.file_digest(output/(name+'.png')),
                before_sha256=polish_runtime.file_digest(output/(name+'-before.png')),
                action_screenshot=name+'-action.png',action_sha256=polish_runtime.file_digest(output/(name+'-action.png'))))
        observed=gameplay_result(data['gameplay_plan'],self.failed) if data['gameplay_plan']['scenarios'] else None
        report=dict(complete=True,input_sha256=polish_runtime.file_digest(source),viewports=rows,
                    **(dict(gameplay=observed) if observed else {}),basis='SYNTHETIC, not real Chromium')
        atomic_json(output/'report.json',report);return report

    def review(self,root,folder,prompt,request_id,**kwargs):
        self.calls.append((prompt,kwargs));data=json.loads(prompt.split('\n',1)[1])
        self.assertIn(chat_build.GAME_UI_REVIEW_INSTRUCTION, prompt)
        self.assertEqual(len(kwargs['images']),4)
        self.assertEqual(data['image_order'],[p.name for p in kwargs['images']])
        for path in kwargs['images']:
            with Image.open(path) as image:self.assertEqual(image.getpixel((0,0)),(0,128,0))
        verdict=dict(meets_task=not self.visual,preserves_scope=True,summary='SYNTHETIC screenshot review',
            issues=['The visible palette does not match the requested warm style'] if self.visual else [],criteria=assessments(data))
        if self.visual:
            row=next(c for c in verdict['criteria'] if c['id']=='presentation')
            row.update(status='not_met',reason='The visible palette does not match the requested warm style')
        return dict(response=json.dumps(verdict))

    def run_quality(self,ref,checks=PLAN,**kwargs):
        return proposal_quality.run(self.root,self.folder,ref,ask='Build a playable counter',brief=project_brief.load(self.folder),design=None,checks=checks,**kwargs)

    def test_activity_follows_real_captures_and_saved_review_without_claiming_a_rerun(self):
        events=[]
        def progress(phase,**metadata):
            if phase=='visual_review':self.assertTrue((proposal_quality.workdir(self.folder,ref)/'candidate/output/desktop.png').is_file())
            if phase=='reviewed':self.assertIsNotNone(proposal_quality.load(self.folder,ref))
            events.append((phase,metadata))
        ref=self.propose()
        self.run_quality(ref,progress=progress)
        self.assertEqual([phase for phase,_ in events],['testing_candidate','visual_review','reviewed'])
        self.assertIn('no blocking issues',events[-1][1]['detail'])
        self.run_quality(ref,progress=progress)
        self.assertEqual(len(events),3,'Reusing saved evidence must not claim new testing occurred')

    def test_activity_reports_an_incomplete_review_without_claiming_visual_inspection(self):
        events=[]
        with patch('ember_harness.polish_runtime.discover',side_effect=ValueError('SYNTHETIC browser unavailable')):
            self.run_quality(self.propose(),progress=lambda phase,**meta:events.append((phase,meta)))
        self.assertEqual([phase for phase,_ in events],['reviewed'])
        self.assertIn('could not finish',events[-1][1]['detail'])

    def test_exact_browser_and_visual_review_never_apply_or_accept_and_replay_is_free(self):
        ref=self.propose();before=chat_build.context(self.root,self.folder)
        report=self.run_quality(ref);again=self.run_quality(ref)
        self.assertEqual(report,again);self.assertEqual(report['status'],'passed',report['issues']);self.assertEqual(len(self.calls),1)
        self.assertEqual(chat_build.context(self.root,self.folder),before)
        self.assertIsNone(chat_build.list_requests(self.folder)[-1]['decision'])
        self.assertEqual(report['assessment']['human_pending'],['human-experience'])
        self.assertEqual(self.app.snapshot()['build']['quality_check'],report)
        self.assertEqual(self.calls[0][1]['budget']['limit_micro_usd'],5_000_000)
        for name in ('desktop.png','mobile-action.png'):
            self.assertTrue(self.app.quality_image_preview(self.sid,ref,name))
        with self.assertRaises(ValueError):self.app.quality_image_preview('0'*24,ref,'desktop.png')
        with self.assertRaises(ValueError):self.app.quality_image_preview(self.sid,ref,'../input.json')

    def test_failed_functionality_cannot_be_overridden_by_positive_ai(self):
        self.failed=True;ref=self.propose();report=self.run_quality(ref)
        self.assertEqual(report['status'],'needs_changes')
        self.assertEqual(report['observations']['candidate']['gameplay']['outcome'],'failed')
        self.assertTrue(report['assessment']['blockers'])

    def test_visual_mismatch_blocks_even_when_gameplay_passes(self):
        events=[]
        self.visual=True;ref=self.propose();report=self.run_quality(ref,progress=lambda phase,**meta:events.append((phase,meta)))
        self.assertEqual(report['status'],'needs_changes')
        self.assertEqual(report['observations']['candidate']['gameplay']['outcome'],'passed')
        self.assertTrue(any('palette' in issue for issue in report['issues']))
        self.assertIn('found issues',events[-1][1]['detail'])

    def test_missing_assertions_or_missing_vision_is_incomplete(self):
        ref=self.propose();report=self.run_quality(ref,checks=None)
        self.assertNotEqual(report['status'],'passed');self.assertTrue(any('unverified' in issue for issue in report['issues']))

    def test_style_mismatch_blocks_even_when_global_verdict_and_gameplay_pass(self):
        def mismatched(*args, **kwargs):
            result = self.review(*args, **kwargs)
            verdict = json.loads(result['response'])
            next(c for c in verdict['criteria'] if c['id'] == 'game-ui-style').update(
                status='not_met', reason='Rounded dashboard cards clash with the pixel-art game.')
            return dict(response=json.dumps(verdict))
        with patch('ember_harness.proposal_quality.run_muse', side_effect=mismatched):
            report = self.run_quality(self.propose())
        self.assertEqual(report['status'], 'needs_changes')
        self.assertTrue(report['verdict']['meets_task'])
        self.assertEqual(report['observations']['candidate']['gameplay']['outcome'], 'passed')
        self.assertTrue(any('game-ui-style: not_met' in issue for issue in report['issues']))

    def test_open_panel_images_replace_movement_attachments_and_are_hash_checked(self):
        def panels(runtime, source, output, **kwargs):
            report = self.capture(runtime, source, output, **kwargs)
            for row in report['viewports']:
                name = row['name'] + '-panel.png'
                Image.new('RGB', (32, 24), 'green').save(output / name)
                row.update(panel_screenshot=name, panel_sha256=polish_runtime.file_digest(output/name))
            atomic_json(output/'report.json', report)
            return report
        with patch('ember_harness.polish_runtime.inspect', side_effect=panels):
            ref = self.propose(); report = self.run_quality(ref)
        self.assertEqual(report['status'], 'passed', report['issues'])
        attached = self.calls[0][1]['images']
        self.assertEqual([p.name for p in attached], ['desktop.png', 'mobile.png', 'desktop-panel.png', 'mobile-panel.png'])
        attached[-1].write_bytes(b'changed panel')
        with self.assertRaisesRegex(ValueError, 'panel capture changed'):
            proposal_quality.load(self.folder, ref)

    def test_browser_unavailable_never_reports_pass_or_dispatches_review(self):
        self.runtime.stop()
        with patch('ember_harness.polish_runtime.discover',side_effect=ValueError('SYNTHETIC browser unavailable')):
            report=self.run_quality(self.propose())
        self.assertEqual(report['status'],'unavailable');self.assertEqual(self.calls,[])

    def test_unrecorded_panel_file_cannot_replace_hash_bound_movement_evidence(self):
        ref = self.propose(); self.run_quality(ref)
        output = proposal_quality.workdir(self.folder, ref)/'candidate/output'
        Image.new('RGB', (32, 24), 'red').save(output/'mobile-panel.png')
        self.assertEqual([p.name for p in proposal_quality.images(self.folder, ref)],
                         ['desktop.png', 'mobile.png', 'desktop-action.png', 'mobile-action.png'])

    def test_saved_checks_are_retained_when_new_checks_are_added(self):
        gameplay.save(self.folder,PLAN,0);extra=deepcopy(PLAN);extra['scenarios'][0]['name']='New interaction'
        report=self.run_quality(self.propose(),extra)
        self.assertEqual(report['checks']['scenarios'][0],PLAN['scenarios'][0])
        self.assertEqual(len(report['checks']['scenarios']),2)
        self.assertEqual(gameplay.load(self.folder)['plan'],PLAN)

    def test_changed_screenshot_during_review_cannot_attach_a_pass(self):
        ref=self.propose();original=self.review
        def changed(*args,**kwargs):
            verdict=original(*args,**kwargs)
            kwargs['images'][0].write_bytes(b'Changed during review')
            return verdict
        with patch('ember_harness.proposal_quality.run_muse',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'screenshot evidence changed'):
                self.run_quality(ref)
        self.assertIsNone(proposal_quality.load(self.folder,ref))

    def test_tampered_action_capture_report_and_changed_checks_cannot_be_reused(self):
        ref=self.propose();self.run_quality(ref)
        work=proposal_quality.workdir(self.folder,ref)
        image=work/'candidate/output/desktop-action.png';original=image.read_bytes();image.write_bytes(b'changed')
        self.assertEqual(proposal_quality.status(self.root,self.folder)['status'],'stale')
        with self.assertRaises(ValueError):proposal_quality.revision_context(self.root,self.folder,ref)
        image.write_bytes(original);gameplay.save(self.folder,PLAN,0)
        self.assertEqual(proposal_quality.status(self.root,self.folder)['status'],'stale')
        with self.assertRaises(ValueError):self.run_quality(ref)

    def test_chat_build_checks_automatically_and_fix_receives_images_and_exact_proposed_files(self):
        gameplay.save(self.folder,PLAN,0);self.visual=True
        ref=self.fixture.propose_project()
        message=read_json(self.folder/'chat.json')[-1]
        self.assertEqual(message['verification']['status'],'needs_changes')
        revised=dict(message='SYNTHETIC requested visual repair',build=dict(title='Warmer counter',summary='Repair the palette',
            edits=[dict(path='style.css',before=builds.PROJECT['style.css'],after='body { background: #ff914d; color: #241b2f; }')]),gameplay_checks=PLAN)
        def repair(*args,**kwargs):
            self.assertEqual(len(kwargs['images']),4)
            data=json.loads(args[2].split('\n',1)[1])
            self.assertEqual(data['proposal_context']['files'],builds.PROJECT)
            self.assertEqual(data['proposal_context']['verification']['original_ask'],'Build or revise a counter')
            return dict(response=json.dumps(revised))
        self.visual=False
        with patch('ember_harness.session_chat.run_muse',side_effect=repair):
            self.app.request_changes(ref,'Fix the palette from the screenshot','quality-repair-turn-01')
        self.assertEqual(read_json(self.folder/'chat.json')[-1]['verification']['status'],'passed')
        self.assertFalse(chat_build.context(self.root,self.folder)['files'])
        self.assertEqual(len(chat_build.status(self.root,self.folder)['completed']),0)
        self.assertEqual(self.app.snapshot()['build']['quality_check']['original_ask'],'Build or revise a counter')


if __name__=='__main__':unittest.main()
