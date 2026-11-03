"""Original reference physics, frozen recipe proposals and bounded observations."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from ember_harness import chat_build, gameplay, mechanic_recipes as recipes

NODE = shutil.which('node')
RUNTIME = recipes.RESOURCE / 'mechanic-runtime.js'


class RecipeTests(unittest.TestCase):
    def test_finite_known_bounded_settings_and_exact_versions(self):
        for settings in ([], False, {'surprise': 1}, {'max_speed': True}, {'max_speed': float('nan')},
                         {'max_speed': float('inf')}, {'max_speed': 481}, {'acceleration_ms': 20.5},
                         {'acceleration_ms': 0}, {'reversal_multiplier': .9}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                recipes.resolve('movement-smoothing', settings)
        for version in (True, 0, 2, 1.0):
            with self.subTest(version=version), self.assertRaises(ValueError):
                recipes.resolve('forgiving-jumps', version=version)
        for value in (-1, 201, float('nan'), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                recipes.resolve('forgiving-jumps', {'coyote_ms': value})
        self.assertEqual(recipes.resolve('forgiving-jumps', {'coyote_ms': 0})['settings']['coyote_ms'], 0)

    def test_catalog_drafts_and_proposals_cannot_redirect_frozen_settings(self):
        frozen = recipes.resolve('movement-smoothing', {'max_speed': 300})
        catalog = recipes.catalog(); catalog[0]['settings']['max_speed']['default'] = 999
        values = deepcopy(frozen); values['settings']['max_speed'] = 400
        with self.assertRaises(ValueError): recipes.validate_snapshot(values)
        self.assertEqual(recipes.validate_snapshot(frozen)['settings']['max_speed'], 300)
        self.assertIn('300 px/s', recipes.request(frozen))
        self.assertEqual(recipes.resolve('movement-smoothing')['settings']['max_speed'], 240)

    def test_only_reviewed_config_changes_and_unsupported_games_fail_closed(self):
        base = recipes.reference_files([])
        chat_build.validate_files(base)
        proposed = recipes.apply(base, recipes.resolve('forgiving-jumps'))
        self.assertEqual([name for name in base if base[name] != proposed[name]], ['mechanic-config.js'])
        self.assertEqual(recipes.inspect(base)['settings']['coyote_ms'], 0)
        self.assertEqual(recipes.inspect(proposed)['settings']['coyote_ms'], 100)
        self.assertEqual(base['app.js'], proposed['app.js'])
        for field in ('index.html', 'app.js', 'mechanic-runtime.js', 'mechanic-config.js'):
            files = dict(proposed); files[field] += '\n/* unreviewed source */'
            with self.subTest(field=field), self.assertRaises(ValueError): recipes.inspect(files)
        with self.assertRaises(ValueError): recipes.inspect({'index.html': '<h1>Arbitrary game</h1>'})
        # Styling does not change runtime compatibility, but its bytes stay in
        # the source binding and existing browser layout checks still apply.
        styled = dict(proposed, **{'style.css': proposed['style.css'] + '\nbody{color:white}'})
        self.assertEqual(recipes.inspect(styled), recipes.inspect(proposed))
        self.assertNotEqual(recipes.binding(styled, 'build', 1), recipes.binding(proposed, 'build', 1))

    def test_saved_input_plans_use_existing_limits_and_separate_simulation_from_input(self):
        plans = recipes.gameplay_plans()
        self.assertEqual(len(plans), 2)
        for plan in plans: gameplay.validate(plan)
        self.assertIn('simulation', plans[0]['title'])
        self.assertEqual({s['viewport'] for s in plans[1]['scenarios']}, {'desktop', 'mobile'})


@unittest.skipUnless(NODE, 'Optional Node runtime needed for deterministic JavaScript physics checks')
class PhysicsTests(unittest.TestCase):
    def evaluate(self, body, config=None):
        script = "const fs=require('node:fs'),vm=require('node:vm');const input=JSON.parse(fs.readFileSync(0,'utf8'));const moduleObject={exports:{}};vm.runInNewContext(input.runtime,{module:moduleObject,exports:moduleObject.exports});const api=moduleObject.exports;const config=input.config;" + body
        result = subprocess.run([NODE, '-e', script], input=json.dumps(dict(runtime=RUNTIME.read_text(),
            config=config or recipes.configuration())), text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_default_legacy_and_edge_settings_match_host_checked_observations(self):
        choices = [[], None, [recipes.resolve('movement-smoothing', dict(max_speed=480, acceleration_ms=23,
            stopping_ms=27, reversal_multiplier=1.5)), recipes.resolve('forgiving-jumps', dict(coyote_ms=200, jump_buffer_ms=42))]]
        for choice in choices:
            files = recipes.reference_files(choice); config = recipes.inspect(files)
            report = self.evaluate('console.log(JSON.stringify(api.verify(config)));', config)
            with self.subTest(settings=config['settings']):
                self.assertEqual(report['outcome'], 'passed')
                self.assertTrue(recipes.validate_report(recipes.binding(files, 'synthetic-build', 3), report)['qualified'])

    def test_window_boundaries_consumption_and_unchanged_ordinary_trajectory(self):
        result = self.evaluate("console.log(JSON.stringify(api.verify(config)));")
        rows = {row['id']:row['observed'] for row in result['checks']}
        self.assertEqual((rows['coyote']['inside_steps'], rows['coyote']['inside_jumps'], rows['coyote']['outside_jumps']), (12, 1, 0))
        self.assertEqual((rows['buffer']['inside_steps'], rows['buffer']['inside_jumps'], rows['buffer']['outside_jumps']), (12, 1, 0))
        self.assertEqual(rows['single-jump'], dict(held_jumps=1, repressed_in_air_jumps=1, reset_jumps=0))
        self.assertEqual(rows['trajectory']['maximum_difference'], 0)
        early = self.evaluate("const m=api.create(config.settings);m.pressJump();m.step();m.advanceSteps(3);m.releaseJump();m.pressJump();m.step();console.log(JSON.stringify(m.snapshot()));")
        self.assertEqual(early['jumpCount'], 1, 'A repress inside the coyote window cannot reuse a consumed jump')

    def test_acceleration_release_neutral_reversal_and_render_rates(self):
        data = self.evaluate("const m=api.create(config.settings);const velocities=[];for(let i=0;i<24;i++)velocities.push(m.step({right:true}).vx);const stop=[];for(let i=0;i<12;i++)stop.push(m.step({right:false}).vx);m.reset();m.advanceSteps(24,{right:true});const reverse=[];for(let i=0;i<7;i++)reverse.push(m.step({left:true,right:false}).vx);console.log(JSON.stringify({velocities,stop,reverse,report:api.verify(config)}));")
        self.assertEqual(data['velocities'], list(range(10, 241, 10)))
        self.assertEqual(data['stop'], list(range(220, -1, -20)))
        self.assertEqual(data['reverse'], [200, 160, 120, 80, 40, 0, -10])
        positions = next(row['observed']['positions'] for row in data['report']['checks'] if row['id']=='render-rates')
        self.assertEqual(positions, [257, 257, 257])

    def test_no_held_input_after_clear_and_step_counts_are_bounded(self):
        result = self.evaluate("const m=api.create(config.settings);m.advanceSteps(4,{right:true});m.pressJump();m.clearInput();const before=m.snapshot();m.advanceSteps(12);const after=m.snapshot();const errors=[];for(const n of [-1,601,1.5,Infinity]){try{m.advanceSteps(n)}catch(e){errors.push(e.message)}}console.log(JSON.stringify({before,after,errors}));")
        self.assertFalse(result['before']['pendingJump']); self.assertFalse(result['before']['jumpHeld'])
        self.assertFalse(result['before']['right']); self.assertEqual(result['after']['vx'], 0)
        self.assertEqual(len(result['errors']), 4)

    def test_broken_mechanic_and_incomplete_or_forged_positive_observations_do_not_qualify(self):
        files = recipes.reference_files(); bound = recipes.binding(files, 'synthetic-build', 1)
        report = self.evaluate('console.log(JSON.stringify(api.verify(config)));')
        missing = deepcopy(report); missing['checks'][0]['observed'] = {}
        with self.assertRaises(ValueError): recipes.validate_report(bound, missing)
        forged = deepcopy(report); forged['checks'][3]['observed']['positions'] = [0, 0, 0]
        with self.assertRaises(ValueError): recipes.validate_report(bound, forged)
        changed = deepcopy(report); changed['settings']['coyote_ms'] = 150
        with self.assertRaises(ValueError): recipes.validate_report(bound, changed)
        broken = RUNTIME.read_text().replace('settings.acceleration_ms===0?direction*cap:', 'true?direction*cap:')
        script = "const vm=require('node:vm');const d=JSON.parse(require('node:fs').readFileSync(0,'utf8'));const m={exports:{}};vm.runInNewContext(d.source,{module:m,exports:m.exports});console.log(JSON.stringify(m.exports.verify(d.config)));"
        result = subprocess.run([NODE,'-e',script], input=json.dumps(dict(source=broken, config=recipes.inspect(files))), text=True, capture_output=True, timeout=15)
        bad = json.loads(result.stdout)
        self.assertEqual(bad['outcome'], 'failed')
        with self.assertRaises(ValueError): recipes.validate_report(bound, bad)
        bad['outcome'] = 'passed'
        for row in bad['checks']: row['status'] = 'passed'
        with self.assertRaises(ValueError): recipes.validate_report(bound, bad)
