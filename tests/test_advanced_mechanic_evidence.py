"""Advanced reference observations retain the normal source and approval bindings."""
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import zipfile

import test_mechanic_evidence as evidence
import test_mechanic_workflow as flows
from quality_fixture import assessments, comparison
from ember_harness import chat_build, gameplay, mechanic_recipes, mechanic_workflow, polish_runtime, project_plan, project_versions, task_run
from ember_harness.recovery import atomic_json, read_json


class AdvancedObservations(evidence.Observations):
    """A synthetic capture envelope with actual canonical advanced-runtime results."""
    def raw(self, configuration):
        if configuration['profile'] != 'ember-platformer-v2':
            return super().raw(configuration)
        from ember_harness import mechanic_expansions
        key = json.dumps(configuration, sort_keys=True)
        if key not in self.raw_cache:
            script = "const api=require(process.argv[1]);const config=JSON.parse(require('node:fs').readFileSync(0,'utf8'));console.log(JSON.stringify(api.verify(config)));"
            result = subprocess.run([evidence.NODE, '-e', script,
                str((mechanic_expansions.RESOURCE / 'advanced-runtime.js').resolve())],
                input=key, text=True, capture_output=True, timeout=15, check=True)
            self.raw_cache[key] = json.loads(result.stdout)
        return deepcopy(self.raw_cache[key])


@unittest.skipUnless(evidence.NODE, 'Optional Node runtime required for real fixed-step observations')
class AdvancedMechanicEvidenceTests(unittest.TestCase):
    def setUp(self):
        from ember_harness import mechanic_expansions
        self.expansions = mechanic_expansions
        self.fixture = flows.MechanicWorkflowTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.folder, self.app = self.fixture.root, self.fixture.folder, self.fixture.app
        self.app.respond(self.fixture.plan_ref, 'decline', 'SYNTHETIC replace movement-only draft with complete reference scope')
        document = project_plan.starter(self.folder)
        document['scope'].update(game_concept='Original Lantern Trail advanced reference',
            core_loop='Move, jump, avoid a sentry and hazard, reach the light and restart.',
            features=['Tune camera deadzone and easing', 'Tune hit stop and invincibility',
                      'Tune enemy patrol, chase and attack', 'Reproduce a seeded reachable level'],
            out_of_scope=['Network', 'Generated artwork', 'Native engine changes', 'Publishing'],
            done_criteria=['Review resolved recipe settings and exact source',
                           'Fixed-step observations and keyboard/touch checks pass',
                           'Johnathan separately plays and accepts the result'])
        self.fixture.plan_ref = project_plan.prepare(self.root, self.folder, document, self.fixture.plan_ref)['request_ref']
        self.fixture.approve_scope()
        self.files = mechanic_expansions.reference_files()
        self.ref = chat_build.propose_build(self.root, self.folder, 'advanced-evidence-initial',
            'Original advanced reference', dict(title='SYNTHETIC advanced reference',
                summary='Exact canonical source for evidence integration',
                files=[dict(path=name, content=content) for name, content in self.files.items()]),
            project_scope=project_plan.context(self.root, self.folder)['binding'])
        self.app.respond(self.ref, 'approve', 'SYNTHETIC exact advanced reference source')
        self.saved = self.app.mechanic_control(self.fixture.sid, 'checks', revision=0)

    def run_current(self, report_id, observed):
        with patch('ember_harness.polish_runtime.discover', return_value={}), \
                patch('ember_harness.polish_runtime.inspect', side_effect=observed):
            return gameplay.run_current(self.root, self.folder, self.saved['revision'], self.ref, report_id)

    def handoff(self):
        raw, _ = self.app.export_handoff(self.fixture.sid, self.ref)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            return json.loads(archive.read('project-report.json'))

    def test_advanced_observations_bind_exact_settings_seed_build_and_saved_plan(self):
        observed = AdvancedObservations()
        event = self.run_current('advanced-current-evidence-0001', observed)
        bound = observed.inputs[-1][1]['mechanic_binding']
        self.assertEqual(bound['profile'], 'ember-platformer-v2')
        self.assertEqual(bound['configuration'], mechanic_recipes.inspect(self.files))
        self.assertEqual(bound['build_ref'], self.ref)
        self.assertEqual(bound['source_manifest'], chat_build.context(self.root, self.folder)['manifest'])
        self.assertEqual(bound['plan_sha256'], self.saved['sha256'])
        self.assertEqual(bound['plan_revision'], self.saved['revision'])
        self.assertEqual(event['mechanics']['binding'], bound)
        self.assertEqual(event['outcome'], 'passed')
        report = self.handoff()
        self.assertEqual(report['mechanics'], bound['configuration'])
        self.assertTrue(report['gameplay']['current_build_checks'][0]['mechanics']['qualified'])
        self.assertFalse(report['project_plan']['tasks'][0]['accepted'])

    def test_missing_legacy_or_forged_advanced_witnesses_cannot_pass_positive_dom(self):
        for defect in ('missing', 'legacy', 'camera', 'seed', 'layout'):
            def mutate(source, data, report):
                self.assertEqual(report['gameplay']['outcome'], 'passed')
                if defect == 'missing':
                    report.pop('mechanics')
                elif defect == 'legacy':
                    report['mechanics']['profile'] = 'ember-platformer-v1'
                elif defect == 'seed':
                    report['mechanics']['settings']['level_seed'] += 1
                elif defect == 'layout':
                    report['mechanics']['checks'][-1]['observed']['hash'] = '00000000'
                else:
                    check = report['mechanics']['checks'][8]
                    check['observed']['first'] += 1000000
                    check['status'] = 'passed'
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                self.run_current('advanced-invalid-' + defect + '-0001', AdvancedObservations(mutate))
        self.assertEqual(gameplay.reports(self.folder), [])

    def test_retained_advanced_raw_tamper_blocks_replay_and_handoff(self):
        observed = AdvancedObservations()
        self.run_current('advanced-retained-tamper-0001', observed)
        source = observed.inputs[-1][0]
        artifact = source.parent / 'output/report.json'
        changed = read_json(artifact)
        changed['mechanics']['checks'][-1]['observed'] = {}
        atomic_json(artifact, changed)
        with self.assertRaises(ValueError):
            self.run_current('advanced-retained-tamper-0001', observed)
        with self.assertRaises(ValueError):
            self.handoff()

    def test_camera_comparison_preserves_the_identical_seeded_level_and_starting_route(self):
        pending = self.fixture.prepare('recipe', 'advanced-camera-comparison-0001', recipe_id='camera-follow',
            settings=dict(camera_deadzone_px=120, camera_easing_ms=300, reduced_motion=0))['request_ref']
        observed = AdvancedObservations()
        with patch('ember_harness.polish_runtime.discover', return_value={}), \
                patch('ember_harness.polish_runtime.inspect', side_effect=observed):
            event = gameplay.run_proposal(self.root, self.folder, self.saved['revision'], pending,
                'advanced-same-seed-camera-0001')
        self.assertEqual(event['outcome'], 'passed')
        before = event['mechanics']['before']; after = event['mechanics']['proposed']
        self.assertEqual(before['observations']['checks'][-1]['observed'], after['observations']['checks'][-1]['observed'])
        self.assertNotEqual(before['observations']['checks'][8]['observed']['first'],
                            after['observations']['checks'][8]['observed']['first'])
        self.assertEqual(before['binding']['configuration']['settings']['level_seed'],
                         after['binding']['configuration']['settings']['level_seed'])
        self.assertEqual(before['binding']['build_ref'], self.ref)
        self.assertEqual(after['binding']['build_ref'], pending)

    def test_downgrading_advanced_source_cannot_erase_required_evidence(self):
        legacy = {**self.files, **mechanic_recipes.reference_files()}
        pending = chat_build.propose_build(self.root, self.folder, 'advanced-downgrade-source-0001',
            'SYNTHETIC unsupported downgrade', dict(title='SYNTHETIC reference downgrade',
                summary='A smaller reference cannot silently erase camera, damage, enemy and level checks',
                files=[dict(path=name, content=text) for name, text in legacy.items()]),
            expected_before=chat_build.context(self.root, self.folder)['sha256'])
        with patch('ember_harness.polish_runtime.discover', return_value={}), \
                patch('ember_harness.polish_runtime.inspect', side_effect=AdvancedObservations()):
            try:
                event = gameplay.run_proposal(self.root, self.folder, self.saved['revision'], pending,
                    'advanced-source-downgrade-check-0001')
            except ValueError:
                return
        self.assertNotEqual(event['outcome'], 'passed')
        self.assertTrue(event['mechanic_review']['blockers'])

    def test_seed_settings_survive_exact_application_zip_forward_restore_and_handoff(self):
        settings = dict(level_seed=404, level_sections=12)
        prepared = self.fixture.prepare('recipe', 'advanced-seed-settings-0001',
            recipe_id='seeded-levels', settings=settings)
        self.assertEqual(chat_build.context(self.root, self.folder)['mechanics'], mechanic_recipes.inspect(self.files))
        self.app.respond(prepared['request_ref'], 'approve', 'SYNTHETIC exact seed and generator settings')
        final = prepared['request_ref']; snapshot = project_versions.snapshot(self.root, self.folder, final)
        self.assertEqual(snapshot['mechanics']['settings']['level_seed'], 404)
        self.assertEqual(snapshot['mechanics']['settings']['level_sections'], 12)
        raw, _ = self.app.export_version(final)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertEqual(json.loads(archive.read('ember-build.json'))['mechanics'], snapshot['mechanics'])
        restore = project_versions.propose_restore(self.root, self.folder, self.ref, final, 'advanced-seed-restore-0001')
        self.app.respond(restore, 'approve', 'SYNTHETIC checked forward restore of advanced source')
        restored = chat_build.context(self.root, self.folder)
        self.assertEqual(restored['mechanics'], mechanic_recipes.inspect(self.files))
        self.assertEqual({row['path']:row['content'] for row in restored['files']}, self.files)
        self.assertEqual(len(project_versions.history(self.folder)), 3)

    def test_negative_advanced_observations_block_all_positive_ai_task_attempts(self):
        binary = self.root / 'synthetic-advanced-muse.exe'
        binary.write_bytes(b'SYNTHETIC provider identity; never executed')
        runtime = dict(node=str(binary), browser=str(binary), module=str(self.root),
            driver=str(polish_runtime.DRIVER), module_hash='unused synthetic module',
            hashes=dict(node=polish_runtime.file_digest(binary), browser=polish_runtime.file_digest(binary),
                        driver=polish_runtime.file_digest(polish_runtime.DRIVER)))
        def positive(root, folder, prompt, phase, **kwargs):
            data = json.loads(prompt.split('\n', 1)[1])
            if phase.startswith('generate'):
                original = data['files']['style.css']
                value = dict(title='SYNTHETIC attractive candidate', summary='Positive opinion cannot replace mechanic evidence',
                    edits=[dict(path='style.css', before=original, after=original+'\n/* '+phase+' */')])
            else:
                value = dict(meets_task=True, preserves_scope=True, summary='SYNTHETIC positive independent opinion',
                    issues=[], criteria=assessments(data), comparison=comparison(data))
            return dict(response=json.dumps(value))
        def negative(source, data, report):
            if source.parent.name != '0':
                report['mechanics']['checks'][-1]['status'] = 'failed'
                report['mechanics']['outcome'] = 'failed'
        with patch('ember_harness.task_run.installed_binary', return_value=binary), \
                patch('ember_harness.polish_runtime.discover', return_value=runtime):
            run = task_run.prepare(self.root, self.folder)['id']
            with patch('ember_harness.task_run.launch', return_value=dict(status='ready')):
                task_run.respond(self.root, self.folder, run, 'approve', 'SYNTHETIC reviewed advanced coder/verifier scope')
            with patch('ember_harness.task_run.run_muse', side_effect=positive), \
                    patch('ember_harness.polish_runtime.inspect', side_effect=AdvancedObservations(negative)):
                task_run.Worker(self.root, self.folder, run).run()
        state = task_run.history(self.root, self.folder)[-1]
        self.assertEqual(state['status'], 'awaiting_decision', state.get('error'))
        self.assertEqual(len(state['reports']), 3)
        for report in state['reports']:
            self.assertTrue(report['verdict']['meets_task'])
            self.assertEqual(report['observations']['gameplay']['outcome'], 'passed')
            self.assertEqual(report['observations']['mechanics']['outcome'], 'failed')
            self.assertFalse(report['qualified'])
        with self.assertRaisesRegex(ValueError, 'qualified'):
            task_run.promote(self.root, self.folder, run)
