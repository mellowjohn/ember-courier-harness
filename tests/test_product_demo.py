"""One integrated run, then independent replay and cross-stage tamper checks."""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

from ember_harness import Harness
from examples.product_demo import main, verify_product, ROOT


@contextmanager
def changed(path, data):
    path = Path(path)
    original = path.read_bytes()
    try:
        path.write_bytes(data)
        yield
    finally:
        path.write_bytes(original)


class ProductDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with redirect_stdout(io.StringIO()):
            cls.demo = main(fixture_approvals=True)
        cls.manifest = cls.demo['manifest']
        cls.h = Harness(cls.manifest['store'])

    def test_shared_scope_asset_bug_amendment_round_and_actual_build(self):
        result = verify_product(self.manifest)
        self.assertEqual((result['asset_status'], result['bug_status'], result['round_status'], result['attempts']),
                         ('accepted', 'closed', 'complete', 1))
        history = self.h.history(self.manifest['fix_id'])
        self.assertEqual([v['status'] for v in history], ['superseded', 'approved'])
        self.assertTrue(self.demo['report'].is_file())

    def test_manifest_cannot_substitute_another_asset_or_scope(self):
        for change in ('asset', 'scope'):
            manifest = deepcopy(self.manifest)
            if change == 'asset':
                manifest['asset']['sha256'] = '0' * 64
            else:
                manifest['scope_id'] = 'ct-unrelated-scope-0001'
            with self.assertRaisesRegex(ValueError, 'audited binding'):
                verify_product(manifest)

    def test_changed_asset_invalidates_whole_product(self):
        with changed(self.manifest['asset']['path'], b'changed asset'), self.assertRaisesRegex(ValueError, 'accepted asset'):
            verify_product(self.manifest)

    def test_changed_fix_source_invalidates_whole_product(self):
        source = Path(self.manifest['repo']) / 'src/reward.py'
        with changed(source, b'def delivery_reward(coins):\n    return 999\n'), self.assertRaisesRegex(ValueError, 'changed|source differs'):
            verify_product(self.manifest)

    def test_changed_clean_verifier_asset_is_not_hidden_by_main_asset(self):
        from ember_harness.rounds import Rounds
        task = Rounds(self.h).status(1)['tasks'][0]
        path = Path(task['verification_repo']) / self.manifest['asset']['relative']
        with changed(path, b'changed verifier asset'), self.assertRaisesRegex(ValueError, 'changed'):
            verify_product(self.manifest)

    def test_execution_capture_tampering_rejects_product_success(self):
        event = self.h._entries()[self.manifest['executions'][0] - 1]
        path = self.h.root / 'executions' / (event['output_ref'] + '.json')
        with changed(path, b'{}'), self.assertRaisesRegex(ValueError, 'tampered'):
            verify_product(self.manifest)

    def test_cli_refresh_and_failure_exit_without_creating_new_run(self):
        command = [sys.executable, str(ROOT / 'examples/product_demo.py'), '--verify',
                   str(self.demo['report'].parent / 'product.json')]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['passed'])
        with changed(self.manifest['asset']['path'], b'changed CLI asset'):
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(json.loads(result.stderr)['passed'])
