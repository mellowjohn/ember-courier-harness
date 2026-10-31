"""Mock inference tests the boundary; the explicit live product run proves actual inference."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from ember_harness import Harness, content_hash, draft, canonical
from ember_harness.contract_lock import verify
from ember_harness.local_agent import LocalAgent, local_weights
from ember_harness.staged_fix import run_test


class LocalAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'data').mkdir()
        self.source = self.root / 'data/reward.py'
        self.source.write_bytes(b'def reward(coins):\n    return coins - 1\n')
        self.fixed = 'def reward(coins):\n    return coins\n'
        self.script = self.root / 'data/regression.py'
        self.script.write_bytes(b'raise AssertionError("captured reward failure fixture")\n')
        self.agent = LocalAgent(sys.executable, 'fixture-local:7b')
        self.h = Harness(self.root / 'state')
        scope = draft('ct-agent-scope-0001', 'planner', 'Test the local agent boundary', role='scope')
        pattern = self.source.parent.as_posix() + '/*.py'
        scope['allowed_paths'] = dict(read=[pattern], write=[pattern])
        scope['inputs'] = [dict(name='regression', path=self.script.as_posix(), sha256=sha256(self.script.read_bytes()).hexdigest())]
        scope['allowed_actions'] = [self.agent.capability(self.source.as_posix()),
            dict(action_id='edit', tool='fs.write', **{'class': 'write'}, args_constraints=dict(
                path={'equals': self.source.as_posix()}, content={'equals': self.fixed}), allow_no_evidence=True),
            dict(action_id='test', tool='test.run', **{'class': 'compute'},
                 args_constraints=dict(script={'equals': self.script.as_posix()}), allow_no_evidence=True)]
        scope = self.approve(scope)
        self.c = draft('ct-agent-worker-0001', 'worker', 'Propose the local fix')
        for key in ('allowed_actions', 'allowed_paths', 'inputs', 'limits'):
            self.c[key] = deepcopy(scope[key])
        self.c = self.approve(self.c, scope['id'])
        self.assertTrue(self.h.verify_inputs(self.c['id']))
        self.pre = run_test(self.h, dict(agent=self.c['agent'], contract_id=self.c['id'], tool='test.run',
            args=dict(script=self.script.as_posix()), paths=dict(read=[self.source.as_posix(), self.script.as_posix()], write=[]), spend=0))
        self.transport = dict(provider='ollama_local', cloud_disabled=True, spend_usd=0,
            model=dict(name=self.agent.model, digest='a' * 64, size=10, details=dict(format='gguf')),
            response=dict(model=self.agent.model, done=True, response=json.dumps(dict(tool='fs.write',
                          args=dict(path=self.source.as_posix(), content=self.fixed)))))

    def approve(self, c, parent=None):
        self.h.save_draft(c)
        return self.h.approve(c['id'], 1, approver='johnathan', quote='Simulated unit fixture approval',
                              expected_hash=content_hash(c), parent_id=parent)['contract']

    def propose(self, transport=None):
        with patch.object(self.agent, '_generate', return_value=transport or self.transport):
            return self.agent.propose(self.h, self.c, self.source, self.pre)

    def test_proposal_is_not_a_write_and_matches_audited_response(self):
        before = self.source.read_bytes()
        action = self.propose()
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(self.h.check(action)['decision'], 'allow')
        self.assertTrue(verify(self.h.root)['ok'])

    def test_wrong_path_model_proposal_denies_without_writing(self):
        t = deepcopy(self.transport)
        outside = self.root / 'outside.py'
        t['response']['response'] = json.dumps(dict(tool='fs.write', args=dict(path=str(outside), content=self.fixed)))
        self.assertEqual(self.h.check(self.propose(t))['decision'], 'deny')
        self.assertFalse(outside.exists())

    def test_only_newline_formatting_is_normalized_before_exact_gate(self):
        t = deepcopy(self.transport)
        t['response']['response'] = json.dumps(dict(tool='fs.write', args=dict(
            path=self.source.as_posix(), content=self.fixed.replace('\n', '\r\n') + '\r\n')))
        action = self.propose(t)
        self.assertEqual(action['args']['content'], self.fixed)
        self.assertEqual(self.h.check(action)['decision'], 'allow')
        self.assertTrue(verify(self.h.root)['ok'])
        t['response']['response'] = json.dumps(dict(tool='fs.write', args=dict(
            path=self.source.as_posix(), content=self.fixed.replace('return coins', 'return coins + 1'))))
        self.assertEqual(self.h.check(self.propose(t))['decision'], 'deny')

    def test_forbidden_tools_and_self_approval_fields_are_rejected(self):
        for proposal in (dict(tool='deploy.site', args=dict(path=str(self.source), content=self.fixed)),
                         dict(tool='fs.write', args=dict(path=str(self.source), content=self.fixed), approved_by='johnathan')):
            t = deepcopy(self.transport)
            t['response']['response'] = json.dumps(proposal)
            with self.assertRaisesRegex(ValueError, 'local agent failed'):
                self.propose(t)

    def test_no_inference_for_outside_or_unapproved_contract(self):
        with patch.object(self.agent, '_generate') as transport:
            with self.assertRaisesRegex(ValueError, 'inference denied'):
                self.agent.propose(self.h, self.c, self.root / 'outside.py', self.pre)
            transport.assert_not_called()

    def test_source_change_during_inference_never_returns_edit(self):
        def changed(*args):
            self.source.write_bytes(b'changed during inference')
            return self.transport
        with patch.object(self.agent, '_generate', side_effect=changed), self.assertRaisesRegex(ValueError, 'source changed'):
            self.agent.propose(self.h, self.c, self.source, self.pre)

    def test_expired_contract_cannot_start_inference(self):
        self.h.clock = lambda: datetime.now(timezone.utc) + timedelta(days=1)
        with patch.object(self.agent, '_generate') as transport:
            with self.assertRaisesRegex(ValueError, 'inference denied'):
                self.agent.propose(self.h, self.c, self.source, self.pre)
            transport.assert_not_called()

    def test_revoked_during_inference_records_failure_without_edit(self):
        def changed(*args):
            self.h.revoke(self.c['id'], approver='johnathan', reason='Fixture mid-inference revocation')
            return self.transport
        with patch.object(self.agent, '_generate', side_effect=changed), self.assertRaisesRegex(ValueError, 'authority or source changed'):
            self.agent.propose(self.h, self.c, self.source, self.pre)
        event = next(e for e in self.h._entries() if e['kind'] == 'agent_proposal')
        self.assertEqual(event['status'], 'failed')

    def test_revocation_after_proposal_blocks_execution(self):
        action = self.propose()
        self.h.revoke(self.c['id'], approver='johnathan', reason='Unit fixture revocation')
        self.assertEqual(self.h.check(action)['decision'], 'deny')

    def test_cloud_metadata_missing_weights_and_remote_names_reject(self):
        for bad in (dict(remote_host='https://ollama.com'), dict(remote_model='cloud'), dict(size=0), dict(details=dict(format='remote'))):
            with self.assertRaisesRegex(ValueError, 'local GGUF'):
                local_weights([{**self.transport['model'], **bad}], self.agent.model)
        for name in ('qwen:cloud', 'https://remote', 'model\nname'):
            with self.assertRaises(ValueError):
                LocalAgent(sys.executable, name)

    def test_transport_failure_and_audit_failure_do_not_return_action(self):
        with patch.object(self.agent, '_generate', side_effect=TimeoutError('fixture timeout')), self.assertRaisesRegex(ValueError, 'fixture timeout'):
            self.agent.propose(self.h, self.c, self.source, self.pre)
        original = self.h._append
        def broken(kind, **kwargs):
            if kind == 'agent_proposal':
                raise OSError('fixture audit failure')
            return original(kind, **kwargs)
        with patch.object(self.h, '_append', side_effect=broken), self.assertRaises(OSError):
            self.propose()

    def test_capture_tampering_fails_contract_lock(self):
        self.propose()
        event = next(e for e in self.h._entries() if e['kind'] == 'agent_proposal')
        (self.h.root / 'agent-captures' / (event['capture_ref'] + '.json')).write_bytes(canonical({}))
        self.assertFalse(verify(self.h.root)['ok'])
