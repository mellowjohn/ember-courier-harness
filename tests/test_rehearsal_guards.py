"""Synthetic browser rehearsals must never reach a live provider adapter."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ember_harness.muse_chat import CreditLedger, run as real_provider
from tools.browser_check import synthetic_provider_guard


class RehearsalGuardTests(unittest.TestCase):
    def test_offline_suite_disables_host_discovery_for_preimported_aliases(self):
        from tools import offline_tests
        from unittest import TestCase, TestSuite
        class UnstubbedWorkflow(TestCase):
            def runTest(self):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    with patch('ember_harness.muse_chat.subprocess.Popen') as process:
                        with self.assertRaisesRegex(ValueError, 'not installed'):
                            real_provider(root, root, 'SYNTHETIC no dispatch', 'unstubbed-test')
                        process.assert_not_called()
                    self.assertFalse((root / '.harness/muse-credits.json').exists())
        with patch('tools.offline_tests.unittest.defaultTestLoader.discover',
                   return_value=TestSuite([UnstubbedWorkflow()])):
            self.assertEqual(offline_tests.main([]), 0)

    def test_preimported_provider_alias_is_blocked_before_reservation_and_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / 'synthetic-not-executable.exe'
            binary.write_bytes(b'Synthetic identity only')
            before = CreditLedger(root).summary()
            with synthetic_provider_guard(), patch('ember_harness.muse_chat.subprocess.Popen') as process:
                with self.assertRaisesRegex(AssertionError, 'unstubbed live provider'):
                    real_provider(root, root, 'SYNTHETIC must never dispatch', 'synthetic-guard-case', binary=binary)
                process.assert_not_called()
            self.assertEqual(CreditLedger(root).summary(), before)
            self.assertFalse((root / '.harness/muse-credits.json').exists())
