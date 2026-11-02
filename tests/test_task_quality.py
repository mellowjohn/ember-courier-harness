"""Evidence validation distinguishes a supported judgment from a bare positive verdict."""
from copy import deepcopy
import unittest

from ember_harness import task_quality
from quality_fixture import assessments


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

    def test_verifier_schema_requires_criteria_without_changing_specialized_schema(self):
        base = dict(required=['summary'], properties=dict(summary=dict(type='string')))
        changed = task_quality.schema(base)
        self.assertIn('criteria', changed['required'])
        self.assertNotIn('criteria', base['required'])

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
