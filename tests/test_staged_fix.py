import contextlib
import io
import json
from pathlib import Path
import unittest

from ember_harness import canonical
from ember_harness.staged_fix import close_bug, execution, run_test
from ember_harness.contract_lock import verify
from examples.staged_fix_demo import main as demo


class StagedFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.demo = demo()

    def arguments(self):
        d = self.demo
        return {"bug_id": "BUG-0001", "severity": "S2", "fix_id": d["fix"]["id"], "verifier_id": d["verifier"]["id"],
                "source_path": d["source"].as_posix(), "pre_seq": d["pre"]["execution_seq"], "post_seq": d["post"]["execution_seq"],
                "review_seq": d["review"]["execution_seq"], "verify_seq": d["qa"]["execution_seq"], "build": d["build"], "pre_build": d["pre_build"], "repo": d["repo"]}

    def test_actual_workflow_closes_once_with_real_local_commit(self):
        self.assertEqual(self.demo["closure"]["status"], "closed")
        self.assertEqual(self.demo["closure"]["review_kind"], "automated_structural_check")
        from ember_harness.attempts import Attempts
        attempt = Attempts(self.demo["harness"]).status("BUG-0001")
        self.assertEqual(attempt["status"], "closed")
        self.assertEqual(attempt["attempts_started"], 1)
        self.assertEqual(attempt["failed_attempts"], 0)
        self.assertTrue(verify(self.demo["harness"].root, repo=self.demo["repo"], base=self.demo["pre_build"])["ok"])
        with self.assertRaisesRegex(ValueError, "already closed"):
            close_bug(self.demo["harness"], **self.arguments())

    def test_TR12_same_author_and_reviewer_rejected(self):
        args = self.arguments()
        args["verifier_id"] = args["fix_id"]
        with self.assertRaisesRegex(ValueError, "must differ"):
            close_bug(self.demo["harness"], **args)

    def test_no_closure_for_a_different_bug_or_severity(self):
        for key, value in (("bug_id", "BUG-9999"), ("severity", "S1")):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "snapshot"):
                close_bug(self.demo["harness"], **(self.arguments() | {key: value}))

    def test_named_build_must_match_fix_commit(self):
        with self.assertRaisesRegex(ValueError, "named verification build"):
            close_bug(self.demo["harness"], **(self.arguments() | {"build": self.demo["pre_build"]}))

    def test_changed_source_invalidates_verification(self):
        source = self.demo["source"]
        original = source.read_bytes()
        try:
            source.write_bytes(b"def delivery_reward(coins):\n    return -1\n")
            with self.assertRaisesRegex(ValueError, "current fixed source"):
                close_bug(self.demo["harness"], **self.arguments())
        finally:
            source.write_bytes(original)

    def test_execution_payload_tamper_rejected(self):
        h = self.demo["harness"]
        payload = h.root / "executions" / (self.demo["qa"]["output_ref"] + ".json")
        original = payload.read_bytes()
        try:
            data = json.loads(original)
            data["returncode"] = 99
            payload.write_bytes(canonical(data))
            with self.assertRaisesRegex(ValueError, "tampered"):
                execution(h, self.demo["qa"]["execution_seq"])
            self.assertFalse(verify(h.root)["ok"])
        finally:
            payload.write_bytes(original)

    def test_registered_regression_is_required(self):
        index = self.demo["harness"].root / "triage/regression/index.json"
        original = index.read_bytes()
        try:
            index.write_bytes(b"[]")
            with self.assertRaisesRegex(ValueError, "registered regression"):
                close_bug(self.demo["harness"], **self.arguments())
        finally:
            index.write_bytes(original)

    def test_test_runner_rejects_unlisted_script_without_executing(self):
        d = self.demo
        action = {"agent": d["fix"]["agent"], "contract_id": d["fix"]["id"], "tool": "test.run",
                  "args": {"script": (d["repo"] / "scripts/unlisted.py").as_posix()}, "paths": {"read": [], "write": []}, "spend": 0}
        with self.assertRaisesRegex(ValueError, "denied"):
            run_test(d["harness"], action)
