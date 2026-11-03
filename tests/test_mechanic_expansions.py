"""Expanded reference rules use real Node simulation and independent host expectations."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from ember_harness import chat_build, gameplay, mechanic_expansions as expanded, mechanic_recipes as recipes, mechanic_workflow

NODE = shutil.which('node')
RUNTIME = expanded.RESOURCE / 'advanced-runtime.js'


class ExpandedRecipeTests(unittest.TestCase):
    def test_settings_versions_and_frozen_definitions_fail_closed(self):
        for name in expanded.DEFINITIONS:
            definition = expanded.DEFINITIONS[name]
            self.assertEqual(expanded.resolve(name)['target'], expanded.PROFILE)
            for field, rules in definition['settings'].items():
                for value in (True, float('inf'), float('nan'), rules['min'] - 1, rules['max'] + 1, .5):
                    with self.subTest(recipe=name, field=field, value=value), self.assertRaises(ValueError):
                        expanded.resolve(name, {field: value})
            for version in (True, 0, 2, 1.0):
                with self.assertRaises(ValueError): expanded.resolve(name, version=version)
            with self.assertRaises(ValueError): expanded.resolve(name, {'hidden_authority': 1})
        saved = expanded.resolve('camera-follow')
        changed = deepcopy(saved); changed['definition']['settings']['camera_deadzone_px']['default'] = 200
        with self.assertRaises(ValueError): expanded.validate_snapshot(changed)
        changed = deepcopy(saved); changed['settings']['camera_deadzone_px'] = 200
        with self.assertRaises(ValueError): expanded.validate_snapshot(changed)

    def test_upgrade_preserves_both_existing_recipe_snapshots_and_reviews_full_source(self):
        movement = recipes.resolve('movement-smoothing', {'max_speed': 300})
        jumping = recipes.resolve('forgiving-jumps', {'coyote_ms': 125})
        original = recipes.reference_files([movement, jumping]); retained = deepcopy(original)
        candidate = expanded.apply(original, expanded.resolve('camera-follow'))
        chat_build.validate_files(candidate)
        state = expanded.inspect(candidate)
        self.assertEqual(original, retained)
        self.assertEqual(state['settings']['max_speed'], 300)
        self.assertEqual(state['settings']['coyote_ms'], 125)
        self.assertIn(movement, state['recipes']); self.assertIn(jumping, state['recipes'])
        self.assertEqual(candidate['mechanic-runtime.js'], original['mechanic-runtime.js'])
        self.assertIn('advanced-runtime.js', candidate)
        self.assertNotEqual(candidate['app.js'], original['app.js'])
        next_candidate = expanded.apply(candidate, expanded.resolve('seeded-levels', {'level_seed': 404}))
        self.assertEqual([name for name in candidate if candidate[name] != next_candidate[name]], ['mechanic-config.js'])
        self.assertEqual(expanded.inspect(next_candidate)['settings']['camera_deadzone_px'], 96)

    def test_canonical_sources_full_manifest_and_plan_binding(self):
        files = expanded.reference_files()
        for name in ('index.html', 'app.js', 'mechanic-runtime.js', 'advanced-runtime.js', 'mechanic-config.js'):
            altered = dict(files); altered[name] += '\n/* changed */'
            with self.subTest(name=name), self.assertRaises(ValueError): expanded.inspect(altered)
        styled = dict(files); styled['style.css'] += '\nbody{color:white}\n'
        self.assertEqual(expanded.inspect(files), expanded.inspect(styled))
        original = expanded.binding(files, 'build-one', 2, 'a' * 64)
        self.assertNotEqual(original, expanded.binding(styled, 'build-one', 2, 'a' * 64))
        self.assertNotEqual(original, expanded.binding(files, 'build-two', 2, 'a' * 64))
        self.assertNotEqual(original, expanded.binding(files, 'build-one', 3, 'b' * 64))
        for plan in expanded.gameplay_plans(): gameplay.validate(plan)

    def test_expanded_configuration_cannot_impersonate_legacy_runtime(self):
        wrong = recipes.reference_files([])
        wrong[expanded.CONFIG_FILE] = expanded.reference_files([expanded.resolve('camera-follow')])[expanded.CONFIG_FILE]
        with self.assertRaises(ValueError): recipes.inspect(wrong)
        with self.assertRaises(ValueError): recipes.binding(wrong, 'wrong profile', 1)
        self.assertIsNone(mechanic_workflow.binding(wrong))
        for recipe in (recipes.resolve('movement-smoothing'), recipes.resolve('forgiving-jumps')):
            forged = dict(recipe, target=expanded.PROFILE)
            with self.assertRaises(ValueError): recipes.validate_snapshot(forged)
            with self.assertRaises(ValueError): expanded.validate_snapshot(forged)

    def test_upgrade_cannot_drop_or_retune_previous_recipes_behind_positive_profile_detection(self):
        movement = recipes.resolve('movement-smoothing', {'max_speed': 300})
        jumping = recipes.resolve('forgiving-jumps', {'coyote_ms': 125})
        original = recipes.reference_files([movement, jumping]); expected = recipes.inspect(original)
        camera = expanded.resolve('camera-follow')
        correct = expanded.apply(original, camera)
        self.assertFalse(mechanic_workflow.review(expected, correct)['blockers'])
        for rows in ([camera], [movement, camera],
                     [recipes.resolve('movement-smoothing', {'max_speed': 400}), jumping, camera]):
            with self.subTest(rows=rows):
                self.assertTrue(mechanic_workflow.review(expected, expanded.reference_files(rows))['blockers'])
        # Retuning remains a separate supported v2 proposal after the full
        # migration preserved its original settings.
        retuned = expanded.apply(correct, recipes.resolve('movement-smoothing', {'max_speed': 400}))
        self.assertFalse(mechanic_workflow.review(expanded.inspect(correct), retuned)['blockers'])
        self.assertTrue(mechanic_workflow.review(expanded.inspect(correct), original)['blockers'])

    def test_host_seed_generator_has_reachable_safe_distinct_reproducible_geometry(self):
        for count in range(6, 13):
            geometries = []
            for seed in (0, 1, 17, 29, 404, 1729, 2147483647):
                result = expanded.layout(seed, count)
                self.assertEqual(result, expanded.layout(seed, count))
                self.assertTrue(result['reachable'] and result['spawn_safe'] and result['goal_safe'])
                self.assertEqual(result['tops'][:2], [360, 360]); self.assertEqual(result['tops'][-2:], [360, 360])
                if seed in (17, 29): geometries.append((result['tops'], result['hazards']))
            self.assertNotEqual(*geometries)


@unittest.skipUnless(NODE, 'Optional Node runtime required for deterministic reference simulation')
class ExpandedRuntimeTests(unittest.TestCase):
    def evaluate(self, body, recipes_rows=None, source=None):
        config = expanded.configuration(recipes_rows)
        script = """const fs=require('node:fs'),vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8')),output={exports:{}};
const base=require(input.base);vm.runInNewContext(input.source,{module:output,exports:output.exports,require:()=>base});
const api=output.exports,config=input.config;""" + body
        result = subprocess.run([NODE, '-e', script], input=json.dumps(dict(
            base=str(expanded.RESOURCE / 'mechanic-runtime.js'), source=source or RUNTIME.read_text(encoding='utf-8'), config=config)),
            text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def report(self, rows=None, source=None):
        return self.evaluate('console.log(JSON.stringify(api.verify(config)));', rows, source)

    def test_all_twelve_observations_pass_independent_host_expectations_at_bounds(self):
        configurations = [None, [], [expanded.resolve('camera-follow', dict(camera_deadzone_px=240, camera_easing_ms=600, reduced_motion=1))],
            [expanded.resolve('impact-protection', dict(hit_stop_ms=120, invincibility_ms=0))],
            [expanded.resolve('impact-protection', dict(hit_stop_ms=0, invincibility_ms=2000))],
            [expanded.resolve('enemy-states', dict(enemy_detection_px=120, enemy_attack_px=90, enemy_hysteresis_px=80, enemy_cooldown_ms=200))],
            [expanded.resolve('seeded-levels', dict(level_seed=2147483647, level_sections=6))],
            [recipes.resolve('movement-smoothing', dict(max_speed=480, acceleration_ms=23, stopping_ms=27, reversal_multiplier=1.5)),
             recipes.resolve('forgiving-jumps', dict(coyote_ms=200, jump_buffer_ms=42)), expanded.resolve('seeded-levels', {'level_sections': 12})]]
        for rows in configurations:
            with self.subTest(rows=rows):
                observed = self.report(rows)
                self.assertEqual(observed['outcome'], 'passed')
                self.assertEqual(len(observed['checks']), 12)
                bound = expanded.binding(expanded.reference_files(rows), 'SYNTHETIC build', 2, 'a' * 64)
                self.assertTrue(expanded.validate_report(bound, observed)['qualified'])

    def test_camera_deadzone_easing_clamps_teleport_and_fixed_render_rates(self):
        result = self.evaluate("""const cam=api.camera(config.settings);const inside=cam.update(230),first=cam.update(700);
const g=api.create(config.settings);g.scenario('camera');const start=g.snapshot();g.step();const firstFrame=g.snapshot();g.teleport(936);const goal=g.snapshot();g.reset();
console.log(JSON.stringify({inside,first,start,firstFrame,goal,reset:g.snapshot(),report:api.verify(config).checks.find(r=>r.id==='camera')}));""")
        self.assertEqual(result['inside'], 0)
        self.assertAlmostEqual(result['first'], 452 / 24)
        self.assertEqual(result['start']['camera_x'], 0)
        self.assertAlmostEqual(result['firstFrame']['camera_x'], 92 / 24)
        self.assertEqual(result['goal']['camera_x'], 600); self.assertEqual(result['reset']['camera_x'], 0)
        positions = result['report']['observed']['positions']
        self.assertLess(max(positions) - min(positions), 1e-8)
        self.assertEqual(result['report']['observed']['reduced_motion'], 452)

    def test_moving_player_camera_route_matches_at_30_60_and_120_fps(self):
        result = self.evaluate("""const routes=[30,60,120].map(fps=>{const g=api.create(config.settings);g.scenario('movement');for(let i=0;i<fps;i++)g.advanceFrame(1/fps,{right:true});return g.snapshot();});console.log(JSON.stringify(routes));""")
        self.assertLess(max(row['x'] for row in result) - min(row['x'] for row in result), 2)
        self.assertLess(max(row['camera_x'] for row in result) - min(row['camera_x'] for row in result), 2)
        self.assertGreater(result[0]['camera_x'], 0)

    def test_fastest_player_stays_visible_with_largest_deadzone_and_slowest_easing(self):
        rows = [recipes.resolve('movement-smoothing', dict(max_speed=480, acceleration_ms=20, stopping_ms=10, reversal_multiplier=1)),
                expanded.resolve('camera-follow', dict(camera_deadzone_px=240, camera_easing_ms=600, reduced_motion=0))]
        result = self.evaluate("""const routes=[30,60,120].map(fps=>{const g=api.create(config.settings);g.scenario('movement');let outside=false;for(let i=0;i<fps*3;i++){g.advanceFrame(1/fps,{right:i<fps*2,left:i>=fps*2});const s=g.snapshot(),screen=s.x+12-s.camera_x;if(screen<12-1e-8||screen>388+1e-8||s.camera_x<0||s.camera_x>600)outside=true;}return {state:g.snapshot(),outside};});console.log(JSON.stringify(routes));""", rows)
        self.assertTrue(all(not row['outside'] for row in result))
        self.assertLess(max(row['state']['camera_x'] for row in result) - min(row['state']['camera_x'] for row in result), 2)

    def test_slowest_supported_player_can_reach_generated_goals_without_ground_hazard_damage(self):
        # Actual player physics, not only graph connectivity or a seed hash.
        # Hazards have a declared grounded contact zone; the route jumps before
        # entering it and releases after landing. No enemy recipe is installed.
        for seed in (1, 17, 29, 404, 2147483647):
            rows = [recipes.resolve('movement-smoothing', dict(max_speed=60, acceleration_ms=600, stopping_ms=600, reversal_multiplier=1)),
                    expanded.resolve('seeded-levels', dict(level_seed=seed, level_sections=12))]
            result = self.evaluate("""const g=api.create(config.settings);for(let i=0;i<2400&&g.state.x<936;i++){const upcoming=g.level.hazards.map(section=>(section+.5)*1000/g.level.sections).find(x=>x+12>=g.state.x);if(g.state.grounded){g.releaseJump();if(upcoming!==undefined&&g.state.x>=upcoming-38)g.pressJump();}g.step({right:true});}console.log(JSON.stringify(g.snapshot()));""", rows)
            with self.subTest(seed=seed):
                self.assertGreaterEqual(result['x'], 936)
                self.assertEqual(result['health'], 5)
                self.assertGreater(result['jumpCount'], 0)

    def test_damage_expiry_hitstop_pause_episode_bound_and_main_adapter(self):
        result = self.evaluate("""const d=api.damage(config.settings);d.contact();const stop=d.state.stopUntil;
for(let i=0;i<90;i++)d.step(true);const before=d.snapshot();d.contact();const after=d.snapshot();
const g=api.create(config.settings);g.scenario('damage');g.step();const hit=g.snapshot();g.setPaused(true);g.advanceSteps(60);const paused=g.snapshot();g.setPaused(false);g.advanceSteps(60);const protectedState=g.snapshot();g.advanceSteps(30);const expiry=g.snapshot();g.reset();
console.log(JSON.stringify({stop,before,after,hit,paused,protectedState,expiry,reset:g.snapshot()}));""")
        self.assertEqual(result['stop'], 8)
        self.assertEqual(result['before']['health'], 4); self.assertEqual(result['after']['health'], 3)
        self.assertEqual(result['after']['stopUntil'], 8)
        self.assertEqual(result['hit']['health'], 4); self.assertGreater(result['hit']['hit_stop_ms'], 0)
        self.assertEqual(result['paused']['tick'], result['hit']['tick'])
        self.assertEqual(result['paused']['hit_stop_ms'], result['hit']['hit_stop_ms'])
        self.assertEqual(result['protectedState']['health'], 4)
        self.assertEqual(result['expiry']['health'], 3)
        self.assertEqual(result['reset']['health'], 5); self.assertEqual(result['reset']['hit_stop_ms'], 0)

    def test_enemy_ranges_hysteresis_cooldown_actor_pause_and_reset(self):
        result = self.evaluate("""const g=api.create(config.settings);g.scenario('enemy-near');g.step();const noticed=g.snapshot();g.scenario('enemy-attack');g.step();const first=g.snapshot();g.setPaused(true);g.advanceSteps(120);const paused=g.snapshot();g.setPaused(false);g.advanceSteps(60);const waiting=g.snapshot();g.advanceSteps(60);const second=g.snapshot();g.reset();
console.log(JSON.stringify({noticed,first,paused,waiting,second,reset:g.snapshot(),report:api.verify(config).checks.find(r=>r.id==='enemy')}));""")
        self.assertEqual(result['noticed']['enemy']['mode'], 'chase')
        self.assertEqual(result['first']['enemy']['mode'], 'attack')
        self.assertEqual(result['first']['enemy']['attacks'], 1)
        self.assertEqual(result['paused']['enemy'], result['first']['enemy'])
        self.assertEqual(result['waiting']['enemy']['attacks'], 1)
        self.assertEqual(result['second']['enemy']['attacks'], 2)
        self.assertEqual(result['reset']['enemy']['mode'], 'patrol'); self.assertEqual(result['reset']['enemy']['attacks'], 0)
        observed = result['report']['observed']
        self.assertEqual(observed['attack_boundary'], 'attack'); self.assertEqual(observed['attack_exit'], 'chase')
        self.assertEqual(observed['jitter'], ['chase'] * 4); self.assertEqual(observed['disengaged'], 'patrol')

    def test_seeded_game_geometry_matches_host_and_restart_without_random_drift(self):
        for seed in (1, 17, 29, 404, 2147483647):
            rows = [expanded.resolve('seeded-levels', {'level_seed': seed})]
            observed = self.evaluate("""const g=api.create(config.settings),before=g.level;g.advanceSteps(120,{right:true});g.reset();console.log(JSON.stringify({before,after:g.level,state:g.snapshot()}));""", rows)
            expected = expanded.layout(seed, 10)
            self.assertEqual(observed['before']['hash'], expected['hash'])
            self.assertEqual(observed['before']['tops'], expected['tops'])
            self.assertEqual(observed['before']['hazards'], expected['hazards'])
            self.assertEqual(observed['before'], observed['after'])
            self.assertEqual(observed['state']['x'], 40)

    def test_source_mutations_cannot_forge_positive_camera_damage_enemy_or_layout_evidence(self):
        files = expanded.reference_files(); bound = expanded.binding(files, 'SYNTHETIC build', 1)
        report = self.report()
        mutations = [('camera', 'first', 0), ('damage', 'at_expiry', 4), ('enemy', 'attacks', 999), ('level', 'hash', '00000000')]
        for name, field, value in mutations:
            forged = deepcopy(report); next(row for row in forged['checks'] if row['id'] == name)['observed'][field] = value
            with self.subTest(name=name), self.assertRaises(ValueError): expanded.validate_report(bound, forged)
        missing = deepcopy(report); missing['checks'].pop()
        with self.assertRaises(ValueError): expanded.validate_report(bound, missing)
        changed = deepcopy(report); changed['settings']['level_seed'] = 404
        with self.assertRaises(ValueError): expanded.validate_report(bound, changed)
        broken_sources = [RUNTIME.read_text().replace('x+(desired-x)*amount', 'x'),
            RUNTIME.read_text().replace('state.tick<state.invincibleUntil', 'false'),
            RUNTIME.read_text().replace('state.tick+steps(settings.enemy_cooldown_ms)', 'state.tick'),
            RUNTIME.read_text().replace('360-(random()%3)*16', '360')]
        for index, source in enumerate(broken_sources):
            bad = self.report(source=source)
            for row in bad['checks']: row['status'] = 'passed'
            bad['outcome'] = 'passed'
            with self.subTest(index=index), self.assertRaises(ValueError): expanded.validate_report(bound, bad)

    def test_input_pause_step_and_seed_bounds_do_not_allow_unbounded_programs(self):
        data = self.evaluate("""const g=api.create(config.settings);g.advanceSteps(12,{right:true});g.pressJump();g.clearInput();g.advanceSteps(12);const released=g.snapshot();g.setPaused(true);const before=g.snapshot();g.advanceFrame(.25,{right:true});const after=g.snapshot();let errors=0;
for(const count of [-1,601,1.5,Infinity])try{g.advanceSteps(count)}catch(e){errors++;}
for(const seed of [-1,2147483648,1.5,Infinity])try{api.generate(seed,10)}catch(e){errors++;}
for(const value of [-1,977,NaN])try{g.teleport(value)}catch(e){errors++;}
console.log(JSON.stringify({released,before,after,errors}));""")
        self.assertFalse(data['released']['right']); self.assertFalse(data['released']['pendingJump'])
        self.assertEqual(data['released']['vx'], 0)
        self.assertEqual(data['before'], data['after'])
        self.assertEqual(data['errors'], 11)
