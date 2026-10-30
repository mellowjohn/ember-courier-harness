import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ember_harness import Harness, canonical
from ember_harness.rounds import Rounds
from ember_harness.reporting import write_round_report
from examples.staged_fix_demo import main as staged_demo


class RoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.demo = staged_demo(with_rounds=True)
        cls.original_entries = cls.demo["harness"]._entries()
        cls.original_state = cls.demo["rounds"].status(1)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        shutil.copytree(self.demo["harness"].root, self.root / "state")
        self.h = Harness(self.root / "state")
        self.rounds = Rounds(self.h)

    def through(self, seq):
        entries = [e for e in self.original_entries if e["seq"] <= seq]
        self.h.audit_path.write_bytes(b"".join(canonical(e) + b"\n" for e in entries))
        heads = {e["entry_hash"] for e in entries}
        for anchor in (self.h.root / "audit/anchors").glob("*.txt"):
            if anchor.read_text().strip() not in heads:
                anchor.unlink()

    def phase(self, name):
        return next(e["seq"] for e in self.original_state["events"] if e["detail"]["checkpoint"] == name)

    def test_complete_round_and_anchor_have_audit_basis(self):
        state = self.rounds.status(1)
        self.assertEqual(state["status"], "complete")
        self.assertEqual(state["status_basis"], self.phase("C3"))
        self.assertEqual(list(state["tasks"][0]["checkpoints"]), ["C1", "C2"])
        self.assertTrue((self.h.root / "audit/anchors/round-1.txt").read_text().strip() in {e["entry_hash"] for e in self.h._entries()})

    def test_TR37_second_round_cannot_start_while_first_is_open(self):
        self.through(self.phase("C0"))
        with self.assertRaisesRegex(ValueError, "still open"):
            self.rounds.start([self.demo["task"]])

    def test_C2_cannot_skip_C1_and_C3_cannot_skip_verification(self):
        self.through(self.phase("C0"))
        with self.assertRaisesRegex(ValueError, "requires C1"):
            self.rounds.verified(1, "BUG-0001", repro_seq=self.demo["pre"]["execution_seq"], verify_seq=self.demo["qa"]["execution_seq"])
        with self.assertRaisesRegex(ValueError, "all tasks require"):
            self.rounds.close(1)

    def test_C3_requires_bug_closure_after_C2(self):
        self.through(self.phase("C2"))
        with self.assertRaisesRegex(ValueError, "closure required"):
            self.rounds.close(1)

    def test_duplicate_checkpoints_and_terminal_round_changes_rejected(self):
        self.through(self.phase("C1"))
        with self.assertRaisesRegex(ValueError, "already recorded"):
            self.rounds.reviewed(1, "BUG-0001", build=self.demo["build"], review_seq=self.demo["review"]["execution_seq"])
        self.through(self.phase("C2"))
        with self.assertRaisesRegex(ValueError, "cannot be repeated"):
            self.rounds.verified(1, "BUG-0001", repro_seq=self.demo["pre"]["execution_seq"], verify_seq=self.demo["qa"]["execution_seq"])
        self.through(self.phase("C3"))
        with self.assertRaisesRegex(ValueError, "terminal"):
            self.rounds.abandon(1, "too late")

    def test_abandonment_requires_reason_and_is_terminal(self):
        self.through(self.phase("C0"))
        with self.assertRaisesRegex(ValueError, "reason"):
            self.rounds.abandon(1, "")
        result = self.rounds.abandon(1, "Pause this plan after feedback")
        self.assertEqual(result["status"], "abandoned")
        with self.assertRaisesRegex(ValueError, "terminal"):
            self.rounds.close(1)
        # The previous-open guard is released; old worker branch still cannot
        # masquerade as a round-2 contract.
        task = {**self.demo["task"], "branch": f"round/2/{self.demo['fix']['id']}"}
        with self.assertRaisesRegex(ValueError, "approved worker branch"):
            self.rounds.start([task])

    def test_forged_round_cache_does_not_promote_planned_to_complete(self):
        self.through(self.phase("C0"))
        (self.h.root / "triage/rounds/round-0001.json").write_bytes(b'{"status":"complete"}')
        self.assertEqual(self.rounds.status(1)["status"], "planned")
        result = write_round_report(self.h, 1)
        text = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("# Round 1: planned", text)
        self.assertNotIn("# Round 1: complete", text)

    def test_report_distinguishes_automatic_approval_and_attestation(self):
        result = write_round_report(self.h, 1)
        text = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("auto-approved under approve_all", text)
        self.assertIn("approved by johnathan", text)
        self.assertIn("self_reported", text)
        self.assertIn("verified", text)
        self.assertIn("Push decision: **not_requested**", text)
        self.assertIn("BUG-0002", text)

    def test_tampered_payload_is_never_reported_as_verified(self):
        event = next(e for e in self.h._entries() if e["kind"] == "evidence")
        (self.h.root / "evidence" / (event["evidence_refs"][0] + ".json")).write_bytes(b"{}")
        result = write_round_report(self.h, 1)
        self.assertFalse(result["integrity_ok"])
        self.assertEqual(result["status"], "claimed, unverified")
        self.assertIn("failed integrity | unverified", Path(result["path"]).read_text(encoding="utf-8"))

    def test_broken_audit_refuses_report(self):
        self.h.audit_path.write_bytes(self.h.audit_path.read_bytes().replace(b'"entry_hash":"', b'"entry_hash":"x', 1))
        with self.assertRaises(ValueError):
            write_round_report(self.h, 1)

    def test_stale_or_revoked_planned_contract_prevents_checkpoint(self):
        self.through(self.phase("C0"))
        self.h.revoke(self.demo["fix"]["id"], approver="johnathan", reason="Fixture revoked")
        with self.assertRaisesRegex(ValueError, "no longer"):
            self.rounds.reviewed(1, "BUG-0001", build=self.demo["build"], review_seq=self.demo["review"]["execution_seq"])

    def test_dirty_checkout_blocks_C3(self):
        self.through(self.demo["closure"]["status_basis"])
        checkout = Path(self.demo["task"]["verification_repo"])
        stray = checkout / "untracked-round-test.tmp"
        try:
            stray.write_bytes(b"dirty")
            with self.assertRaisesRegex(ValueError, "dirty"):
                self.rounds.close(1)
        finally:
            stray.unlink(missing_ok=True)

    def test_source_changed_after_verified_closure_blocks_round_close(self):
        self.through(self.demo["closure"]["status_basis"])
        source = self.demo["source"]
        original = source.read_bytes()
        try:
            source.write_bytes(b"def delivery_reward(coins):\n    return -100\n")
            with self.assertRaisesRegex(ValueError, "source/build changed"):
                self.rounds.close(1)
        finally:
            source.write_bytes(original)

    def test_cache_write_failure_does_not_erase_durable_checkpoint(self):
        self.through(self.phase("C0"))
        with patch.object(Path, "write_bytes", side_effect=OSError("cache full")):
            result = self.rounds.abandon(1, "Fixture cache failure")
        self.assertEqual(result["status"], "abandoned")
        self.assertIn("cache full", result["cache_warning"])
        self.assertEqual(self.rounds.status(1)["status"], "abandoned")

    def test_round_checkpoint_audit_failure_never_completes(self):
        self.through(self.demo["closure"]["status_basis"])
        with patch.object(self.h, "_append", side_effect=OSError("audit full")):
            with self.assertRaises(OSError):
                self.rounds.close(1)
        self.assertEqual(self.rounds.status(1)["status"], "awaiting_approval")

    def test_cli_round_status_and_report(self):
        from ember_harness.__main__ import main
        prefix = ["--store", str(self.h.root)]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(prefix + ["round-status", "1"]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "complete")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(prefix + ["round-report", "1"]), 0)

    def test_unknown_round_and_invalid_plan_fail(self):
        with self.assertRaises(ValueError):
            self.rounds.status(0)
        with self.assertRaises(ValueError):
            self.rounds.status(99)
        with self.assertRaises(ValueError):
            self.rounds.start([])

    def test_plan_rejects_duplicate_workers_and_stale_versions(self):
        self.through(self.phase("C0") - 1)
        task = self.demo["task"]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.rounds.start([task, task])
        with self.assertRaisesRegex(ValueError, "one or two"):
            self.rounds.start([task, task, task])
        with self.assertRaisesRegex(ValueError, "no longer"):
            self.rounds.start([{**task, "fix_version": 2}])
        with self.assertRaisesRegex(ValueError, "snapshot"):
            self.rounds.start([{**task, "bug_id": "BUG-9999"}])
        self.assertEqual(self.rounds.start([task])["status"], "planned")

    def test_report_cannot_overwrite_approved_contract(self):
        target = self.h._path(self.demo["fix"]["id"], 1)
        original = target.read_bytes()
        with self.assertRaisesRegex(ValueError, "cannot overwrite"):
            write_round_report(self.h, 1, target)
        self.assertEqual(target.read_bytes(), original)

    def test_invalid_next_round_list_is_rejected(self):
        for value in ({}, "", ["BUG-0002", "BUG-0002"], ["invalid"]):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "next-round"):
                self.rounds.close(1, next_round=value)
