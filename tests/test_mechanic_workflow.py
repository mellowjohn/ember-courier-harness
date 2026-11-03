"""Recipes follow the existing scoped exact-build, version and acceptance paths."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ember_harness import chat_build, gameplay, mechanic_recipes, mechanic_workflow, project_plan, project_versions
from ember_harness.local_ui import App
from tools.browser_check import synthetic_provider_guard

ROOT = Path(__file__).resolve().parents[1]


class MechanicWorkflowTests(unittest.TestCase):
    def setUp(self):
        quiet = redirect_stdout(io.StringIO()); quiet.__enter__(); self.addCleanup(quiet.__exit__, None, None, None)
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=scratch); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); (self.root / 'examples').mkdir(); (self.root / 'examples/product_demo.py').touch()
        guard = synthetic_provider_guard(); guard.__enter__(); self.addCleanup(guard.__exit__, None, None, None)
        discovery = patch('ember_harness.muse_chat.installed_binary', return_value=None)
        discovery.start(); self.addCleanup(discovery.stop)
        task_discovery = patch('ember_harness.task_run.installed_binary', return_value=None)
        task_discovery.start(); self.addCleanup(task_discovery.stop)
        self.app = App(self.root); self.app.start('SYNTHETIC mechanic product workflow', chat_only=True)
        self.sid = self.app.session['id']; self.folder = self.app.sessions_dir / self.sid
        document = project_plan.starter(self.folder)
        document['scope'].update(game_concept='Original Lantern Trail reference platformer',
            core_loop='Move, jump across a gap, reach the light and restart.',
            features=['Tune movement and jumping'], out_of_scope=['Network', 'Generated artwork', 'Engine changes'],
            done_criteria=['Review recipe values and exact changes', 'Keyboard/touch and simulation checks pass', 'Owner plays and separately accepts'])
        self.plan_ref = project_plan.prepare(self.root, self.folder, document, None)['request_ref']

    def approve_scope(self):
        self.app.respond(self.plan_ref, 'approve', 'SYNTHETIC TEST: original reference movement/jumping scope')

    def prepare(self, action, operation='mechanic-operation-0001', **values):
        return self.app.mechanic_control(self.sid, action, operation_id=operation,
            expected_manifest=chat_build.context(self.root, self.folder)['manifest'], **values)

    def apply(self, action, operation='mechanic-operation-0001', **values):
        proposed = self.prepare(action, operation, **values)
        self.app.respond(proposed['request_ref'], 'approve', 'SYNTHETIC TEST: exact mechanic source only')
        return proposed['request_ref']

    def test_scope_sample_frozen_recipe_reload_exact_settings_and_separate_acceptance(self):
        with self.assertRaises(ValueError): self.prepare('sample')
        self.assertFalse(chat_build.list_requests(self.folder))
        self.approve_scope()
        sample = self.prepare('sample')
        self.assertEqual(sample['mechanics']['recipes'], [])
        self.assertFalse(chat_build.context(self.root, self.folder)['files'])
        self.app.respond(sample['request_ref'], 'approve', 'SYNTHETIC TEST: exact baseline platformer')
        baseline = {row['path']:row['content'] for row in chat_build.context(self.root, self.folder)['files']}
        saved_checks = self.app.mechanic_control(self.sid, 'checks', revision=0)
        self.assertEqual(saved_checks['plan'], mechanic_workflow.checks())
        proposed = self.prepare('recipe', 'movement-operation-0001', recipe_id='movement-smoothing',
            settings=dict(max_speed=300, acceleration_ms=250, stopping_ms=150, reversal_multiplier=2))
        self.assertEqual(chat_build.context(self.root, self.folder)['mechanics']['recipes'], [])
        payload = next(row for row in chat_build.list_requests(self.folder) if row['ref']==proposed['request_ref'])['payload']['body']['build']
        frozen = deepcopy(payload['mechanics'])
        fresh = App(self.root); restored = fresh.resume(self.sid)
        retained = next(row for row in restored['build']['requests'] if row['ref']==proposed['request_ref'])
        self.assertEqual(retained['payload']['body']['build']['mechanics'], frozen)
        fresh.respond(proposed['request_ref'], 'approve', 'SYNTHETIC TEST: reviewed resolved settings after reload')
        applied = {row['path']:row['content'] for row in chat_build.context(self.root, self.folder)['files']}
        self.assertEqual([name for name in baseline if baseline[name]!=applied[name]], ['mechanic-config.js'])
        self.assertEqual(mechanic_recipes.inspect(applied)['settings']['max_speed'], 300)
        self.assertEqual(frozen, project_versions.snapshot(self.root, self.folder, proposed['request_ref'])['mechanics'])
        self.assertIsNone(project_plan.status(self.root, self.folder)['tasks'][0]['acceptance'])
        self.assertEqual(payload['project_scope']['task_id'], 'task-1')

    def test_invalid_settings_manifest_and_retired_scope_cannot_prepare_or_change_files(self):
        self.approve_scope(); self.apply('sample')
        before = chat_build.context(self.root, self.folder)
        count = len(chat_build.list_requests(self.folder))
        for values in (dict(recipe_id='unknown', settings={}),
                       dict(recipe_id='movement-smoothing', settings={'max_speed': float('nan')}),
                       dict(recipe_id='forgiving-jumps', settings={'coyote_ms': 201}),
                       dict(recipe_id='forgiving-jumps', settings={'surprise': 1})):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.prepare('recipe', **values)
        with self.assertRaisesRegex(ValueError, 'game changed'):
            self.app.mechanic_control(self.sid, 'recipe', operation_id='stale-operation-00001',
                expected_manifest={}, recipe_id='movement-smoothing', settings={})
        with self.assertRaisesRegex(ValueError, 'intended session'):
            self.app.mechanic_control('f'*24, 'recipe', operation_id='other-session-000001',
                expected_manifest=before['manifest'], recipe_id='movement-smoothing', settings={})
        self.assertEqual(len(chat_build.list_requests(self.folder)), count)
        self.assertEqual(chat_build.context(self.root, self.folder)['manifest'], before['manifest'])
        approved = project_plan.status(self.root, self.folder)['approved']
        chat_build.harness(self.folder).revoke(approved['contract_id'], approver='johnathan', reason='SYNTHETIC owner revocation')
        with self.assertRaises(ValueError): self.prepare('recipe', recipe_id='movement-smoothing', settings={})
        self.assertEqual(chat_build.context(self.root, self.folder)['manifest'], before['manifest'])

    def test_recipe_metadata_zip_handoff_restore_and_final_acceptance(self):
        self.approve_scope(); baseline = self.apply('sample')
        self.apply('recipe', 'movement-export-00001', recipe_id='movement-smoothing', settings={})
        final = self.apply('recipe', 'jumping-export-000001', recipe_id='forgiving-jumps', settings={})
        expected = chat_build.context(self.root, self.folder)['mechanics']
        raw, _ = self.app.export_version(final)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            meta = json.loads(archive.read('ember-build.json'))
            self.assertEqual(meta['mechanics'], expected)
            self.assertEqual(archive.read('mechanic-config.js').decode(),
                             project_versions.snapshot(self.root, self.folder, final)['files']['mechanic-config.js'])
        handoff, _ = self.app.export_handoff(self.sid, final)
        with zipfile.ZipFile(io.BytesIO(handoff)) as archive:
            report = json.loads(archive.read('project-report.json'))
            self.assertEqual(report['mechanics'], expected)
            self.assertFalse(report['project_plan']['tasks'][0]['accepted'])
        restore = project_versions.propose_restore(self.root, self.folder, baseline, final, 'restore-mechanic-00001')
        self.app.respond(restore, 'approve', 'SYNTHETIC reviewed forward restoration')
        self.assertEqual(chat_build.context(self.root, self.folder)['mechanics']['recipes'], [])
        self.assertEqual(len(project_versions.history(self.folder)), 4)
        self.app.plan_control(self.sid, 'accept', plan_ref=self.plan_ref, task_id='task-1', build_ref=restore)
        self.assertEqual(project_plan.status(self.root, self.folder)['tasks'][0]['state'], 'human_accepted')

    def test_required_checks_and_supported_source_bindings_remain_frozen(self):
        self.approve_scope(); self.apply('sample')
        saved = self.app.mechanic_control(self.sid, 'checks', revision=0)
        files = {row['path']:row['content'] for row in chat_build.context(self.root, self.folder)['files']}
        bound = mechanic_workflow.capture_binding(files, 'exact-build-ref', saved)
        self.assertEqual(bound['plan_sha256'], saved['sha256'])
        self.assertEqual(bound['plan_revision'], saved['revision'])
        self.assertEqual(bound['build_ref'], 'exact-build-ref')
        self.assertEqual(bound['source_manifest'], chat_build.context(self.root, self.folder)['manifest'])
        old_hash = saved['sha256']
        altered = deepcopy(saved['plan']); altered['scenarios'][1]['steps'][-1]['value'] = '999'
        revised = gameplay.save(self.folder, altered, saved['revision'])
        self.assertNotEqual(old_hash, revised['sha256'])
        self.assertEqual(bound['plan_sha256'], old_hash)
        broken = dict(files); broken['app.js'] += '\n/* incompatible interaction change */'
        self.assertTrue(mechanic_workflow.review(mechanic_recipes.inspect(files), broken)['blockers'])
        self.assertFalse(mechanic_workflow.status(broken)['supported'])
