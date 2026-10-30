from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ember_harness import Harness, canonical, content_hash, draft


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.data = self.root / "files"
        self.data.mkdir()
        self.path = self.data / "result.txt"
        self.path.write_bytes(b"expected")
        self.expected = sha256(b"expected").hexdigest()
        self.h = Harness(self.root / "state")

    def setup_contract(self, requirements, tool="fs.write", inputs=None, max_calls=None):
        now = datetime.now(timezone.utc)
        glob = self.data.as_posix() + "/*.txt"
        c = draft("ct-evidence-scope-0001", "planner", "Verify a local result", role="scope")
        c["allowed_paths"] = {"read": [glob], "write": [glob]}
        c["limits"]["time_window"] = {"not_before": now.isoformat(), "not_after": (now + timedelta(hours=1)).isoformat()}
        constraints = {"path": {"path_within": glob}, "content": {"equals": "expected"}}
        self.args = {"path": self.path.as_posix(), "content": "expected"}
        if tool != "fs.write":
            self.source = self.data / "source.txt"
            self.source.write_bytes(b"expected")
            constraints = {"src": {"path_within": glob}, "dest": {"path_within": glob}}
            self.args = {"src": self.source.as_posix(), "dest": self.path.as_posix()}
        c["allowed_actions"] = [{"action_id": "produce", "tool": tool, "class": "write", "args_constraints": constraints}]
        c["required_evidence"] = {"produce": requirements}
        c["inputs"] = inputs or []
        self.h.save_draft(c)
        self.h.approve(c["id"], 1, approver="johnathan", quote="Fixture only", expected_hash=content_hash(c))
        self.c = deepcopy(c)
        self.c.update(id="ct-evidence-worker-0001", agent="worker")
        self.c["extensions"]["orchestration"]["role"] = "coding"
        if max_calls is not None:
            self.c["limits"]["max_calls"] = max_calls
        self.h.save_draft(self.c)
        self.h.approve(self.c["id"], 1, approver="johnathan", quote="Fixture only", expected_hash=content_hash(self.c), parent_id=c["id"])
        if inputs:
            self.assertTrue(self.h.verify_inputs(self.c["id"]))
        self.action = {"agent": "worker", "contract_id": self.c["id"], "tool": tool, "args": self.args,
                       "paths": {"read": [], "write": [self.path.as_posix()]}, "spend": 0}
        decision = self.h.check(self.action)
        self.assertEqual(decision["decision"], "allow")
        self.seq = decision["audit_seq"]

    def verify(self, items):
        return self.h.verify_evidence(self.c["id"], "produce", items, decision_seq=self.seq)

    def hash_item(self):
        return {"kind": "file_hash", "params": {"path": self.path.as_posix(), "sha256": self.expected}, "result": "pass"}

    def test_file_hash_complete_and_CT23_payload_reference(self):
        self.setup_contract([{"kind": "file_hash", "params": {"path": self.path.as_posix()}}])
        result = self.verify([self.hash_item()])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["items"][0]["label"], "verified")
        payload = self.h.root / "evidence" / (result["evidence_ref"] + ".json")
        self.assertEqual(sha256(payload.read_bytes()).hexdigest(), result["evidence_ref"])
        entry = self.h._entries()[-1]
        self.assertEqual(entry["seq"], result["status_basis"])
        self.assertEqual(entry["evidence_refs"], [result["evidence_ref"]])

    def test_missing_or_changed_file_and_forged_pass_incomplete(self):
        self.setup_contract([{"kind": "file_hash", "params": {}}])
        self.assertEqual(self.verify([])["status"], "incomplete")
        self.path.write_bytes(b"tampered")
        self.assertEqual(self.verify([self.hash_item()])["status"], "incomplete")
        self.path.unlink()
        self.assertEqual(self.verify([self.hash_item()])["status"], "incomplete")

    def test_refresh_rechecks_current_bytes(self):
        self.setup_contract([{"kind": "file_hash", "params": {}}])
        self.assertEqual(self.verify([self.hash_item()])["status"], "complete")
        self.path.write_bytes(b"changed")
        result = self.h.step_status(self.c["id"], "produce")
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(self.h._entries()[-1]["status"], "incomplete")

    def test_CT23_stored_payload_tamper_rejected(self):
        self.setup_contract([{"kind": "file_hash", "params": {}}])
        result = self.verify([self.hash_item()])
        file = self.h.root / "evidence" / (result["evidence_ref"] + ".json")
        file.write_text('{"items":[]}')
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.h.step_status(self.c["id"], "produce")

    def test_decision_binding_and_revocation(self):
        self.setup_contract([{"kind": "file_hash", "params": {}}])
        with self.assertRaises(ValueError):
            self.h.verify_evidence(self.c["id"], "produce", [self.hash_item()], decision_seq=1)
        denied = deepcopy(self.action)
        denied["tool"] = "network.post"
        self.seq = self.h.check(denied)["audit_seq"]
        with self.assertRaises(ValueError):
            self.verify([self.hash_item()])
        self.h.revoke(self.c["id"], approver="johnathan", reason="fixture")
        with self.assertRaises(ValueError):
            self.verify([self.hash_item()])

    def test_unrelated_and_outside_files_rejected(self):
        self.setup_contract([{"kind": "file_hash", "params": {}}])
        other = self.data / "other.txt"
        other.write_bytes(b"expected")
        item = self.hash_item()
        item["params"]["path"] = other.as_posix()
        self.assertEqual(self.verify([item])["status"], "incomplete")

    def test_checklist_cannot_establish_complete_alone(self):
        self.setup_contract([{"kind": "checklist", "params": {"items": ["reviewed"]}}])
        item = {"kind": "checklist", "params": {"checks": {"reviewed": True}, "attested_by": "worker"}}
        result = self.verify([item])
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["items"][0]["label"], "self_reported")
        item["params"]["checks"]["reviewed"] = False
        self.assertEqual(self.verify([item])["items"][0]["result"], "fail")

    def test_approved_regex_cannot_be_replaced(self):
        self.setup_contract([{"kind": "output_snippet", "params": {"pattern": "^PASS$"}}])
        bad = {"kind": "output_snippet", "params": {"text": "FAIL", "pattern": ".*"}}
        self.assertEqual(self.verify([bad])["status"], "incomplete")
        bad["params"]["text"] = "PASS"
        self.assertEqual(self.verify([bad])["status"], "complete")

    def test_file_list_sizes_and_count(self):
        self.setup_contract([{"kind": "file_list", "params": {"expect_count": 1}}])
        item = {"kind": "file_list", "params": {"files": [{"path": self.path.as_posix(), "size": 8}]}}
        self.assertEqual(self.verify([item])["status"], "complete")
        item["params"]["files"][0]["size"] = 9
        self.assertEqual(self.verify([item])["status"], "incomplete")

    def test_CT16_copy_hashes(self):
        self.setup_contract([{"kind": "source_dest_hash", "params": {"conversion": None}}], tool="fs.copy")
        item = {"kind": "source_dest_hash", "params": {"source_path": self.source.as_posix(), "dest_path": self.path.as_posix(),
                 "conversion": None, "source_sha256": self.expected, "dest_sha256": self.expected}}
        self.assertEqual(self.verify([item])["status"], "complete")
        self.path.write_bytes(b"different")
        item["params"]["dest_sha256"] = sha256(b"different").hexdigest()
        self.assertEqual(self.verify([item])["status"], "incomplete")

    def test_CT16_conversion_different_hashes(self):
        self.setup_contract([{"kind": "source_dest_hash", "params": {"conversion": "jpeg_to_png"}}], tool="image.convert_png")
        self.path.write_bytes(b"converted")
        item = {"kind": "source_dest_hash", "params": {"source_path": self.source.as_posix(), "dest_path": self.path.as_posix(),
                "conversion": "jpeg_to_png", "source_sha256": self.expected, "dest_sha256": sha256(b"converted").hexdigest()}}
        self.assertEqual(self.verify([item])["status"], "complete")

    def test_CT22_late_bound_hash_cannot_be_replaced(self):
        self.setup_contract([{"kind": "file_hash", "params": {}}], inputs=[{"name": "chained", "path": self.path.as_posix(), "sha256": None, "late_bind": True}])
        self.path.write_bytes(b"changed")
        item = self.hash_item()
        item["params"]["sha256"] = sha256(b"changed").hexdigest()
        self.assertEqual(self.verify([item])["status"], "incomplete")
        self.assertFalse(self.h.verify_inputs(self.c["id"]))

    def test_approved_hash_cannot_be_replaced(self):
        self.setup_contract([{"kind": "file_hash", "params": {"sha256": self.expected}}])
        self.path.write_bytes(b"changed")
        item = self.hash_item()
        item["params"]["sha256"] = sha256(b"changed").hexdigest()
        self.assertEqual(self.verify([item])["status"], "incomplete")

    def test_malformed_evidence_and_unrelated_list_fail(self):
        self.setup_contract([{"kind": "file_list", "params": {"expect_count": 1}}])
        self.assertEqual(self.verify([{"kind": "file_list", "params": "bad"}])["status"], "incomplete")
        other = self.data / "unrelated.txt"
        other.write_bytes(b"expected")
        item = {"kind": "file_list", "params": {"files": [{"path": other.as_posix(), "size": 8}]}}
        self.assertEqual(self.verify([item])["status"], "incomplete")

    def test_audit_failure_never_returns_complete(self):
        self.setup_contract([{"kind": "file_hash", "params": {}}])
        with patch.object(self.h, "_append", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.verify([self.hash_item()])
