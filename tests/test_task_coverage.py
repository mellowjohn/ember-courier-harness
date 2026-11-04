"""Coverage intent stays advisory; every configured browser scenario stays required."""
from copy import deepcopy
import unittest

from ember_harness import gameplay, task_coverage
from ember_harness.core import digest


def saved(plan, revision=1):
    return dict(plan=plan, revision=revision, sha256=digest(plan))


def scenario(name='Start', viewport='desktop', coverage=None, steps=None):
    value = dict(name=name, viewport=viewport, steps=steps or [dict(action='visible', selector='#start')])
    if coverage is not None:
        value['coverage'] = coverage
    return value


def observed(plan, failed_index=None):
    rows = []
    for index, row in enumerate(plan['scenarios']):
        failure = index == failed_index
        rows.append(dict(name=row['name'], viewport=row['viewport'],
                         outcome='failed' if failure else 'passed', errors=[], steps=[
                             dict(index=i, status='failed' if failure and i == len(row['steps'])-1 else 'passed',
                                  observed='SYNTHETIC browser observation')
                             for i in range(len(row['steps']))]))
    return dict(plan_sha256=digest(plan), outcome='failed' if failed_index is not None else 'passed', scenarios=rows)


class TaskCoverageTests(unittest.TestCase):
    def test_old_plan_is_unchanged_and_names_do_not_claim_coverage(self):
        plan = dict(title='Old saved plan', scenarios=[scenario('Success, failure, reset and repeat touch keyboard')])
        before = deepcopy(plan)
        self.assertEqual(gameplay.validate(plan), before)
        review = task_coverage.analyze('Improve first play', dict(fields=dict(controls='Touch and keyboard')), saved(plan))
        self.assertEqual(review['missing'], list(gameplay.COVERAGE_PATHS) + ['keyboard', 'touch'])
        self.assertEqual(review['expectation_mapping']['basis'], 'review_required')
        self.assertEqual(review['expectation_mapping']['scenario_refs'][0]['name'], plan['scenarios'][0]['name'])
        self.assertEqual(plan, before)

    def test_explicit_intent_and_input_paths_are_distinct_and_frozen(self):
        plan = dict(title='Bounded loop', scenarios=[
            scenario(coverage=['discoverability', 'success'], steps=[
                dict(action='press', key='Enter'), dict(action='visible', selector='#playing')]),
            scenario('Touch retry', 'mobile', ['reset', 'repeated_play'], steps=[
                dict(action='tap', selector='#restart'), dict(action='visible', selector='#playing')])])
        packet = saved(plan, revision=8)
        review = task_coverage.analyze('Make restart reliable', {}, packet)
        rows = {row['id']:row for row in review['paths']}
        self.assertEqual(review['plan_revision'], 8)
        self.assertEqual(review['plan_sha256'], digest(plan))
        self.assertEqual(review['missing'], ['failure'])
        self.assertEqual(rows['reset']['basis'], 'declared_intent')
        self.assertEqual(rows['keyboard']['basis'], 'observed_input')
        self.assertEqual(rows['touch']['scenario_refs'], [dict(index=1, name='Touch retry', viewport='mobile')])
        self.assertEqual(review['editor_limits'], dict(scenario_slots=2, action_budget_remaining_ms=86000,
                                                     steps_per_scenario=32))
        packet['plan']['scenarios'][1]['coverage'].clear()
        self.assertEqual(rows['reset']['status'], 'configured')
        with self.assertRaisesRegex(ValueError, 'exact saved'):
            task_coverage.analyze('Make restart reliable', {}, packet)

    def test_input_without_a_following_assertion_is_not_covered(self):
        plan = dict(title='Inputs alone', scenarios=[scenario(steps=[
            dict(action='visible', selector='#playing'), dict(action='press', key='Enter')]),
            scenario('Touch alone', 'mobile', steps=[
                dict(action='visible', selector='#playing'), dict(action='tap', selector='#start')])])
        review = task_coverage.analyze('Respond to input', {}, saved(plan))
        self.assertIn('keyboard', review['missing'])
        self.assertIn('touch', review['missing'])
        plan['scenarios'][0]['steps'].append(dict(action='text', selector='#score', value='1'))
        self.assertNotIn('keyboard', task_coverage.analyze('Respond to input', {}, saved(plan))['missing'])

    def test_coverage_is_bounded_data_with_no_implicit_defaults(self):
        for labels in (['success', 'success'], ['evaluate'], 'reset', [None], [dict(action='approve')]):
            plan = dict(title='Invalid declaration', scenarios=[scenario(coverage=labels)])
            with self.subTest(labels=labels), self.assertRaisesRegex(ValueError, 'coverage'):
                gameplay.validate(plan)
        plan = dict(title='Empty', scenarios=[])
        review = task_coverage.analyze('Start first game', {}, saved(plan, revision=0))
        self.assertEqual(len(review['missing']), 7)
        self.assertEqual(review['expectation_mapping']['scenario_refs'], [])
        self.assertEqual(review['editor_limits']['scenario_slots'], 4)

    def test_metadata_changes_invalidate_results_and_cannot_waive_failures(self):
        plan = dict(title='Complete loop', scenarios=[
            scenario('Happy path', coverage=['success']),
            scenario('Reset', coverage=['reset']),
            scenario('Second play', coverage=['repeated_play']),
            scenario('Touch', 'mobile', steps=[
                dict(action='tap', selector='#start'), dict(action='visible', selector='#playing')])])
        for index in (1, 2, 3):
            result = observed(plan, failed_index=index)
            with self.subTest(path=plan['scenarios'][index]['name']):
                self.assertEqual(gameplay.validate_result(plan, result)['outcome'], 'failed')
                result['outcome'] = 'passed'
                with self.assertRaisesRegex(ValueError, 'differs'):
                    gameplay.validate_result(plan, result)
        result = observed(plan)
        plan['scenarios'][0]['coverage'].append('discoverability')
        with self.assertRaisesRegex(ValueError, 'frozen plan'):
            gameplay.validate_result(plan, result)


if __name__ == '__main__':
    unittest.main()
