"""Evidence validation distinguishes a supported judgment from a bare positive verdict."""
from copy import deepcopy
import unittest

from ember_harness import task_quality
from quality_fixture import assessments, comparison


class TaskQualityTests(unittest.TestCase):
    def setUp(self):
        self.plan = dict(goal='Make the delivery action clear',
            project_plan=dict(document=dict(scope=dict(core_loop='Pick up and deliver',
                out_of_scope=['Combat'], asset_budget={'external': 0}, done_criteria=['Enjoyable to replay']),
                art_direction=dict(style='Warm and readable'))), brief=dict(fields={'controls': 'Space'}),
            gameplay_plan=dict(plan=dict(scenarios=[dict(name='Delivery and reset')])) )
        self.quality = task_quality.prepare(self.plan)
        self.files = {'app.js': 'const deliveryLabel = "Deliver parcel";'}
        self.observed = dict(viewports=[dict(screenshot=name+'.png', sha256='f'*64) for name in ('desktop', 'mobile')],
            gameplay=dict(scenarios=[dict(outcome='passed')]))
        self.verdict = dict(meets_task=True, preserves_scope=True, issues=[], summary='Synthetic opinion',
            criteria=assessments(dict(quality=self.quality, files=self.files)))

    def review(self, verdict=None):
        return task_quality.review(self.quality, verdict or self.verdict, self.files, self.observed)

    def test_supported_review_keeps_human_experience_pending(self):
        result = self.review()
        self.assertEqual(result['blockers'], [])
        self.assertEqual(result['human_pending'], ['human-experience'])
        self.plan['goal'] = 'Later draft change'
        self.assertEqual(self.quality['criteria'][0]['expectation'], 'Make the delivery action clear')

    def test_bare_positive_missing_duplicate_and_unknown_criteria_block(self):
        for change in ('empty', 'missing', 'duplicate', 'unknown'):
            verdict = deepcopy(self.verdict)
            rows = verdict['criteria']
            if change == 'empty': rows.clear()
            if change == 'missing': rows.pop()
            if change == 'duplicate': rows.append(deepcopy(rows[0]))
            if change == 'unknown': rows[0]['id'] = 'invented'
            with self.subTest(change=change):
                self.assertTrue(self.review(verdict)['blockers'])

    def test_unobserved_or_unmet_required_criteria_block(self):
        for status in ('not_met', 'not_observed'):
            verdict = deepcopy(self.verdict)
            verdict['criteria'][0].update(status=status, reason='No observable delivery feedback')
            with self.subTest(status=status):
                self.assertIn('No observable delivery feedback', ' '.join(self.review(verdict)['blockers']))

    def test_invented_evidence_wrong_method_and_missing_mobile_block(self):
        for change in ('source', 'capture', 'scenario', 'empty', 'mobile'):
            verdict = deepcopy(self.verdict)
            if change == 'source': verdict['criteria'][0]['evidence'][0]['detail'] = 'This code does not exist'
            if change == 'capture': verdict['criteria'][2]['evidence'][0]['ref'] = '../../fake.png'
            if change == 'scenario': verdict['criteria'][3]['evidence'][0]['ref'] = '9'
            if change == 'empty': verdict['criteria'][0]['evidence'] = []
            if change == 'mobile': verdict['criteria'][2]['evidence'].pop()
            with self.subTest(change=change):
                self.assertTrue(self.review(verdict)['blockers'])

    def test_model_cannot_claim_human_acceptance_or_override_failed_gameplay(self):
        verdict = deepcopy(self.verdict)
        verdict['criteria'][-1]['status'] = 'met'
        self.assertTrue(self.review(verdict)['blockers'])
        self.observed['gameplay']['scenarios'][0]['outcome'] = 'failed'
        self.assertTrue(self.review()['blockers'])

    def test_game_ui_needs_both_viewports_and_blocks_a_bare_positive_verdict(self):
        for criterion_id in ('game-ui-integration', 'game-ui-style'):
            for defect in ('not_met', 'missing_mobile', 'source_only'):
                verdict = deepcopy(self.verdict)
                row = next(c for c in verdict['criteria'] if c['id'] == criterion_id)
                if defect == 'not_met':
                    row.update(status='not_met', reason='HUD is a detached footer with mismatched card styling')
                elif defect == 'missing_mobile':
                    row['evidence'].pop()
                else:
                    row['evidence'] = [dict(kind='source', ref='app.js', detail=self.files['app.js'])]
                with self.subTest(criterion=criterion_id, defect=defect):
                    self.assertTrue(any(b.startswith(criterion_id + ':') for b in self.review(verdict)['blockers']))

    def test_verifier_schema_requires_criteria_without_changing_specialized_schema(self):
        base = dict(required=['summary'], properties=dict(summary=dict(type='string')))
        changed = task_quality.schema(base)
        self.assertIn('criteria', changed['required'])
        self.assertNotIn('criteria', base['required'])

    def test_abbreviated_or_explained_source_evidence_never_counts_as_verbatim(self):
        for excerpt in ('const deliveryLabel ... "Deliver parcel";',
                        self.files['app.js'] + ' preserves the delivery label'):
            verdict = deepcopy(self.verdict)
            verdict['criteria'][0]['evidence'][0]['detail'] = excerpt
            with self.subTest(excerpt=excerpt):
                self.assertTrue(any(b.startswith('task: unsupported source') for b in self.review(verdict)['blockers']))

    def test_panel_evidence_is_supported_only_when_bound_to_browser_observations(self):
        row = next(c for c in self.verdict['criteria'] if c['id'] == 'game-ui-integration')
        row['evidence'].append(dict(kind='capture', ref='mobile-panel.png', detail='The open help panel fits the stage'))
        self.assertTrue(any('unsupported capture' in b for b in self.review()['blockers']))
        self.observed['viewports'][1].update(panel_screenshot='mobile-panel.png', panel_sha256='a'*64)
        self.assertEqual(self.review()['blockers'], [])

    def test_platformer_review_requires_visible_joins_and_source_geometry(self):
        self.plan['brief']['fields']['goal']='Explore a jungle platformer'
        quality=task_quality.prepare(self.plan)
        data=dict(quality=quality,files=self.files)
        verdict=dict(criteria=assessments(data))
        self.assertEqual(task_quality.review(quality,verdict,self.files,self.observed)['blockers'],[])
        visual=next(r for r in verdict['criteria'] if r['id']=='platformer-terrain')
        visual['evidence']=[dict(kind='source',ref='app.js',detail=self.files['app.js'])]
        geometry=next(r for r in verdict['criteria'] if r['id']=='platformer-geometry')
        geometry['evidence']=[dict(kind='capture',ref='desktop.png',detail='SYNTHETIC attractive terrain')]
        blockers=task_quality.review(quality,verdict,self.files,self.observed)['blockers']
        self.assertTrue(any('platformer-terrain: review both' in b for b in blockers))
        self.assertTrue(any('platformer-geometry: task and preservation judgments need a source' in b for b in blockers))

    def test_comparison_requires_paired_evidence_and_meaningful_improvement(self):
        baseline = {'app.js': 'const deliveryLabel = "Unclear old action";'}
        frozen = dict(baseline_status='captured')
        verdict = dict(comparison=comparison(dict(files=self.files, baseline_files=baseline, comparison=frozen)))
        check = lambda value: task_quality.compare(frozen, value, self.files, baseline, self.observed, self.observed)
        self.assertEqual(check(verdict)['blockers'], [])
        for defect in ('unchanged', 'loss', 'missing_before', 'forged_before', 'missing_after', 'missing_scenario'):
            value = deepcopy(verdict)
            if defect == 'unchanged': value['comparison'].update(improved=False, improvement='Only the background changed; delivery is still unclear')
            elif defect == 'loss': value['comparison']['losses'] = ['Restart no longer resets the delivery state']
            elif defect == 'missing_before': value['comparison']['evidence'] = [e for e in value['comparison']['evidence'] if e['kind'] != 'baseline_capture']
            elif defect == 'forged_before': next(e for e in value['comparison']['evidence'] if e['kind'] == 'baseline_source')['detail'] = 'This was never in the starting source'
            elif defect == 'missing_after': value['comparison']['evidence'] = [e for e in value['comparison']['evidence'] if e['kind'] != 'capture']
            else: value['comparison']['evidence'] = [e for e in value['comparison']['evidence'] if e['kind'] != 'gameplay']
            with self.subTest(defect=defect):
                self.assertTrue(check(value)['blockers'])
        self.assertTrue(check({})['blockers'])
        unchanged = dict(comparison=comparison(dict(files=baseline, baseline_files=baseline, comparison=frozen)))
        self.assertTrue(task_quality.compare(frozen, unchanged, baseline, baseline, self.observed, self.observed)['blockers'])

    def test_blank_comparison_does_not_invent_before_evidence_or_change_legacy_schema(self):
        frozen = dict(baseline_status='no_playable_baseline')
        verdict = dict(comparison=comparison(dict(files=self.files, comparison=frozen)))
        result = task_quality.compare(frozen, verdict, self.files, {}, self.observed, None)
        self.assertEqual(result['blockers'], [])
        verdict['comparison']['evidence'].append(dict(kind='baseline_capture', ref='desktop.png', detail='Invented starting game'))
        self.assertTrue(task_quality.compare(frozen, verdict, self.files, {}, self.observed, None)['blockers'])
        self.assertNotIn('comparison', task_quality.VERDICT_SCHEMA['required'])
        self.assertIn('comparison', task_quality.comparison_schema(task_quality.VERDICT_SCHEMA)['required'])
