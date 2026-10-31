from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from ember_harness import Harness, canonical, content_hash
from ember_harness.amendments import record_path
import test_evidence as evidence_fixtures


class AmendmentTests(unittest.TestCase):
    setUp = evidence_fixtures.EvidenceTests.setUp
    setup_contract = evidence_fixtures.EvidenceTests.setup_contract
    hash_item = evidence_fixtures.EvidenceTests.hash_item
    verify = evidence_fixtures.EvidenceTests.verify

    def start(self, max_calls=1):
        self.setup_contract([{"kind": "file_hash", "params": {"sha256": self.expected}}], max_calls=max_calls)

    def proposal(self, pointer="/limits/max_calls", value=2):
        return {"reason": "Review feedback needs another attempt", "round": 1,
                "source": {"kind": "review", "id": "REV-0001"},
                "changes": [{"op": "replace", "pointer": pointer, "value": value}],
                "widening": {"computed": True, "items": []}, "diff": ["untrusted"]}

    def propose(self, proposal=None, **kwargs):
        return self.h.amend(self.c["id"], proposal or self.proposal(), proposed_by="worker", **kwargs)

    def approve(self, result, acknowledge=True):
        c, record = result["contract"], result["amendment_record"]
        if acknowledge and record["widening"]["items"]:
            self.h.acknowledge_widening(c["id"], c["version"], record["widening_sha256"], approver="johnathan", quote="Fixture separate acknowledgement")
        return self.h.approve(c["id"], c["version"], approver="johnathan", quote="Fixture approval", expected_hash=content_hash(c))

    def test_CT31_compiler_preserves_intent_and_computes_lineage_diff(self):
        self.start()
        original = self.h._path(self.c["id"], 1).read_bytes()
        result = self.propose()
        c, record = result["contract"], result["amendment_record"]
        self.assertEqual(c["version"], 2)
        self.assertEqual(c["status"], "draft")
        self.assertIsNone(c["content_hash"])
        self.assertEqual(c["intent_text"], self.c["intent_text"])
        self.assertEqual(c["extensions"]["lineage"]["supersedes"]["version"], 1)
        self.assertEqual(record["changed_fields"], ["/limits/max_calls"])
        self.assertTrue(record["widening"]["items"])
        self.assertIn("WIDER THAN USUAL", result["summary"]["warnings"][0])
        self.assertEqual(self.h._path(self.c["id"], 1).read_bytes(), original)
        self.assertEqual(self.h.check(self.action)["reason"], "limit_exceeded")

    def test_CT32_supersession_limits_reset_and_history_survive_restart(self):
        self.start()
        old_hash = self.h.history(self.c["id"])[0]["content_hash"]
        result = self.propose()
        approved = self.approve(result)
        self.h = Harness(self.root / "state")
        self.assertEqual(self.h.check(self.action)["decision"], "allow")
        pinned = {**self.action, "contract_version": 1}
        self.assertEqual(self.h.check(pinned)["reason"], "contract_superseded")
        history = self.h.history(self.c["id"])
        self.assertEqual([x["status"] for x in history], ["superseded", "approved"])
        self.assertEqual(history[0]["content_hash"], old_hash)
        self.assertEqual(history[0]["status_basis"], approved["approval_seq"])
        self.assertEqual(json.loads(self.h._path(self.c["id"], 1).read_text())["status"], "superseded")
        self.assertTrue((self.h._path(self.c["id"], 1).parent / "STATE.json").exists())
        record = json.loads(record_path(self.h, self.c["id"], 2).read_text())
        self.assertEqual(record["to_hash"], approved["contract"]["content_hash"])

    def test_IT14_separate_ack_required_and_bound_to_current_proposal(self):
        self.start()
        result = self.propose()
        with self.assertRaisesRegex(ValueError, "widening_ack_missing"):
            self.approve(result, acknowledge=False)
        for actor, hashed in (("worker", result["summary"]["widening_sha256"]), ("johnathan", "0" * 64)):
            with self.assertRaises(ValueError):
                self.h.acknowledge_widening(self.c["id"], 2, hashed, approver=actor, quote="fixture")
        ack = self.h.acknowledge_widening(self.c["id"], 2, result["summary"]["widening_sha256"], approver="johnathan", quote="fixture ack")
        replacement = self.propose(self.proposal(value=3), replace_pending=True)
        with self.assertRaisesRegex(ValueError, "widening_ack_missing"):
            self.approve(replacement, acknowledge=False)
        approved = self.approve(replacement)
        event = self.h._entries()[approved["approval_seq"] - 1]
        self.assertGreater(event["widening_ack_seq"], ack["seq"])

    def test_single_successor_and_invalid_pointer_operations(self):
        self.start()
        for pointer in ("/intent_text", "/version", "/extensions/lineage/supersedes", "/extensions/orchestration/role", "/id", "/allowed_actions/9/tool", "/goal~3bad"):
            with self.subTest(pointer=pointer), self.assertRaises((ValueError, IndexError, KeyError)):
                self.propose(self.proposal(pointer, "bad"))
        self.propose()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.propose()

    def test_record_draft_and_proposal_tampering_refuse_approval(self):
        for target in ("record", "draft", "proposal"):
            with self.subTest(target=target):
                # Restore pending bytes through a fresh compile between attacks.
                if not hasattr(self, "c"):
                    self.start()
                    result = self.propose()
                else:
                    result = self.propose(replace_pending=True)
                if target == "record":
                    path = record_path(self.h, self.c["id"], 2)
                elif target == "draft":
                    path = self.h._path(self.c["id"], 2)
                else:
                    path = self.h.root / result["amendment_record"]["proposal_ref"]["path"]
                value = json.loads(path.read_text())
                value["goal" if target == "draft" else "reason"] = "tampered"
                path.write_bytes(canonical(value))
                with self.assertRaises(ValueError):
                    self.approve(result)

    def test_IT13_forward_rollback_leaves_old_versions_terminal(self):
        self.start(max_calls=4)
        narrower = self.propose(self.proposal(value=2))
        self.assertFalse(narrower["amendment_record"]["widening"]["items"])
        self.approve(narrower)
        proposal = {"reason": "Restore known working terms", "round": 2, "source": {"kind": "manual", "id": "ROLLBACK-1"}, "rollback_to": 1}
        result = self.propose(proposal)
        self.assertEqual(result["contract"]["version"], 3)
        self.assertEqual(result["contract"]["limits"]["max_calls"], 4)
        self.assertTrue(result["amendment_record"]["widening"]["items"])
        self.assertEqual(result["contract"]["extensions"]["lineage"]["amendment_log"][-1]["rollback_to"], 1)
        self.approve(result)
        self.assertEqual([x["status"] for x in self.h.history(self.c["id"])], ["superseded", "superseded", "approved"])

    def test_CT33_late_evidence_uses_current_requirements(self):
        self.start()
        proposal = self.proposal("/required_evidence/produce/-", {"kind": "checklist", "params": {"items": ["reviewed"]}})
        proposal["changes"][0]["op"] = "add"
        result = self.propose(proposal)
        self.approve(result)
        verified = self.verify([self.hash_item()])
        self.assertEqual(verified["status"], "incomplete")
        self.assertTrue(self.h._entries()[-1]["late_under_superseded"])

    def test_CT36_carry_forward_rechecks_without_new_action(self):
        self.start()
        self.assertEqual(self.verify([self.hash_item()])["status"], "complete")
        self.approve(self.propose())
        actions_before = len([e for e in self.h._entries() if e["kind"] == "decision"])
        result = self.h.carry_forward(self.c["id"])
        self.assertEqual(result["results"]["produce"]["status"], "complete")
        self.assertEqual(actions_before, len([e for e in self.h._entries() if e["kind"] == "decision"]))
        self.path.write_bytes(b"changed")
        self.assertEqual(self.h.carry_forward(self.c["id"])["results"]["produce"]["status"], "incomplete")

    def test_scope_narrowing_revokes_children_and_widening_preserves_fitting_children(self):
        self.start()
        scope_id = "ct-evidence-scope-0001"
        result = self.h.amend(scope_id, self.proposal(value=60), proposed_by="planner")
        c, record = result["contract"], result["amendment_record"]
        self.h.acknowledge_widening(scope_id, 2, record["widening_sha256"], approver="johnathan", quote="fixture")
        self.h.approve(scope_id, 2, approver="johnathan", quote="fixture", expected_hash=content_hash(c))
        self.assertIn(self.c["id"], self.h._active(self.h._entries()))
        narrow = self.h.amend(scope_id, self.proposal("/allowed_paths/write", []), proposed_by="planner")
        self.h.approve(scope_id, 3, approver="johnathan", quote="fixture", expected_hash=content_hash(narrow["contract"]))
        self.assertEqual(self.h.check(self.action)["decision"], "deny")
        self.assertEqual(self.h.history(self.c["id"])[0]["status"], "revoked")

    def test_terminal_revocation_cannot_be_amended(self):
        self.start()
        self.h.revoke(self.c["id"], approver="johnathan", reason="fixture")
        with self.assertRaises(ValueError):
            self.propose()

    def test_audit_failure_keeps_old_authority_and_draft_retryable(self):
        self.start()
        result = self.propose()
        self.h.acknowledge_widening(self.c["id"], 2, result["summary"]["widening_sha256"], approver="johnathan", quote="fixture")
        with patch.object(self.h, "_append", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.approve(result, acknowledge=False)
        self.assertEqual(self.h.history(self.c["id"])[0]["status"], "approved")
        self.assertEqual(json.loads(self.h._path(self.c["id"], 2).read_text())["status"], "draft")
        self.approve(result, acknowledge=False)

    def test_child_amendment_cannot_exceed_scope_even_with_ack(self):
        self.start()
        with self.assertRaisesRegex(ValueError, "exceeds scope"):
            self.approve(self.propose(self.proposal(value=51)))

    def test_cli_amend_acknowledge_approve_history(self):
        import contextlib
        import io
        from ember_harness.__main__ import main
        self.start()
        file = self.root / "proposal.json"
        file.write_bytes(canonical(self.proposal()))
        prefix = ["--store", str(self.h.root)]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(prefix + ["amend", self.c["id"], str(file), "--proposed-by", "worker"]), 0)
        result = json.loads(output.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(prefix + ["acknowledge-widening", self.c["id"], "2", "--widening-hash", result["summary"]["widening_sha256"], "--quote", "Fixture acknowledgement"]), 0)
            self.assertEqual(main(prefix + ["approve", self.c["id"], "2", "--reviewed-hash", content_hash(result["contract"]), "--quote", "Fixture approval"]), 0)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(prefix + ["history", self.c["id"]]), 0)
        self.assertEqual([v["status"] for v in json.loads(output.getvalue())["versions"]], ["superseded", "approved"])

    def test_new_ttl_window_is_flagged_as_widening(self):
        self.start()
        proposal = self.proposal("/limits/time_window", {"not_before": None, "not_after": None, "ttl_hours": 1})
        result = self.propose(proposal)
        self.assertTrue(result["amendment_record"]["widening"]["items"])
        self.assertEqual(result["amendment_record"]["affected_actions"], ["produce"])

    def test_json_pointer_escapes_and_array_edits(self):
        from ember_harness.amendments import patch as apply_operations
        value = {"required_evidence": {"a/b~c": ["one", "two"]}}
        apply_operations(value, [{"op": "replace", "pointer": "/required_evidence/a~1b~0c/0", "value": "new"},
                                 {"op": "remove", "pointer": "/required_evidence/a~1b~0c/1"},
                                 {"op": "add", "pointer": "/required_evidence/a~1b~0c/-", "value": "end"}])
        self.assertEqual(value["required_evidence"]["a/b~c"], ["new", "end"])

    def test_unaffected_evidence_tamper_blocks_carry_forward(self):
        self.start()
        result = self.verify([self.hash_item()])
        self.approve(self.propose())
        file = self.h.root / "evidence" / (result["evidence_ref"] + ".json")
        file.write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.h.carry_forward(self.c["id"])

    def test_terminal_head_cannot_be_reapproved_and_rollback_checks_history(self):
        self.start()
        self.approve(self.propose())
        with self.assertRaises(ValueError):
            self.h.approve(self.c["id"], 1, approver="johnathan", quote="fixture", expected_hash=content_hash(self.c))
        path = self.h._path(self.c["id"], 1)
        historical = json.loads(path.read_text())
        historical["goal"] = "tampered history"
        path.write_bytes(canonical(historical))
        with self.assertRaisesRegex(ValueError, "historical contract hash mismatch"):
            self.propose({"reason": "Rollback", "round": 2, "source": {"kind": "manual", "id": "test"}, "rollback_to": 1})

    def test_scope_subset_cannot_add_previously_forbidden_argument(self):
        from ember_harness.core import subset
        self.start()
        old = json.loads(self.h._path(self.c["id"], 1).read_text())
        child = deepcopy(old)
        child["allowed_actions"][0]["args_constraints"]["expected_sha256"] = {"equals": "0" * 64}
        self.assertFalse(subset(child, old))

    def test_same_widening_with_changed_reason_requires_fresh_ack(self):
        self.start()
        result = self.propose()
        self.h.acknowledge_widening(self.c["id"], 2, result["summary"]["widening_sha256"], approver="johnathan", quote="fixture")
        proposal = self.proposal()
        proposal["reason"] = "Different feedback changes the reviewed draft"
        replacement = self.propose(proposal, replace_pending=True)
        self.assertEqual(result["summary"]["widening_sha256"], replacement["summary"]["widening_sha256"])
        with self.assertRaisesRegex(ValueError, "widening_ack_missing"):
            self.approve(replacement, acknowledge=False)

    def test_agent_change_marks_all_actions_affected(self):
        self.start()
        result = self.propose(self.proposal("/agent", "replacement-worker"))
        self.assertEqual(result["amendment_record"]["affected_actions"], ["produce"])
        self.approve(result)
        self.assertEqual(self.h.check(self.action)["decision"], "deny")
