"""Fixed-runtime observations stay bound across task, proposal and handoff adapters."""
from copy import deepcopy
from hashlib import sha256
import io
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image

import test_gameplay as dom
import test_mechanic_workflow as flows
import test_task_run as tasks
import test_polish as overnight
from quality_fixture import assessments, comparison, review_sheets
from ember_harness import chat_build, gameplay, mechanic_recipes as recipes, mechanic_workflow, polish, polish_runtime, project_plan, task_run
from ember_harness.recovery import atomic_json, read_json

NODE = shutil.which('node')


class Observations:
    """Synthetic browser envelope plus actual fixed-runtime Node observations."""
    def __init__(self, mutate=None):
        self.mutate = mutate
        self.inputs = []
        self.raw_cache = {}

    def raw(self, configuration):
        key = json.dumps(configuration, sort_keys=True)
        if key not in self.raw_cache:
            script = "const api=require(process.argv[1]);const config=JSON.parse(require('node:fs').readFileSync(0,'utf8'));console.log(JSON.stringify(api.verify(config)));"
            result = subprocess.run([NODE, '-e', script, str((recipes.RESOURCE/'mechanic-runtime.js').resolve())],
                input=key, text=True, capture_output=True, timeout=15, check=True)
            self.raw_cache[key] = json.loads(result.stdout)
        return deepcopy(self.raw_cache[key])

    def __call__(self, runtime, source, output, *, check):
        check()
        source, output = Path(source), Path(output)
        data = read_json(source); self.inputs.append((source, deepcopy(data)))
        output.mkdir(parents=True, exist_ok=True)
        views = []
        for view in ('desktop', 'mobile'):
            for suffix in ('', '-before'):
                Image.new('RGB', (40, 30), '#334455').save(output/(view+suffix+'.png'))
            views.append(dict(name=view, loaded=True, observations=[], after=dict(overflow=False),
                screenshot=view+'.png', sha256=polish_runtime.file_digest(output/(view+'.png')),
                before_screenshot=view+'-before.png', before_sha256=polish_runtime.file_digest(output/(view+'-before.png'))))
        if data.get('review_sheets'):
            review_sheets(output, views)
        report = dict(complete=True, input_sha256=polish_runtime.file_digest(source), viewports=views,
                      gameplay=dom.result(data['gameplay_plan']))
        if data.get('mechanic_binding'):
            report['mechanics'] = self.raw(data['mechanic_binding']['configuration'])
        if self.mutate:
            self.mutate(source, data, report)
        atomic_json(output/'report.json', report)
        # Exercise the production artifact validator, not a mocked positive verdict.
        return polish_runtime.verified_report(source, output)


@unittest.skipUnless(NODE, 'Optional Node runtime required for real fixed-step observations')
class CurrentMechanicEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = flows.MechanicWorkflowTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.folder, self.app = self.fixture.root, self.fixture.folder, self.fixture.app
        self.fixture.approve_scope()
        self.ref = self.fixture.apply('sample')
        self.saved = mechanic_workflow.save_checks(self.folder, 0)

    def run_current(self, report_id, observed, revision=None):
        with patch('ember_harness.polish_runtime.discover', return_value={}), patch('ember_harness.polish_runtime.inspect', side_effect=observed):
            return gameplay.run_current(self.root, self.folder, revision or self.saved['revision'], self.ref, report_id)

    def handoff(self):
        raw, _ = self.app.export_handoff(self.fixture.sid, self.ref)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            return json.loads(archive.read('project-report.json'))

    def test_exact_build_manifest_and_plan_binding_then_raw_tamper_blocks_replay_and_export(self):
        observed = Observations()
        event = self.run_current('mechanic-current-binding-0001', observed)
        source, request = observed.inputs[-1]
        bound = request['mechanic_binding']
        self.assertEqual(bound['build_ref'], self.ref)
        self.assertEqual(bound['source_manifest'], chat_build.context(self.root,self.folder)['manifest'])
        self.assertEqual(bound['plan_sha256'], self.saved['sha256'])
        self.assertEqual(bound['plan_revision'], self.saved['revision'])
        self.assertEqual(event['mechanics']['binding'], bound)
        self.assertEqual(event['outcome'], 'passed')
        self.assertTrue(self.handoff()['gameplay']['current_build_checks'][0]['mechanics']['qualified'])
        artifact = source.parent/'output/report.json'
        changed = read_json(artifact); changed['mechanics']['checks'][0]['observed'] = {}
        atomic_json(artifact, changed)
        with self.assertRaisesRegex(ValueError, 'changed|observations|evidence'):
            self.run_current('mechanic-current-binding-0001', observed)
        with self.assertRaises(ValueError):
            self.handoff()

    def test_missing_or_forged_raw_observations_cannot_record_a_passing_dom_result(self):
        for defect in ('missing', 'empty', 'forged'):
            def mutate(source, data, report):
                if defect == 'missing': report.pop('mechanics')
                elif defect == 'empty': report['mechanics']['checks'][0]['observed'] = {}
                else: report['mechanics']['checks'][3]['observed']['positions'] = [0,0,0]
                self.assertEqual(report['gameplay']['outcome'], 'passed')
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                self.run_current('mechanic-invalid-'+defect+'-0001', Observations(mutate))
        self.assertEqual(gameplay.reports(self.folder), [])

    def test_changed_saved_plan_cannot_reuse_or_export_old_passing_mechanic_checks(self):
        observed = Observations(); self.run_current('mechanic-old-plan-report-0001', observed)
        updated = deepcopy(self.saved['plan']); updated['title'] += ' revised'
        revised = gameplay.save(self.folder, updated, self.saved['revision'])
        with self.assertRaisesRegex(ValueError, 'another version or plan'):
            self.run_current('mechanic-old-plan-report-0001', observed, revised['revision'])
        self.assertEqual(self.handoff()['gameplay']['current_build_checks'], [])

    def test_proposal_bindings_name_actual_before_after_builds_and_revalidate_raw_evidence(self):
        pending = self.fixture.prepare('recipe', 'mechanic-evidence-recipe-0001', recipe_id='movement-smoothing', settings={})['request_ref']
        observed = Observations()
        with patch('ember_harness.polish_runtime.discover', return_value={}), patch('ember_harness.polish_runtime.inspect', side_effect=observed):
            event = gameplay.run_proposal(self.root,self.folder,self.saved['revision'],pending,'mechanic-proposal-binding-0001')
        snapshot = chat_build.proposal_snapshot(self.root,self.folder,pending)
        for label, actual_ref, manifest in [('before',self.ref,snapshot['before_manifest']),('proposed',pending,snapshot['manifest'])]:
            binding = event['mechanics'][label]['binding']
            self.assertEqual(binding['build_ref'], actual_ref)
            self.assertEqual(binding['source_manifest'], manifest)
            self.assertEqual(binding['plan_sha256'], self.saved['sha256'])
            self.assertEqual(binding['plan_revision'], self.saved['revision'])
        artifact = self.folder/'proposal-checks/mechanic-proposal-binding-0001/proposed/output/report.json'
        changed = read_json(artifact); changed['mechanics']['outcome'] = 'failed'
        atomic_json(artifact, changed)
        self.assertEqual(gameplay.proposal_status(self.root,self.folder)['state'], 'stale')
        with patch('ember_harness.polish_runtime.discover', return_value={}), patch('ember_harness.polish_runtime.inspect', side_effect=observed):
            with self.assertRaises(ValueError):
                gameplay.run_proposal(self.root,self.folder,self.saved['revision'],pending,'mechanic-proposal-binding-0001')

    def test_changed_canonical_candidate_cannot_downgrade_to_dom_only_recommendation(self):
        files = {row['path']:row['content'] for row in chat_build.context(self.root,self.folder)['files']}
        files['app.js'] += '\n/* incompatible canonical control edit */'
        pending = chat_build.propose_build(self.root,self.folder,'mechanic-incompatible-proposal','Modify reference controls',
            dict(title='SYNTHETIC incompatible candidate',summary='Positive-looking source must not erase mechanic coverage',
                 files=[dict(path=k,content=v) for k,v in files.items()]),
            expected_before=chat_build.context(self.root,self.folder)['sha256'])
        with patch('ember_harness.polish_runtime.discover', return_value={}), patch('ember_harness.polish_runtime.inspect', side_effect=Observations()):
            try:
                event = gameplay.run_proposal(self.root,self.folder,self.saved['revision'],pending,'mechanic-downgrade-check-0001')
            except ValueError:
                return  # Explicit incompatible-reference refusal is also safe.
        self.assertNotEqual(event['outcome'], 'passed', 'A passing DOM echo cannot replace lost fixed-step evidence')


@unittest.skipUnless(NODE, 'Optional Node runtime required for real fixed-step observations')
class TaskMechanicEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = tasks.TaskRunTests(); self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.root, self.folder = self.fixture.root, self.fixture.folder
        files = recipes.reference_files([])
        ref = chat_build.propose_build(self.root,self.folder,'mechanic-task-reference','Original supported platformer',
            dict(title='SYNTHETIC canonical reference',summary='Approved source for task evidence tests',
                 files=[dict(path=k,content=v) for k,v in files.items()]),
            expected_before=chat_build.context(self.root,self.folder)['sha256'])
        self.fixture.app.respond(ref,'approve','SYNTHETIC exact canonical game')
        self.saved = mechanic_workflow.save_checks(self.folder, 1)
        self.phases = []
        self.incompatible = False

    def provider(self, root, folder, prompt, phase, **kwargs):
        self.phases.append(phase); data = json.loads(prompt.split('\n',1)[1])
        if phase.startswith('generate'):
            name = 'app.js' if self.incompatible else 'style.css'
            original = data['files'][name]
            result = dict(title='SYNTHETIC candidate',summary='Untrusted positive generation',
                          edits=[dict(path=name,before=original,after=original+'\n/* revision '+phase+' */')])
        else:
            result = dict(meets_task=True,preserves_scope=True,summary='SYNTHETIC positive independent judgment',issues=[],
                          criteria=assessments(data),comparison=comparison(data))
        return dict(response=json.dumps(result))

    def test_negative_mechanic_result_blocks_positive_ai_and_passing_dom(self):
        run = self.fixture.prepare(); self.fixture.approve(run)
        def negative(source,data,report):
            if source.parent.name != '0':
                report['mechanics']['checks'][0]['status'] = 'failed'
                report['mechanics']['outcome'] = 'failed'
        state = self.fixture.run_worker(run, model=self.provider, browser=Observations(negative))
        self.assertEqual(state['status'], 'awaiting_decision', state.get('error'))
        self.assertEqual(len(state['reports']),3)
        for report in state['reports']:
            self.assertTrue(report['verdict']['meets_task'])
            self.assertEqual(report['observations']['gameplay']['outcome'],'passed')
            self.assertEqual(report['observations']['mechanics']['outcome'],'failed')
            self.assertFalse(report['qualified'])
        with self.assertRaisesRegex(ValueError, 'qualified'):
            task_run.promote(self.root,self.folder,run)


    def test_changed_canonical_source_blocks_task_qualification(self):
        self.incompatible = True
        run = self.fixture.prepare(); self.fixture.approve(run)
        state = self.fixture.run_worker(run, model=self.provider, browser=Observations())
        self.assertNotEqual(state['status'],'ready_review')
        self.assertTrue(all(not report['qualified'] for report in state['reports']))
        if not state['reports']:
            self.assertEqual(state['status'],'interrupted')
        with self.assertRaisesRegex(ValueError, 'qualified'):
            task_run.promote(self.root,self.folder,run)


@unittest.skipUnless(NODE, 'Optional Node runtime required for real fixed-step observations')
class PolishMechanicEvidenceTests(unittest.TestCase):
    def test_runtime_downgrade_cannot_replace_positive_canonical_baseline(self):
        fixture = overnight.PolishTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        root, folder = fixture.root, fixture.folder
        files = recipes.reference_files([])
        ref = chat_build.propose_build(root,folder,'mechanic-polish-reference','Supported polish reference',
            dict(title='SYNTHETIC canonical reference',summary='Exact platformer for polish regression',
                 files=[dict(path=k,content=v) for k,v in files.items()]),
            expected_before=chat_build.context(root,folder)['sha256'])
        fixture.app.respond(ref,'approve','SYNTHETIC exact reference')
        mechanic_workflow.save_checks(folder,0)
        run = fixture.prepare(rounds=2); fixture.approve(run)
        calls = {}
        def positive_model(root, folder, prompt, phase, **kwargs):
            data = json.loads(prompt.split('\n',1)[1]); calls[phase] = data
            if phase.startswith('generate'):
                original = data['files']['mechanic-runtime.js']
                response = dict(title='SYNTHETIC enticing regression',summary='Untrusted source loses canonical support',
                    edits=[dict(path='mechanic-runtime.js',before=original,after=original+'\n/* incompatible runtime */')])
            else:
                response = overnight.critique(5 if phase=='critique-0' else 10,preferred=phase!='critique-0')
            return dict(response=json.dumps(response))
        with patch('ember_harness.polish.run_muse',side_effect=positive_model), patch('ember_harness.polish_runtime.inspect',side_effect=Observations()):
            polish.Worker(root,folder,run).run()
        work,h,packet,plan = polish.load(folder,run)
        self.assertEqual(plan['mechanics'],mechanic_workflow.binding(files))
        candidates = [e for e in h._entries() if e['kind']=='polish_candidate']
        self.assertEqual(len(candidates),3)
        self.assertEqual(candidates[0]['observations']['mechanics']['outcome'],'passed')
        for candidate in candidates[1:]:
            self.assertEqual(candidate['observations']['gameplay']['outcome'],'passed')
            self.assertTrue(candidate['critique']['core_preserved'])
            self.assertTrue(candidate['critique']['prefer_candidate'])
            self.assertNotIn('mechanics',candidate['observations'])
            self.assertTrue(candidate['mechanics']['blockers'])
            self.assertGreater(polish.failures(candidate),0)
            self.assertIn('incompatible runtime',polish.candidate_files(folder,run,candidate['index'])['mechanic-runtime.js'])
            with self.assertRaisesRegex(ValueError,'mechanic reference'):
                polish.promote(root,folder,run,candidate['index'])
        state = polish.history(root,folder)[0]
        self.assertEqual(state['best_index'],0)
        self.assertTrue(state['candidates'][1]['mechanics']['blockers'])
        self.assertEqual(polish.choose_best(candidates)['index'],0)
        self.assertEqual(calls['generate-1']['mechanics'],plan['mechanics'])
        self.assertTrue(calls['critique-1']['mechanic_review']['blockers'])
        feedback = calls['generate-2']['rejected_attempt']
        self.assertTrue(feedback['mechanic_review']['blockers'])
        self.assertIn('canonical runtime',feedback['mechanic_review']['blockers'][0])

