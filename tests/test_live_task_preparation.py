import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ember_harness import chat_build, gameplay, project_plan
from tools import prepare_live_task

ROOT = Path(__file__).resolve().parents[1]


class LiveTaskPreparationTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / '.harness/test-temp'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'examples').mkdir()
        (self.root / 'examples/product_demo.py').touch()
        self.binary = self.root / 'muse.exe'
        self.binary.write_bytes(b'Preparation-only identity, never executable')
        self.credits = dict(limit_usd=150, available_usd=140, reserved_usd=5,
                            estimated_spent_usd=5, blocked=None)

    def prepare(self):
        with patch.object(prepare_live_task, 'installed_binary', return_value=str(self.binary)), \
             patch.object(prepare_live_task.polish_runtime, 'discover', return_value={'identity': 'fixture'}), \
             patch.object(prepare_live_task.CreditLedger, 'summary', return_value=self.credits), \
             patch('subprocess.Popen', side_effect=AssertionError('Preparation must not dispatch')):
            return prepare_live_task.prepare(self.root)

    def test_preparation_uses_real_pending_scope_without_approval_or_game_writes(self):
        output = self.prepare()
        data = json.loads((output / 'preparation.json').read_text(encoding='utf-8'))
        folder = Path(data['session_folder'])
        saved = project_plan.status(self.root, folder)
        self.assertFalse(saved['active'])
        self.assertIsNone(saved['approved'])
        self.assertEqual(saved['pending']['ref'], data['request_ref'])
        self.assertFalse(chat_build.context(self.root, folder)['files'])
        self.assertEqual(gameplay.load(folder), data['gameplay'])
        self.assertEqual(len(saved['draft_document']['scope']['features']), 1)
        entries = chat_build.harness(folder)._entries()
        self.assertFalse(any(e['kind'] in ('owner_decision', 'approval', 'action') for e in entries))
        self.assertFalse((self.root / '.harness/muse-credits.json').exists())
        self.assertFalse((folder / 'task-runs').exists())

    def test_missing_or_insufficient_credit_stops_before_creating_session(self):
        for balance, blocked in [(9.99, None), (140, 'unresolved usage')]:
            self.credits.update(available_usd=balance, blocked=blocked)
            with self.subTest(balance=balance, blocked=blocked), self.assertRaisesRegex(ValueError, 'ledger'):
                self.prepare()
            self.assertFalse((self.root / '.harness/ui/sessions').exists())

    def test_missing_muse_or_browser_stops_before_creating_session(self):
        with patch.object(prepare_live_task, 'installed_binary', return_value=None):
            with self.assertRaisesRegex(ValueError, 'Install'):
                prepare_live_task.prepare(self.root)
        with patch.object(prepare_live_task, 'installed_binary', return_value=str(self.binary)), \
             patch.object(prepare_live_task.polish_runtime, 'discover', side_effect=ValueError('No browser')):
            with self.assertRaisesRegex(ValueError, 'No browser'):
                prepare_live_task.prepare(self.root)
        self.assertFalse((self.root / '.harness/ui/sessions').exists())


if __name__ == '__main__':
    unittest.main()
