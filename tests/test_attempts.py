from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ember_harness import Harness, canonical, content_hash
from ember_harness.attempts import Attempts, status, validate_history
from ember_harness.contract_lock import verify
from ember_harness.staged_fix import run_test
from examples.attempt_demo import setup, contract, approve, exercise, CANDIDATES


class AttemptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.ctx = setup(Path(self.temp.name).resolve())
        self.h = self.ctx["h"]
        self.attempts = Attempts(self.h)

    def failed(self, number):
        c = contract(self.ctx, number)
        approve(self.ctx, c)
        run, action = exercise(self.ctx, c)
        result = self.attempts.fail(c["id"], execution_seq=run["execution_seq"], reason="Fixture candidate fails regression")
        return c, run, action, result

    def blocked(self):
        for number in range(1, 4):
            self.failed(number)
        return self.attempts.status("BUG-0042")

    def retry(self, current):
        return self.attempts.decide("BUG-0042", choice="retry", expected_state_hash=current["state_hash"], approver="johnathan", quote="Fixture owner allows one more attempt")

    def test_TR33_three_failures_block_fourth_under_approve_all(self):
        current = self.blocked()
        self.assertEqual(current["failed_attempts"], 3)
        self.assertEqual(current["status"], "awaiting_decision")
        with self.assertRaisesRegex(ValueError, "attempt_limit_reached"):
            approve(self.ctx, contract(self.ctx, 4))
        self.assertTrue(verify(self.h.root)["ok"], verify(self.h.root))

    def test_only_owner_and_current_state_can_reopen(self):
        current = self.blocked()
        for actor, hashed, quote in (("worker", current["state_hash"], "yes"), ("hack-lead", current["state_hash"], "yes"),
                                     ("johnathan", "0" * 64, "yes"), ("johnathan", current["state_hash"], "")):
            with self.subTest(actor=actor, hashed=hashed), self.assertRaises(ValueError):
                self.attempts.decide("BUG-0042", choice="retry", expected_state_hash=hashed, approver=actor, quote=quote)
        self.assertEqual(self.retry(current)["status"], "ready")

    def test_owner_retry_is_one_use_and_does_not_reset_count(self):
        decision = self.retry(self.blocked())
        c, run, action, current = self.failed(4)
        self.assertEqual(current["failed_attempts"], 4)
        self.assertEqual(current["status"], "awaiting_decision")
        approval = self.h._active(self.h._entries())[c["id"]]
        self.assertEqual(approval["bug_attempt"]["escalation_ref"], decision["decision_seq"])
        with self.assertRaisesRegex(ValueError, "attempt_limit_reached"):
            approve(self.ctx, contract(self.ctx, 5))

    def test_stop_is_terminal_for_work_until_owner_reconsiders(self):
        current = self.blocked()
        stopped = self.attempts.decide("BUG-0042", choice="stop", expected_state_hash=current["state_hash"], approver="johnathan", quote="Fixture stop")
        self.assertEqual(stopped["status"], "stopped")
        with self.assertRaisesRegex(ValueError, "stopped"):
            approve(self.ctx, contract(self.ctx, 4))
        with self.assertRaises(ValueError):
            self.retry(current)
        self.retry(stopped)
        approve(self.ctx, contract(self.ctx, 4))

    def test_restart_and_new_round_records_do_not_reset_counts(self):
        current = self.blocked()
        self.h = Harness(self.h.root)
        self.h._append("state_transition", detail={"scope": "round", "round": 99, "checkpoint": "abandoned"}, status="abandoned", reason="Fixture unrelated round")
        self.assertEqual(Attempts(self.h).status("BUG-0042"), current)
        with self.assertRaisesRegex(ValueError, "attempt_limit_reached"):
            approve(self.ctx, contract(self.ctx, 4))

    def test_amendment_keeps_same_attempt_before_failure(self):
        c = contract(self.ctx, 1)
        approve(self.ctx, c)
        result = self.h.amend(c["id"], {"reason": "Clarify goal", "round": 1, "source": {"kind": "review", "id": "r1"},
                "changes": [{"op": "replace", "pointer": "/goal", "value": "Clarified same attempt"}]}, proposed_by="worker")
        c2 = result["contract"]
        self.h.approve(c["id"], 2, approver="johnathan", quote="Fixture amendment approval", expected_hash=content_hash(c2))
        self.h.verify_inputs(c["id"])
        current = self.attempts.status("BUG-0042")
        self.assertEqual(current["attempts_started"], 1)
        self.assertEqual(current["attempts"][0]["version"], 2)
        run, _ = exercise(self.ctx, c2)
        self.attempts.fail(c["id"], execution_seq=run["execution_seq"], reason="Fails after amendment")
        self.assertEqual(self.attempts.status("BUG-0042")["failed_attempts"], 1)

    def test_finished_attempt_cannot_be_reused_or_amended_back_to_work(self):
        c, run, action, _ = self.failed(1)
        self.assertEqual(self.h.check(action)["reason"], "attempt_failed")
        with self.assertRaisesRegex(ValueError, "attempt_failed"):
            self.attempts.fail(c["id"], execution_seq=run["execution_seq"], reason="Duplicate outcome")
        result = self.h.amend(c["id"], {"reason": "Try bypassing finished status", "round": 2, "source": {"kind": "manual", "id": "r2"},
                    "changes": [{"op": "replace", "pointer": "/goal", "value": "Another goal"}]}, proposed_by="worker")
        with self.assertRaisesRegex(ValueError, "cannot be reopened"):
            self.h.approve(c["id"], 2, approver="johnathan", quote="Fixture", expected_hash=content_hash(result["contract"]))

    def test_baseline_repro_and_passing_test_do_not_count_as_failed_fixes(self):
        c = contract(self.ctx, 1)
        approve(self.ctx, c)
        action = {"agent": c["agent"], "contract_id": c["id"], "tool": "test.run", "args": {"script": self.ctx["script"].as_posix()},
                  "paths": {"read": [self.ctx["source"].as_posix(), self.ctx["script"].as_posix()], "write": []}, "spend": 0}
        pre = run_test(self.h, action)
        with self.assertRaisesRegex(ValueError, "baseline repro"):
            self.attempts.fail(c["id"], execution_seq=pre["execution_seq"], reason="Baseline only")
        self.assertEqual(self.attempts.status("BUG-0042")["failed_attempts"], 0)

    def test_passing_regression_cannot_be_recorded_as_failure(self):
        c = contract(self.ctx, 1, code=CANDIDATES[-1])
        approve(self.ctx, c)
        run, _ = exercise(self.ctx, c)
        self.assertEqual(run["returncode"], 0)
        with self.assertRaisesRegex(ValueError, "failing regression"):
            self.attempts.fail(c["id"], execution_seq=run["execution_seq"], reason="False failure")

    def test_other_bug_has_independent_budget(self):
        self.blocked()
        c = contract(self.ctx, 1, bug_id="BUG-0043")
        approve(self.ctx, c)
        self.assertEqual(self.attempts.status("BUG-0043")["attempts_started"], 1)
        self.assertEqual(self.attempts.status("BUG-0042")["status"], "awaiting_decision")

    def test_parallel_unfinished_fix_contracts_cannot_reserve_extra_attempts(self):
        approve(self.ctx, contract(self.ctx, 1))
        with self.assertRaisesRegex(ValueError, "in_progress"):
            approve(self.ctx, contract(self.ctx, 2))

    def test_revocation_consumes_attempt_instead_of_resetting_it(self):
        for number in range(1, 4):
            c = contract(self.ctx, number)
            approve(self.ctx, c)
            self.h.revoke(c["id"], approver="johnathan", reason="Fixture abandoned candidate")
        current = self.attempts.status("BUG-0042")
        self.assertEqual(current["status"], "awaiting_decision")
        self.assertEqual(current["attempts_started"], 3)
        self.assertEqual(current["failed_attempts"], 0)
        with self.assertRaisesRegex(ValueError, "attempt_limit_reached"):
            approve(self.ctx, contract(self.ctx, 4))

    def test_bug_identity_and_derived_from_cannot_be_changed_to_escape_limit(self):
        c, _, _, _ = self.failed(1)
        other = contract(self.ctx, 1, bug_id="BUG-0043")
        other["extensions"]["lineage"]["derived_from"] = {"id": c["id"]}
        with self.assertRaisesRegex(ValueError, "cannot change its bug identity"):
            approve(self.ctx, other)
        mismatched = contract(self.ctx, 2)
        mismatched["extensions"]["triage"]["bug_id"] = "BUG-9999"
        with self.assertRaisesRegex(ValueError, "differs"):
            approve(self.ctx, mismatched)

    def test_failure_audit_write_error_does_not_increment_count(self):
        c = contract(self.ctx, 1)
        approve(self.ctx, c)
        run, _ = exercise(self.ctx, c)
        with patch.object(self.h, "_append", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.attempts.fail(c["id"], execution_seq=run["execution_seq"], reason="Fixture failed write")
        self.assertEqual(self.attempts.status("BUG-0042")["failed_attempts"], 0)
        self.attempts.fail(c["id"], execution_seq=run["execution_seq"], reason="Retry recording the outcome")

    def test_owner_audit_write_error_grants_no_retry_credit(self):
        current = self.blocked()
        with patch.object(self.h, "_append", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.retry(current)
        self.assertEqual(self.attempts.status("BUG-0042"), current)

    def test_tampered_captured_output_cannot_establish_failure_or_pass_lock(self):
        c = contract(self.ctx, 1)
        approve(self.ctx, c)
        run, _ = exercise(self.ctx, c)
        path = self.h.root / "executions" / (run["output_ref"] + ".json")
        path.write_bytes(b"{}")
        with self.assertRaises(ValueError):
            self.attempts.fail(c["id"], execution_seq=run["execution_seq"], reason="Tampered")
        self.assertFalse(verify(self.h.root)["ok"])

    def test_cli_status_failure_and_owner_decision(self):
        from ember_harness.__main__ import main
        current = self.blocked()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["--store", str(self.h.root), "attempt-status", "BUG-0042"]), 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "awaiting_decision")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--store", str(self.h.root), "attempt-decide", "BUG-0042", "--choice", "retry", "--state-hash", current["state_hash"], "--quote", "Fixture owner decision"]), 0)

    def test_blanket_or_duplicate_owner_decisions_do_not_stack(self):
        current = self.blocked()
        with self.assertRaises(ValueError):
            self.attempts.decide("BUG-0042", choice="approve_all", expected_state_hash=current["state_hash"], approver="johnathan", quote="Fixture blanket yes")
        self.retry(current)
        with self.assertRaises(ValueError):
            self.retry(current)

    def test_stale_execution_from_prior_version_cannot_finish_new_version(self):
        c = contract(self.ctx, 1)
        approve(self.ctx, c)
        run, _ = exercise(self.ctx, c)
        result = self.h.amend(c["id"], {"reason": "Clarify before final verdict", "round": 1, "source": {"kind": "review", "id": "r"},
                "changes": [{"op": "replace", "pointer": "/goal", "value": "Current version has a new reviewed goal"}]}, proposed_by="worker")
        self.h.approve(c["id"], 2, approver="johnathan", quote="Fixture approval", expected_hash=content_hash(result["contract"]))
        with self.assertRaisesRegex(ValueError, "current attempt version"):
            self.attempts.fail(c["id"], execution_seq=run["execution_seq"], reason="Stale verdict")
        self.assertEqual(self.attempts.status("BUG-0042")["failed_attempts"], 0)

    def test_failed_extra_approval_write_keeps_one_retry_available(self):
        self.retry(self.blocked())
        c = contract(self.ctx, 4)
        self.h.save_draft(c)
        with patch.object(self.h, "_append", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.h.approve(c["id"], 1, approver="johnathan", quote="Fixture approval", expected_hash=content_hash(c), parent_id=self.ctx["scope"]["id"])
        self.assertEqual(self.attempts.status("BUG-0042")["status"], "ready")
        approve(self.ctx, c)
        self.assertEqual(self.attempts.status("BUG-0042")["attempts_started"], 4)

    def test_report_and_lock_verify_failure_proofs_and_owner_notes(self):
        from ember_harness.reporting import write_attempt_report
        current = self.blocked()
        self.retry(current)
        result = write_attempt_report(self.h, "BUG-0042")
        self.assertTrue(result["integrity_ok"])
        text = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("Failed: **3**", text)
        self.assertIn("self_reported", text)
        self.assertEqual(len(verify(self.h.root)["bug_attempts"]), 1)
        escalation = next(e for e in self.h._entries() if e.get("scope") == "attempt_escalation")
        (self.h.root / "evidence" / (escalation["evidence_refs"][0] + ".json")).write_bytes(b"{}")
        result = write_attempt_report(self.h, "BUG-0042")
        self.assertFalse(result["integrity_ok"])
        self.assertEqual(result["status"], "claimed, unverified")

    def test_fix_prefix_cannot_drop_snapshot_or_declared_bug(self):
        c = contract(self.ctx, 1)
        c["inputs"] = [i for i in c["inputs"] if i["name"] != "bug_snapshot"]
        c["extensions"].pop("triage")
        with self.assertRaisesRegex(ValueError, "pinned bug_snapshot"):
            approve(self.ctx, c)

    def test_renamed_derived_contract_cannot_drop_bug_binding(self):
        c, _, _, _ = self.failed(1)
        renamed = contract(self.ctx, 2)
        renamed["id"] = "ct-renamed-worker-0002"
        renamed["inputs"] = [i for i in renamed["inputs"] if i["name"] != "bug_snapshot"]
        renamed["extensions"].pop("triage")
        renamed["extensions"]["lineage"]["derived_from"] = {"id": c["id"]}
        with self.assertRaisesRegex(ValueError, "cannot change its bug identity"):
            approve(self.ctx, renamed)


if __name__ == "__main__":
    unittest.main()
