import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ember_harness.muse_chat import CreditLedger, MODEL, run, settle_capture, provider_schema, structured_schema, decode_structured, UNEXPECTED_USAGE, execution_policy
from ember_harness.core import digest


def retry_capture(request_id='historical-request'):
    events = [dict(payload_type='run.model.configured', payload=dict(model_id=MODEL, provider_id='meta')),
              dict(payload_type='run.usage', payload=dict(calls=2, failed_calls=1, completed_calls=1, cancelled_calls=0,
                   models=[dict(model=MODEL, calls=1, input_tokens=19641, output_tokens=3061)])),
              dict(payload_type='run.terminal.completed', payload=dict(terminal='completed', text='Saved reply'))]
    capture = dict(events=events, model=MODEL, exit_code=0, reservation_micro_usd=5_000_000,
                   ledger_request_id=request_id, response='Saved reply')
    capture['capture_sha256'] = digest(capture)
    return capture

ROOT = Path(__file__).resolve().parents[1]


def wire_reply(value, schema):
    """Synthetic provider fixture in the native transport format."""
    from jsonschema import Draft202012Validator
    schema = provider_schema(schema)
    for key in ('anyOf', 'oneOf'):
        if key in schema and 'type' not in schema:
            return wire_reply(value, next(child for child in schema[key]
                if Draft202012Validator(child).is_valid(value)))
    if schema.get('type') == 'object':
        extra = schema.get('additionalProperties')
        if isinstance(extra, dict):
            if (extra.get('type') == 'object' and extra.get('additionalProperties') is False
                    and 'key' not in extra.get('properties', {})
                    and not any(key in extra for key in ('anyOf', 'oneOf', 'allOf'))):
                return [dict(key=k, **wire_reply(v, extra)) for k, v in value.items()]
            return [dict(key=k, value=wire_reply(v, extra)) for k, v in value.items()]
        return {key: wire_reply(value[key], child) if key in value else None
                for key, child in schema.get('properties', {}).items()}
    if schema.get('type') == 'array':
        return [wire_reply(item, schema['items']) for item in value]
    return value


class MuseChatTests(unittest.TestCase):
    def test_gameplay_steps_have_exact_provider_fields(self):
        from jsonschema import Draft202012Validator
        from ember_harness import chat_build, gameplay

        plan = dict(title='Check a drawn wizard', scenarios=[dict(name='Idle', viewport='desktop', steps=[
            dict(action='sprite_state', entity='wizard-hero', value='idle', frames=2),
        ])])
        reply = dict(message='Draft the wizard', build=None, gameplay_checks=plan)
        wire = wire_reply(reply, chat_build.CHAT_SCHEMA)
        schema = Draft202012Validator(structured_schema(chat_build.CHAT_SCHEMA))
        schema.validate(wire)
        self.assertEqual(gameplay.validate(decode_structured(wire, chat_build.CHAT_SCHEMA)['gameplay_checks']), plan)

        step = wire['gameplay_checks']['scenarios'][0]['steps'][0]
        step['selector'] = '#game'
        self.assertFalse(schema.is_valid(wire))
        del step['selector']
        del step['frames']
        self.assertFalse(schema.is_valid(wire))

    def test_sprite_chat_depth_and_native_markers_fit_provider_limit(self):
        from copy import deepcopy
        from jsonschema import Draft202012Validator, ValidationError
        from ember_harness.chat_build import CHAT_SCHEMA
        from ember_harness.muse_chat import structured_depth
        from tools.sprite_scene_check import plan
        reply = dict(message='Plan the sprite animation', build=None,
            sprite_project=dict(intent='plan', expected_revision=0, plan=plan('a' * 64, 'b' * 64)))
        wire = wire_reply(reply, CHAT_SCHEMA)
        schema = structured_schema(CHAT_SCHEMA)
        self.assertLessEqual(structured_depth(schema), 10)
        states = wire['sprite_project']['plan']['entities'][0]['machine']['states']
        self.assertTrue(all('key' in state and 'clip' in state and 'value' not in state for state in states))
        Draft202012Validator(schema).validate(wire)
        decoded = decode_structured(wire, CHAT_SCHEMA)
        Draft202012Validator(CHAT_SCHEMA).validate(decoded)
        self.assertEqual(decoded['sprite_project'], reply['sprite_project'])
        duplicate = deepcopy(wire)
        duplicate['sprite_project']['plan']['entities'][0]['machine']['states'].append(states[0])
        with self.assertRaisesRegex(ValueError, 'duplicate map key'):
            decode_structured(duplicate, CHAT_SCHEMA)
        invalid = deepcopy(wire)
        invalid['sprite_project']['plan']['entities'][0]['machine']['states'][0]['clip'] = 'INVALID CLIP'
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(invalid)

    def test_oversized_schema_stops_before_reservation_and_reserved_keys_round_trip(self):
        from unittest.mock import Mock
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            root = Path(directory); session = root / 'session'; session.mkdir()
            binary = root / 'synthetic.exe'; binary.touch()
            nested = dict(type='string')
            for _ in range(11):
                nested = dict(type='object', additionalProperties=False, required=['child'], properties=dict(child=nested))
            with patch('ember_harness.muse_chat.subprocess.Popen') as provider:
                with self.assertRaisesRegex(ValueError, '11 nesting levels.*limit is 10'):
                    run(root, session, 'No dispatch', 'too-deep', binary=binary, output_schema=nested)
                provider.assert_not_called()
            self.assertEqual(CreditLedger(root).read()['requests'], {})
        # A map value's own key field must never overwrite the map's row key.
        schema = dict(type='object', additionalProperties=dict(type='object', additionalProperties=False,
            required=['key'], properties=dict(key=dict(type='string'))))
        value = {'outer': {'key': 'inner'}}
        wire = wire_reply(value, schema)
        self.assertEqual(wire, [dict(key='outer', value=dict(key='inner'))])
        self.assertEqual(decode_structured(wire, schema), value)

    def test_chat_selects_discussion_build_and_large_source_allowances(self):
        import test_chat_build as builds
        fixture = builds.ChatBuildTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        response = dict(response=json.dumps(dict(message='Synthetic reply', build=None)))
        with patch('ember_harness.session_chat.run_muse', return_value=response) as provider:
            fixture.app.chat('Let us discuss controls.', 'discuss-controls-001')
            self.assertEqual(provider.call_args.kwargs['execution']['profile'], 'conversation')
            fixture.app.chat('Build an original platform game.', 'build-platformer-001')
            self.assertEqual(provider.call_args.kwargs['execution']['profile'], 'build')
        large = {**builds.PROJECT, 'app.js': builds.PROJECT['app.js'] + '\n/*' + 'x' * 50000 + '*/'}
        ref = fixture.propose_project(large, 'large-source-game-001')
        fixture.app.respond(ref, 'approve', 'SYNTHETIC TEST: large editable source')
        with patch('ember_harness.session_chat.run_muse', return_value=response) as provider:
            fixture.app.chat('Adjust the controls.', 'revise-platformer-001')
            selected = provider.call_args.kwargs['execution']
            self.assertEqual(selected['profile'], 'deep')
            self.assertEqual(selected['timeout_seconds'], 1800)

    def test_long_build_survives_old_deadline_reports_quiet_progress_and_pins_policy(self):
        import subprocess
        from unittest.mock import Mock
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            root = Path(directory); session = root / 'session'; session.mkdir()
            binary = root / 'synthetic.exe'; binary.write_bytes(b'Never executed')
            clock, reports = [0], []
            execution = execution_policy('build')
            def start(args, **kwargs):
                self.assertEqual(args[args.index('--reasoning-effort') + 1], 'high')
                self.assertEqual(args[args.index('--max-model-steps') + 1], '1')
                def wait(timeout):
                    clock[0] += 90
                    if clock[0] < 360:
                        raise subprocess.TimeoutExpired(args, timeout)
                    event = dict(payload_type='run.terminal.completed', payload=dict(terminal='completed', text='Built'))
                    kwargs['stdout'].write(json.dumps(event).encode()); kwargs['stdout'].flush()
                    return 0
                return Mock(wait=wait)
            with patch('ember_harness.muse_chat.time.monotonic', side_effect=lambda: clock[0]), \
                    patch('ember_harness.muse_chat.subprocess.Popen', side_effect=start) as provider:
                capture = run(root, session, 'Build the game', 'long-build', binary=binary, execution=execution,
                              progress=lambda phase, **values: reports.append(values))
                self.assertEqual(capture['elapsed_seconds'], 360)
                self.assertEqual(capture['execution'], execution)
                self.assertEqual([row['elapsed_seconds'] for row in reports], [90, 180, 270, 360])
                self.assertEqual(run(root, session, 'Build the game', 'long-build', binary=binary, execution=execution), capture)
                with self.assertRaisesRegex(ValueError, 'context changed'):
                    run(root, session, 'Build the game', 'long-build', binary=binary,
                        execution=execution_policy('build', repair=True))
                self.assertEqual(provider.call_count, 1)
            self.assertEqual(CreditLedger(root).summary()['reserved_usd'], 5)

    def test_execution_limit_stops_incomplete_work_and_preserves_credit_hold(self):
        import subprocess
        from unittest.mock import Mock
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            root = Path(directory); session = root / 'session'; session.mkdir()
            binary = root / 'synthetic.exe'; binary.write_bytes(b'Never executed')
            clock = [0]
            def wait(timeout):
                if timeout == 10:
                    return 0
                clock[0] = 1800
                raise subprocess.TimeoutExpired('synthetic', timeout)
            process = Mock(wait=wait)
            with patch('ember_harness.muse_chat.time.monotonic', side_effect=lambda: clock[0]), \
                    patch('ember_harness.muse_chat.subprocess.Popen', return_value=process) as provider:
                with self.assertRaisesRegex(ValueError, '30-minute.*incomplete'):
                    run(root, session, 'Repair', 'bounded-deep', binary=binary,
                        execution=execution_policy('build', repair=True))
                process.kill.assert_called_once(); self.assertEqual(provider.call_count, 1)
            self.assertEqual(CreditLedger(root).summary()['reserved_usd'], 5)
            with patch('ember_harness.muse_chat.subprocess.Popen') as provider:
                with self.assertRaisesRegex(ValueError, 'limits'):
                    run(root, session, 'Repair', 'invalid-profile', binary=binary,
                        execution={**execution_policy('build'), 'timeout_seconds': 999999})
                provider.assert_not_called()
            self.assertEqual(CreditLedger(root).summary()['reserved_usd'], 5)

    def test_lowered_credit_ceiling_matches_display_and_denies_dispatch(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            root = Path(directory)
            ledger = CreditLedger(root)
            ledger.path.write_text(json.dumps(dict(version=1, limit_micro_usd=6_000_000, requests={})))
            ledger.reserve('held')
            self.assertEqual(ledger.summary()['limit_usd'], 6)
            self.assertEqual(ledger.summary()['available_usd'], 1)
            with self.assertRaisesRegex(ValueError, 'cannot cover'):
                ledger.reserve('over-limit')
            ledger.path.write_text(json.dumps(dict(version=1, limit_micro_usd=0, requests={})))
            self.assertEqual(ledger.summary()['limit_usd'], 0)
            self.assertEqual(ledger.summary()['available_usd'], 0)
            binary = root / 'never-executed.exe'
            binary.touch()
            session = root / 'session'
            session.mkdir()
            with patch('ember_harness.muse_chat.subprocess.Popen') as provider:
                with self.assertRaisesRegex(ValueError, 'cannot cover'):
                    run(root, session, 'Never dispatch', 'zero-budget', binary=binary)
                provider.assert_not_called()
            self.assertEqual(ledger.read()['requests'], {})

    def test_cancel_check_stops_a_quiet_provider_and_retains_the_reservation(self):
        from unittest.mock import Mock
        scratch=ROOT/'.harness/test-temp';scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            root=Path(directory);session=root/'session';session.mkdir()
            binary=root/'synthetic.exe';binary.write_bytes(b'Never executed')
            process=Mock()
            with patch('ember_harness.muse_chat.subprocess.Popen',return_value=process):
                with self.assertRaisesRegex(ValueError,'SYNTHETIC cancellation'):
                    run(root,session,'Plan','quiet-call',binary=binary,check=Mock(side_effect=ValueError('SYNTHETIC cancellation')))
            process.kill.assert_called_once()
            self.assertEqual(CreditLedger(root).summary()['reserved_usd'],5)

    def test_screenshot_requests_bind_images_prompt_and_run_budget_on_replay(self):
        from PIL import Image
        from unittest.mock import Mock
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            root=Path(directory); session=root/'session'; session.mkdir()
            binary=root/'synthetic.exe'; binary.write_bytes(b'Never executed')
            image=root/'screenshot.png'; Image.new('RGB',(40,30),'green').save(image)
            original=image.read_bytes(); budget=dict(id='e'*64,limit_micro_usd=5_000_000)
            events=[dict(payload_type='run.terminal.completed',payload=dict(terminal='completed',text='Screenshot critique'))]
            def start(args,**kwargs):
                attached=Path(args[args.index('--image')+1])
                self.assertEqual(attached.read_bytes(),original)
                self.assertNotEqual(attached,image)
                kwargs['stdout'].write(json.dumps(events[0]).encode());kwargs['stdout'].flush()
                return Mock(wait=Mock(return_value=0))
            with patch('ember_harness.muse_chat.subprocess.Popen',side_effect=start) as process:
                first=run(root,session,'Inspect screenshot','image-critique',binary=binary,images=[image],budget=budget)
                self.assertEqual(run(root,session,'Inspect screenshot','image-critique',binary=binary,images=[image],budget=budget),first)
                self.assertEqual(process.call_count,1)
                for changes in (dict(prompt='Different prompt'),dict(budget={**budget,'limit_micro_usd':10_000_000})):
                    options=dict(prompt='Inspect screenshot',budget=budget)|changes
                    with self.assertRaisesRegex(ValueError,'context changed'):
                        run(root,session,options['prompt'],'image-critique',binary=binary,images=[image],budget=options['budget'])
                Image.new('RGB',(40,30),'red').save(image)
                with self.assertRaisesRegex(ValueError,'context changed'):
                    run(root,session,'Inspect screenshot','image-critique',binary=binary,images=[image],budget=budget)
                self.assertEqual(process.call_count,1)
            self.assertEqual(CreditLedger(root).budget_summary('e'*64)['reserved_usd'],5)

    def test_shared_credit_reservations_survive_restart_and_cannot_exceed_150(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            ledger = CreditLedger(folder)
            for i in range(30):
                ledger.reserve(str(i))
            with self.assertRaisesRegex(ValueError, 'budget'):
                CreditLedger(folder).reserve('31')
            self.assertEqual(CreditLedger(folder).summary()['reserved_usd'], 150)
            ledger.settle('0', 100, 100)
            ledger.settle('1', 100, 100)
            self.assertEqual(ledger.summary()['estimated_spent_usd'], .0011)
            CreditLedger(folder).reserve('31')
            self.assertLessEqual(ledger.summary()['reserved_usd'] + ledger.summary()['estimated_spent_usd'], 150)
            with self.assertRaises(ValueError):
                ledger.reserve('31')

    def test_muse_transport_is_single_step_metered_and_does_not_repeat_saved_reply(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            session = root / 'session'
            session.mkdir()
            binary = root / 'muse-test.exe'
            binary.write_bytes(b'test binary, never executed')
            events = [dict(payload_type='run.terminal.completed', payload=dict(terminal='completed', text='Muse reply')),
                      dict(payload_type='run.usage', payload=dict(calls=1, completed_calls=1, failed_calls=0,
                           models=[dict(model=MODEL, calls=1, input_tokens=100, output_tokens=100)]))]

            def start(args, **kwargs):
                self.assertEqual(args[args.index('--provider') + 1], 'meta')
                self.assertEqual(args[args.index('--max-model-steps') + 1], '1')
                self.assertEqual(args[args.index('--config') + 1], 'provider_retry.max_retries=0')
                for flag in ('--disable-write', '--disable-shell', '--disable-web-tools', '--no-foreign-personal-context'):
                    self.assertIn(flag, args)
                self.assertNotIn('--yolo', args)
                kwargs['stdout'].write(('\n'.join(json.dumps(e) for e in events)).encode())
                kwargs['stdout'].flush()
                from unittest.mock import Mock
                return Mock(wait=Mock(return_value=0))

            with patch('ember_harness.muse_chat.subprocess.Popen', side_effect=start) as process:
                first = run(root, session, 'Hello', 'turn-one', binary=binary)
                second = run(root, session, 'Hello', 'turn-one', binary=binary)
                self.assertEqual(first['response'], 'Muse reply')
                self.assertEqual(first, second)
                self.assertEqual(process.call_count, 1)
            self.assertEqual(CreditLedger(root).summary()['estimated_spent_usd'], .00055)
            self.assertEqual(CreditLedger(root).summary()['reserved_usd'], 0)
            capture = session / 'muse-captures/turn-one.json'
            data = json.loads(capture.read_bytes())
            data['response'] = 'changed'
            capture.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'changed'):
                run(root, session, 'Hello', 'turn-one', binary=binary)

    def test_stream_reports_observed_phases_without_exposing_provider_text(self):
        import subprocess
        from unittest.mock import Mock
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            session = root / 'session'
            session.mkdir()
            binary = root / 'muse-test.exe'
            binary.write_bytes(b'synthetic binary')
            reports = []
            def start(args, **kwargs):
                events = iter([
                    dict(payload_type='run.lifecycle.started', payload=dict(prompt='PRIVATE PROMPT')),
                    dict(payload_type='run.output.delta', payload=dict(text='PRIVATE RESPONSE')),
                    dict(payload_type='run.terminal.completed', payload=dict(terminal='completed', text='Reply')),
                ])
                def wait(timeout):
                    event = next(events)
                    kwargs['stdout'].write((json.dumps(event) + '\n').encode())
                    kwargs['stdout'].flush()
                    if event['payload_type'] != 'run.terminal.completed':
                        raise subprocess.TimeoutExpired(args, timeout)
                    return 0
                return Mock(wait=wait)
            with patch('ember_harness.muse_chat.subprocess.Popen', side_effect=start):
                capture = run(root, session, 'Hello', 'progress-stream', binary=binary,
                              progress=lambda phase, **values: reports.append(dict(phase=phase, **values)))
            self.assertEqual([r['phase'] for r in reports], ['muse_working', 'receiving', 'provider_finished'])
            self.assertEqual(reports[1]['response_chars'], len('PRIVATE RESPONSE'))
            self.assertNotIn('PRIVATE', json.dumps(reports))
            self.assertEqual(capture['response'], 'Reply')
            self.assertEqual(CreditLedger(root).summary()['reserved_usd'], 5)

    def test_progress_failure_stops_cli_and_keeps_credit_reservation(self):
        import subprocess
        from unittest.mock import Mock
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            session = root / 'session'
            session.mkdir()
            binary = root / 'muse-test.exe'
            binary.write_bytes(b'synthetic binary')
            process = Mock(wait=Mock(side_effect=[subprocess.TimeoutExpired('muse', .25), 0]))
            def start(args, **kwargs):
                kwargs['stdout'].write(b'{"payload_type":"run.lifecycle.started"}\n')
                kwargs['stdout'].flush()
                return process
            with patch('ember_harness.muse_chat.subprocess.Popen', side_effect=start):
                with self.assertRaisesRegex(OSError, 'SYNTHETIC disk failure'):
                    run(root, session, 'Hello', 'failed-progress', binary=binary,
                        progress=Mock(side_effect=OSError('SYNTHETIC disk failure')))
            process.kill.assert_called_once()
            self.assertEqual(CreditLedger(root).summary()['reserved_usd'], 5)

    def test_inspected_retry_keeps_full_hold_and_replays_without_dispatch(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            ledger = CreditLedger(root)
            ledger.reserve('historical-request')
            capture = retry_capture()
            # A legacy blocked ledger can still be repaired without erasing its evidence.
            ledger.freeze(UNEXPECTED_USAGE)
            inspection = ledger.retain_inspected_retry(capture)
            self.assertEqual(inspection['total_bound_micro_usd'], 4_494_009)
            self.assertEqual(ledger.summary()['reserved_usd'], 5)
            self.assertIsNone(ledger.summary()['blocked'])
            session = root / 'session'
            (session / 'muse-captures').mkdir(parents=True)
            (session / 'muse-captures/turn.json').write_text(json.dumps(capture), encoding='utf-8')
            binary = root / 'muse-test.exe'
            binary.write_bytes(b'never executed')
            with patch('ember_harness.muse_chat.subprocess.Popen') as process:
                self.assertEqual(run(root, session, 'Hello', 'turn', binary=binary)['response'], 'Saved reply')
                process.assert_not_called()
            self.assertEqual(ledger.summary()['reserved_usd'], 5)
            self.assertEqual(ledger.summary()['estimated_spent_usd'], 0)

    def test_retry_inspection_rejects_unbounded_usage_and_other_open_reservations(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            ledger = CreditLedger(folder)
            ledger.reserve('historical-request')
            ledger.freeze(UNEXPECTED_USAGE)
            for change in ('hash', 'model', 'calls', 'tokens'):
                capture = retry_capture()
                if change == 'hash':
                    capture['response'] = 'changed'
                else:
                    if change == 'model':
                        capture['events'][0]['payload']['model_id'] = 'other-model'
                    elif change == 'calls':
                        capture['events'][1]['payload']['failed_calls'] = 2
                    else:
                        capture['events'][1]['payload']['models'][0]['output_tokens'] = 500000
                    capture['capture_sha256'] = digest({k: v for k, v in capture.items() if k != 'capture_sha256'})
                with self.subTest(change=change), self.assertRaises(ValueError):
                    ledger.retain_inspected_retry(capture)
            self.assertEqual(ledger.summary()['reserved_usd'], 5)
            self.assertEqual(ledger.read()['blocked'], UNEXPECTED_USAGE)
            # A second unresolved request must not be silently cleared by this inspection.
            data = ledger.read()
            data['requests']['other-request'] = dict(status='reserved', reserved_micro_usd=5_000_000)
            ledger.path.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Other unresolved'):
                ledger.retain_inspected_retry(retry_capture())

    def test_changed_inspected_capture_refreezes_without_releasing_hold(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            ledger = CreditLedger(folder)
            ledger.reserve('historical-request')
            ledger.freeze(UNEXPECTED_USAGE)
            capture = retry_capture()
            ledger.retain_inspected_retry(capture)
            capture['events'][1]['payload']['models'][0]['output_tokens'] += 1
            capture['capture_sha256'] = digest({k: v for k, v in capture.items() if k != 'capture_sha256'})
            with self.assertRaisesRegex(ValueError, 'changed'):
                settle_capture(ledger, 'unused', capture)
            self.assertEqual(ledger.summary()['reserved_usd'], 5)
            self.assertEqual(ledger.read()['blocked'], 'Inspected Muse capture changed')

    def test_failed_provider_request_retains_hold_without_credit_inspection(self):
        from unittest.mock import Mock
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            root = Path(directory); session = root / 'session'; session.mkdir()
            binary = root / 'synthetic.exe'; binary.write_bytes(b'Never executed')
            events = [dict(payload_type='run.usage', payload=dict(calls=1, failed_calls=1, completed_calls=0, models=[])),
                      dict(payload_type='run.terminal.failed', payload=dict(terminal='failed', reason='SYNTHETIC schema rejection'))]
            def start(args, **kwargs):
                kwargs['stdout'].write(('\n'.join(json.dumps(e) for e in events)).encode()); kwargs['stdout'].flush()
                return Mock(wait=Mock(return_value=1))
            with patch('ember_harness.muse_chat.subprocess.Popen', side_effect=start) as process:
                for _ in range(2):
                    with self.assertRaisesRegex(ValueError, 'SYNTHETIC schema rejection'):
                        run(root, session, 'Hello', 'failed-call', binary=binary)
                self.assertEqual(process.call_count, 1)
            ledger = CreditLedger(root)
            self.assertIsNone(ledger.summary()['blocked'])
            self.assertEqual(ledger.summary()['reserved_usd'], 5)
            ledger.reserve('next-message')
            self.assertEqual(ledger.summary()['reserved_usd'], 10)

    def test_uncertain_usage_does_not_freeze_other_sessions_or_release_funds(self):
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            ledger = CreditLedger(directory)
            ledger.reserve('historical-request')
            settle_capture(ledger, 'unused', retry_capture())
            self.assertIsNone(ledger.summary()['blocked'])
            self.assertEqual(ledger.summary()['reserved_usd'], 5)
            ledger.reserve('another-session')
            ledger.freeze(UNEXPECTED_USAGE)
            self.assertIsNone(ledger.summary()['blocked'])
            CreditLedger(directory).reserve('after-restart')
            self.assertEqual(ledger.summary()['reserved_usd'], 15)
            self.assertNotIn('blocked', ledger.read())
            self.assertEqual(ledger.read()['retired_usage_inspections'], [UNEXPECTED_USAGE])
            self.assertEqual(ledger.summary()['estimated_spent_usd'], 0)

    def test_muse_receives_compatible_schema_while_local_checks_remain_strict(self):
        from unittest.mock import Mock
        from jsonschema import Draft202012Validator, ValidationError
        from ember_harness.chat_build import CHAT_SCHEMA
        compatible = provider_schema(CHAT_SCHEMA)
        self.assertNotIn('uniqueItems', json.dumps(compatible))
        self.assertNotIn('propertyNames', json.dumps(compatible))
        self.assertNotIn('"$ref"', json.dumps(compatible))
        self.assertIn('uniqueItems', json.dumps(CHAT_SCHEMA))
        features = CHAT_SCHEMA['properties']['plan']['anyOf'][1]['properties']['scope']['properties']['features']
        with self.assertRaises(ValidationError):
            Draft202012Validator(features).validate(['Duplicate task', 'Duplicate task'])
        # Schema property names are data and must not be removed as keywords.
        self.assertEqual(provider_schema({'properties': {'uniqueItems': {'type': 'string'}}}),
                         {'properties': {'uniqueItems': {'type': 'string'}}})
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            root = Path(directory); session = root / 'session'; session.mkdir()
            binary = root / 'synthetic.exe'; binary.write_bytes(b'Never executed')
            def start(args, **kwargs):
                actual = json.loads(Path(args[args.index('--output-schema') + 1]).read_bytes())
                self.assertEqual(actual, structured_schema(CHAT_SCHEMA))
                prompt = Path(args[args.index('--prompt-file') + 1]).read_text(encoding='utf-8')
                supplied = json.loads(prompt.split('\n', 1)[1].split('\nRequest:\n', 1)[0])
                self.assertEqual(supplied, actual)
                response = wire_reply(dict(message='Synthetic reply', build=None), CHAT_SCHEMA)
                event = dict(payload_type='run.terminal.completed', payload=dict(terminal='completed', text=json.dumps(response)))
                kwargs['stdout'].write(json.dumps(event).encode()); kwargs['stdout'].flush()
                return Mock(wait=Mock(return_value=0))
            with patch('ember_harness.muse_chat.subprocess.Popen', side_effect=start):
                capture = run(root, session, 'Plan', 'schema-check', binary=binary, output_schema=CHAT_SCHEMA)
                self.assertEqual(json.loads(capture['response']), dict(message='Synthetic reply', build=None,
                    brief_updates=None, plan=None, asset=None, image_request=None, image_requests=None, sprite_project=None,gameplay_checks=None))

    def test_native_plan_and_optional_updates_round_trip_without_encoded_json(self):
        from jsonschema import Draft202012Validator
        from ember_harness.chat_build import CHAT_SCHEMA
        from ember_harness.project_plan import starter
        reply = dict(message='Review the amended plan.', build=None, plan=starter(ROOT),
                     brief_updates=dict(controls='Space to shoot'))
        wire = wire_reply(reply, CHAT_SCHEMA)
        self.assertIsInstance(wire['plan'], dict)
        self.assertIsInstance(wire['plan']['scope']['asset_budget'], list)
        Draft202012Validator(structured_schema(CHAT_SCHEMA)).validate(wire)
        decoded = decode_structured(wire, CHAT_SCHEMA)
        Draft202012Validator(CHAT_SCHEMA).validate(decoded)
        self.assertEqual(decoded['plan'], reply['plan'])
        self.assertEqual(decoded['brief_updates'], reply['brief_updates'])
        wire['plan']['scope']['asset_budget'].append(wire['plan']['scope']['asset_budget'][0])
        with self.assertRaisesRegex(ValueError, 'duplicate map key'):
            decode_structured(wire, CHAT_SCHEMA)

    def test_native_build_keeps_edits_and_drops_unused_optional_files(self):
        from jsonschema import Draft202012Validator
        from ember_harness.chat_build import CHAT_SCHEMA
        reply = dict(message='Review the change.', build=dict(title='Movement', summary='Animate movement',
            edits=[dict(path='app.js', before='const speed=1;', after='const speed=2;')]))
        wire = wire_reply(reply, CHAT_SCHEMA)
        self.assertIsNone(wire['build']['files'])
        Draft202012Validator(structured_schema(CHAT_SCHEMA)).validate(wire)
        decoded = decode_structured(wire, CHAT_SCHEMA)
        self.assertEqual(decoded['build'], reply['build'])
        Draft202012Validator(CHAT_SCHEMA).validate(decoded)

    def test_planning_references_validate_locally_and_in_the_dispatched_schema(self):
        from copy import deepcopy
        from jsonschema import Draft202012Validator, ValidationError
        from ember_harness.chat_build import CHAT_SCHEMA
        from ember_harness.project_plan import starter, validate_document
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            plan = starter(directory)
            plan['art_direction']['references'] = [dict(path='original-art.png', sha256='a' * 64, note='Original direction')]
            reply = dict(message='Review this plan.', build=None, plan=plan)
            Draft202012Validator(CHAT_SCHEMA).validate(reply)
            self.assertEqual(validate_document(plan), plan)
            compatible = provider_schema(CHAT_SCHEMA)
            Draft202012Validator(compatible).validate(reply)
            self.assertNotIn('"$ref"', json.dumps(compatible))
            self.assertNotIn('"$defs"', json.dumps(compatible))
            invalid = deepcopy(reply)
            invalid['plan']['art_direction']['references'][0]['sha256'] = 'invalid hash'
            for schema in (CHAT_SCHEMA, compatible):
                with self.assertRaises(ValidationError):
                    Draft202012Validator(schema).validate(invalid)
            with self.assertRaises(ValidationError):
                validate_document(invalid['plan'])

    def test_broken_or_recursive_schema_refs_stop_before_dispatch_or_credit_reservation(self):
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            root = Path(directory); session = root / 'session'; session.mkdir()
            binary = root / 'synthetic.exe'; binary.write_bytes(b'Never executed')
            schemas = [dict(properties=dict(hash={'$ref': '#/$defs/missing'})),
                       {'$ref': 'https://example.org/schema'},
                       {'$defs': {'loop': {'$ref': '#/$defs/loop'}}, '$ref': '#/$defs/loop'}]
            with patch('ember_harness.muse_chat.subprocess.Popen') as provider:
                for index, schema in enumerate(schemas):
                    with self.assertRaisesRegex(ValueError, 'schema'):
                        run(root, session, 'Never dispatch', 'invalid-schema-' + str(index),
                            binary=binary, output_schema=schema)
                provider.assert_not_called()
            self.assertEqual(CreditLedger(root).read()['requests'], {})
        schema = {'$defs': {'escaped/key~': {'type': 'string', 'minLength': 2}},
                  'properties': {'name': {'$ref': '#/$defs/escaped~1key~0'}},
                  'enum': [{'$ref': 'literal data'}]}
        self.assertEqual(provider_schema(schema), {'properties': {'name': {'type': 'string', 'minLength': 2}},
                                                 'enum': [{'$ref': 'literal data'}]})

    def test_invalid_structured_reply_is_saved_and_rejected_without_redispatch(self):
        from unittest.mock import Mock
        from ember_harness.chat_build import CHAT_SCHEMA
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            root = Path(directory); session = root / 'session'; session.mkdir()
            binary = root / 'synthetic.exe'; binary.write_bytes(b'Never executed')
            invalid = dict(message='Invalid controls', build=None, brief_updates=dict(controls=42))
            events = [dict(payload_type='run.terminal.completed', payload=dict(terminal='completed',
                           text=json.dumps({**wire_reply(dict(message='Valid fixture', build=None), CHAT_SCHEMA),
                                           **invalid}))),
                      dict(payload_type='run.usage', payload=dict(calls=1, completed_calls=1, failed_calls=0,
                           models=[dict(model=MODEL, calls=1, input_tokens=10, output_tokens=10)]))]
            def start(args, **kwargs):
                kwargs['stdout'].write(('\n'.join(json.dumps(e) for e in events)).encode()); kwargs['stdout'].flush()
                return Mock(wait=Mock(return_value=0))
            with patch('ember_harness.muse_chat.subprocess.Popen', side_effect=start) as provider:
                for _ in range(2):
                    with self.assertRaisesRegex(ValueError, 'invalid structured reply') as failure:
                        run(root, session, 'Plan', 'invalid-payload', binary=binary, output_schema=CHAT_SCHEMA)
                    self.assertIn('Reported credit usage has been recorded', str(failure.exception))
                    self.assertNotIn('reservation remains counted', str(failure.exception))
                self.assertEqual(provider.call_count, 1)
            saved = json.loads((session / 'muse-captures/invalid-payload.json').read_bytes())
            self.assertIsNone(saved['response'])
            self.assertEqual(saved['events'], events)
            ledger = CreditLedger(root)
            self.assertIsNone(ledger.summary()['blocked'])
            self.assertEqual(ledger.summary()['reserved_usd'], 0)
            self.assertEqual(ledger.summary()['estimated_spent_usd'], .000055)

    def test_malformed_json_is_never_salvaged_or_redispatched_on_replay(self):
        from unittest.mock import Mock
        from ember_harness.chat_build import CHAT_SCHEMA
        scratch = ROOT / '.harness/test-temp'; scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            root = Path(directory); session = root / 'session'; session.mkdir()
            binary = root / 'synthetic.exe'; binary.write_bytes(b'Never executed')
            valid = json.dumps(wire_reply(dict(message='Review', build=None), CHAT_SCHEMA))
            bad = valid + '}'  # The original extra-closing-brace failure.
            event = dict(payload_type='run.terminal.completed', payload=dict(terminal='completed', text=bad))
            def start(args, **kwargs):
                kwargs['stdout'].write(json.dumps(event).encode()); kwargs['stdout'].flush()
                return Mock(wait=Mock(return_value=0))
            with patch('ember_harness.muse_chat.subprocess.Popen', side_effect=start) as process:
                for _ in range(2):
                    with self.assertRaisesRegex(ValueError, 'Extra data'):
                        run(root, session, 'Plan', 'bad-json', binary=binary, output_schema=CHAT_SCHEMA)
                self.assertEqual(process.call_count, 1)
            saved = json.loads((session / 'muse-captures/bad-json.json').read_bytes())
            self.assertIsNone(saved['response'])
            self.assertEqual(saved['events'], [event])
            self.assertEqual(CreditLedger(root).summary()['reserved_usd'], 5)


if __name__ == '__main__':
    unittest.main()
