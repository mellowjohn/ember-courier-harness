from copy import deepcopy
from hashlib import sha256
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import ValidationError
from ember_harness import canonical, content_hash, draft
from ember_harness.intake import Intake, canonical_bug_id, fingerprint, route
from ember_harness.attempts import Attempts
from ember_harness.contract_lock import verify
from examples.intake_demo import setup, ingest


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.ctx = setup(Path(self.temp.name).resolve())
        self.h, self.intake = self.ctx["h"], self.ctx["intake"]

    def merge(self, a, b):
        return self.intake.confirm_duplicate(a["id"], b["id"], contract_id=self.ctx["reviewer"]["id"], bug_hash=a["record_hash"], target_hash=b["record_hash"], note="Fixture QA confirms the same reproducible symptom")

    def fix(self, bug_id, cid="ct-fix-intake-0001"):
        snap = self.intake.snapshot(bug_id, cid)
        root = draft("ct-fix-intake-scope-0001", "fix-planner", "Read frozen intake data", role="scope")
        root["limits"]["time_window"] = deepcopy(self.ctx["scope"]["limits"]["time_window"])
        root["allowed_paths"]["read"] = [(self.h.root / "triage/fix_contracts").as_posix() + "/*/*.json"]
        self.h.save_draft(root)
        self.h.approve(root["id"], 1, approver="johnathan", quote="Fixture scope approval", expected_hash=content_hash(root))
        child = deepcopy(root)
        child.update(id=cid, agent="fix-author")
        child["extensions"]["orchestration"]["role"] = "coding"
        child["inputs"] = [{"name": "bug_snapshot", "path": snap["path"], "sha256": snap["sha256"]}]
        self.h.save_draft(child)
        approved = self.h.approve(cid, 1, approver="johnathan", quote="Fixture fix approval", expected_hash=content_hash(child), parent_id=root["id"])
        return snap, approved["contract"]

    def test_complete_finding_has_audited_state_and_owner(self):
        bug = ingest(self.ctx, "complete")
        self.assertEqual(bug["state"], "triaged")
        self.assertEqual(bug["owner"], "Systems Designer")
        event = self.h._entries()[bug["status_basis"] - 1]
        self.assertEqual(event["records"][0]["record_hash"], bug["record_hash"])
        self.assertTrue(verify(self.h.root)["ok"])

    def test_TR03_missing_fields_return_to_QA_then_update(self):
        finding = deepcopy(self.ctx["finding"])
        finding.pop("steps"); finding.pop("expected")
        bug = ingest(self.ctx, "missing", finding)
        self.assertEqual(bug["state"], "needs_repro")
        self.assertEqual(bug["owner"], "QA")
        self.assertEqual(set(bug["completeness"]["missing"]), {"steps", "expected"})
        changed = ingest(self.ctx, "fixed", self.ctx["finding"], bug_id=bug["id"], expected_hash=bug["record_hash"])
        self.assertEqual(changed["id"], bug["id"])
        self.assertEqual(changed["state"], "triaged")
        with self.assertRaisesRegex(ValueError, "current canonical"):
            ingest(self.ctx, "stale", bug_id=bug["id"], expected_hash=bug["record_hash"])

    def test_blank_repro_fields_cannot_claim_completeness(self):
        finding = {**self.ctx["finding"], "expected": "   ", "area": "  "}
        bug = ingest(self.ctx, "blank", finding)
        self.assertEqual(bug["state"], "needs_repro")
        self.assertIn("area", bug["completeness"]["missing"])
        with self.assertRaises(ValueError):
            ingest(self.ctx, "blank-step", {**self.ctx["finding"], "steps": [" "]})

    def test_matching_fingerprint_never_auto_merges_and_keeps_oldest(self):
        first = ingest(self.ctx, "first")
        second = ingest(self.ctx, "second", {**self.ctx["finding"], "summary": "One coin is missing after delivery"})
        self.assertIsNone(second["duplicate_of"])
        self.assertEqual(second["duplicate_candidates"][0]["bug_id"], first["id"])
        self.merge(second, first)
        target = self.intake.get(first["id"])
        alias = self.intake.get(second["id"])
        self.assertEqual(alias["state"], "duplicate")
        self.assertEqual(alias["duplicate_of"], first["id"])
        self.assertEqual(target["duplicate_count"], 1)
        self.assertEqual(len(target["finding_refs"]), 2)
        self.assertEqual(canonical_bug_id(self.h._entries(), second["id"]), first["id"])

    def test_text_similarity_is_only_a_hint(self):
        ingest(self.ctx, "first")
        other = {**self.ctx["finding"], "symptom_tag": "different_symptom", "build_family": "different-family"}
        second = ingest(self.ctx, "second", other)
        self.assertEqual(second["duplicate_candidates"][0]["reason"], "text_similarity_hint")
        self.assertIsNone(second["duplicate_of"])

    def test_build_family_is_explicit_and_defaults_to_exact_build(self):
        a = {k: v for k, v in self.ctx["finding"].items() if k != "build_family"}
        b = {**a, "build_id": "another-release"}
        self.assertNotEqual(fingerprint(a), fingerprint(b))
        self.assertEqual(fingerprint({**a, "build_family": "release"}), fingerprint({**b, "build_family": "release"}))

    def test_log_fingerprint_normalizes_addresses_numbers_timestamps(self):
        a = {"source": "log", "subsystem": "renderer", "stack_frames": ["2026-10-29T12:00:00Z Load 0xABC line 41", "Draw 7", "Tick 9", "ignored A"]}
        b = {"source": "log", "subsystem": "renderer", "stack_frames": ["2026-10-30T13:02:10Z Load 0xDEF line 83", "Draw 8", "Tick 4", "ignored B"]}
        self.assertEqual(fingerprint(a), fingerprint(b))
        self.assertNotEqual(fingerprint(a), fingerprint({**b, "subsystem": "audio"}))

    def test_log_crash_can_substitute_excerpt_for_steps_but_requires_S0_review(self):
        finding = {**self.ctx["finding"], "source": "log", "area": "crash", "impact": "crash", "severity": "S3", "log_excerpt": "Crash at 0xABCD"}
        finding.pop("steps")
        bug = ingest(self.ctx, "crash", finding)
        self.assertTrue(bug["completeness"]["complete"])
        self.assertEqual(bug["severity_proposed"], "S0")
        self.assertIsNone(bug["severity"])
        self.assertEqual(bug["state"], "new")
        reviewed = self.intake.review_severity(bug["id"], contract_id=self.ctx["reviewer"]["id"], expected_hash=bug["record_hash"], severity="S0", demo_impact=True, note="Fixture QA confirms crash")["bugs"][0]
        self.assertEqual(reviewed["owner"], "Engine")
        self.assertFalse(reviewed["route"]["code_fix_allowed"])
        with self.assertRaises(ValueError):
            self.intake.snapshot(bug["id"], "ct-fix-engine-0001")

    def test_demo_path_severity_changes_require_review(self):
        first = ingest(self.ctx, "first", {**self.ctx["finding"], "demo_impact": True, "severity": "S1", "impact": "core_loop_broken"})
        updated = ingest(self.ctx, "changed", {**self.ctx["finding"], "demo_impact": True, "severity": "S2"}, bug_id=first["id"], expected_hash=first["record_hash"])
        self.assertTrue(updated["severity_review_required"])
        self.assertEqual(updated["state"], "new")

    def test_confirmed_S0_cannot_be_downgraded_by_unreviewed_update(self):
        bug = ingest(self.ctx, "s0", {**self.ctx["finding"], "severity": "S0"})
        confirmed = self.intake.review_severity(bug["id"], contract_id=self.ctx["reviewer"]["id"], expected_hash=bug["record_hash"], severity="S0", demo_impact=False, note="Fixture confirmed critical finding")["bugs"][0]
        self.assertEqual(confirmed["severity_basis"], "qa_review")
        changed = ingest(self.ctx, "downgrade", self.ctx["finding"], bug_id=bug["id"], expected_hash=confirmed["record_hash"])
        self.assertEqual(changed["state"], "new")
        self.assertTrue(changed["severity_review_required"])
        self.assertNotEqual(changed["severity_basis"], "qa_review")

    def test_confirmed_merge_appends_distinct_evidence_and_preserves_title(self):
        first = ingest(self.ctx, "first")
        extra = self.ctx["inputs"] / "another.log"
        extra.write_bytes(b"Independent reproduction of the missing reward coin")
        finding = {**self.ctx["finding"], "summary": "Another reward report", "evidence": [{"path": extra.as_posix(), "sha256": sha256(extra.read_bytes()).hexdigest()}]}
        second = ingest(self.ctx, "second", finding)
        self.merge(second, first)
        merged = self.intake.get(first["id"])
        self.assertEqual(merged["title"], first["title"])
        self.assertEqual(len(merged["evidence"]), 2)
        self.assertTrue(verify(self.h.root)["ok"])

    def test_duplicate_alias_cannot_authorize_independent_fix_identity(self):
        from ember_harness.intake import fix_identity_allowed
        first, second = ingest(self.ctx, "first"), ingest(self.ctx, "second")
        self.merge(second, first)
        with self.assertRaisesRegex(ValueError, "canonical duplicate"):
            fix_identity_allowed(self.h._entries(), second["id"])
        fix_identity_allowed(self.h._entries(), first["id"])

    def test_priority_order_matches_architecture(self):
        from ember_harness.intake import classify
        ranks = []
        for severity, demo in (("S0", False), ("S1", True), ("S1", False), ("S2", True), ("S2", False), ("S3", True)):
            bug = {**deepcopy(self.ctx["finding"]), "severity": severity, "severity_proposed": severity, "severity_review_required": False, "demo_impact": demo}
            ranks.append(classify(bug)["priority"])
        self.assertEqual(ranks, [0, 1, 2, 3, 4, 5])

    def test_route_table_and_non_code_policy(self):
        expected = {"rendering": "Engine", "physics": "Engine", "tools": "Editor", "asset_import": "Editor", "verification": "QA", "dialogue": "Narrative", "vfx": "Concept Artist", "public_posts": "Herald", "community": "Comms", "crafting": "Systems Designer", "unknown": "Hack Lead"}
        for area, owner in expected.items():
            with self.subTest(area=area):
                self.assertEqual(route(area)["owner"], owner)
        for area in ("messages", "store_pages", "engine_code", "unknown"):
            bug = ingest(self.ctx, area, {**self.ctx["finding"], "area": area, "symptom_tag": area})
            with self.assertRaises(ValueError):
                self.intake.snapshot(bug["id"], "ct-fix-blocked-0001")

    def test_review_requires_distinct_approved_QA_and_current_hashes(self):
        a, b = ingest(self.ctx, "a"), ingest(self.ctx, "b")
        with self.assertRaisesRegex(ValueError, "QA reviewer"):
            self.intake.confirm_duplicate(b["id"], a["id"], contract_id=self.ctx["contract"]["id"], bug_hash=b["record_hash"], target_hash=a["record_hash"], note="Self-confirm")
        with self.assertRaisesRegex(ValueError, "current open"):
            self.intake.confirm_duplicate(b["id"], a["id"], contract_id=self.ctx["reviewer"]["id"], bug_hash="0" * 64, target_hash=a["record_hash"], note="Stale")
        with self.assertRaises(ValueError):
            self.intake.confirm_duplicate(b["id"], a["id"], contract_id=self.ctx["reviewer"]["id"], bug_hash=b["record_hash"], target_hash=a["record_hash"], note="")

    def test_evidence_hash_and_scope_fail_closed(self):
        bad = deepcopy(self.ctx["finding"])
        bad["evidence"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            ingest(self.ctx, "bad-hash", bad)
        secret = self.ctx["folder"] / "outside.log"
        secret.write_bytes(b"not in approved read paths")
        bad["evidence"] = [{"path": secret.as_posix(), "sha256": sha256(secret.read_bytes()).hexdigest()}]
        with self.assertRaisesRegex(ValueError, "denied"):
            ingest(self.ctx, "outside", bad)
        self.assertEqual(self.intake.list(), [])

    def test_evidence_copy_tamper_and_cache_tamper(self):
        bug = ingest(self.ctx, "one")
        cache = self.ctx["data"] / "bugs" / (bug["id"] + ".json")
        cache.write_bytes(b'{"state":"closed"}')
        self.assertEqual(self.intake.get(bug["id"])["state"], "triaged")
        Path(bug["evidence"][0]["path"]).write_bytes(b"tampered")
        self.assertFalse(verify(self.h.root)["ok"])
        with self.assertRaisesRegex(ValueError, "hash or path mismatch"):
            self.intake.snapshot(bug["id"], "ct-fix-tampered-0001")
        with self.assertRaisesRegex(ValueError, "overwrite refused"):
            ingest(self.ctx, "two")

    def test_frozen_snapshot_uses_canonical_id_and_survives_later_bug_updates(self):
        a, b = ingest(self.ctx, "a"), ingest(self.ctx, "b")
        self.merge(b, a)
        snap, c = self.fix(b["id"])
        self.assertEqual(snap["id"], a["id"])
        self.assertEqual(Attempts(self.h).status(b["id"])["bug_id"], a["id"])
        current = self.intake.get(a["id"])
        ingest(self.ctx, "extra-details", {**self.ctx["finding"], "actual": "Four coins on repeated runs"}, bug_id=a["id"], expected_hash=current["record_hash"])
        self.assertTrue(self.h.verify_inputs(c["id"]))
        self.assertEqual(json.loads(Path(snap["path"]).read_text())["actual"], "Four coins")
        with self.assertRaisesRegex(ValueError, "cannot be overwritten"):
            self.intake.snapshot(a["id"], c["id"])

    def test_late_merge_cannot_erase_allocated_attempt_history(self):
        a, b = ingest(self.ctx, "a"), ingest(self.ctx, "b")
        self.fix(a["id"])
        with self.assertRaisesRegex(ValueError, "owner reconciliation"):
            self.merge(b, a)
        self.assertEqual(Attempts(self.h).status(a["id"])["attempts_started"], 1)
        self.assertIsNone(self.intake.get(b["id"])["duplicate_of"])

    def test_intake_expiry_or_revocation_denies_new_findings(self):
        self.h.revoke(self.ctx["contract"]["id"], approver="johnathan", reason="Fixture revoke")
        with self.assertRaisesRegex(ValueError, "active approved"):
            ingest(self.ctx, "denied")
        self.assertEqual(self.intake.list(), [])

    def test_expired_intake_window_denies_inspection(self):
        from datetime import datetime, timedelta
        self.h.clock = lambda: datetime.fromisoformat(self.ctx["scope"]["limits"]["time_window"]["not_after"]) + timedelta(seconds=1)
        with self.assertRaisesRegex(ValueError, "outside_time_window"):
            ingest(self.ctx, "expired")
        self.assertEqual(self.intake.list(), [])

    def test_QA_contract_cannot_confirm_its_own_intake_author(self):
        a, b = ingest(self.ctx, "a"), ingest(self.ctx, "b")
        reviewer = deepcopy(self.ctx["reviewer"])
        reviewer.update(id="ct-self-reviewer-0001", agent=self.ctx["contract"]["agent"])
        self.h.save_draft(reviewer)
        self.h.approve(reviewer["id"], 1, approver="johnathan", quote="Fixture review approval", expected_hash=content_hash(reviewer), parent_id=self.ctx["scope"]["id"])
        with self.assertRaisesRegex(ValueError, "must differ"):
            self.intake.confirm_duplicate(b["id"], a["id"], contract_id=reviewer["id"], bug_hash=b["record_hash"], target_hash=a["record_hash"], note="Self review")

    def test_intake_report_fails_integrity_when_evidence_changes(self):
        from ember_harness.reporting import write_intake_report
        bug = ingest(self.ctx, "one")
        result = write_intake_report(self.h, self.ctx["data"])
        self.assertTrue(result["integrity_ok"])
        Path(bug["evidence"][0]["path"]).write_bytes(b"changed")
        result = write_intake_report(self.h, self.ctx["data"])
        self.assertFalse(result["integrity_ok"])
        self.assertIn("claimed, unverified", Path(result["path"]).read_text(encoding="utf-8"))

    def test_broken_or_unsupported_finding_cannot_write_a_bug(self):
        with self.assertRaises(ValidationError):
            ingest(self.ctx, "unsupported", {**self.ctx["finding"], "execute": "publish.now"})
        with self.assertRaises(ValidationError):
            ingest(self.ctx, "bad-frequency", {**self.ctx["finding"], "frequency": "all_the_time"})
        self.assertEqual(self.intake.list(), [])

    def test_audit_failure_never_creates_authoritative_bug(self):
        original = self.h._append
        def append(kind, **fields):
            if fields.get("detail", {}).get("scope") == "bug_intake":
                raise OSError("audit full")
            return original(kind, **fields)
        with patch.object(self.h, "_append", side_effect=append):
            with self.assertRaises(OSError):
                ingest(self.ctx, "fail")
        self.assertEqual(self.intake.list(), [])

    def test_cli_ingest_list_report_and_snapshot(self):
        from ember_harness.__main__ import main
        source = self.ctx["inputs"] / "cli.json"
        source.write_bytes(canonical(self.ctx["finding"]))
        prefix = ["--store", str(self.h.root)]
        common = ["--root", str(self.ctx["data"])]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(prefix + ["bug-ingest", str(source), "--contract", self.ctx["contract"]["id"], *common]), 0)
        bug = json.loads(output.getvalue())["bugs"][0]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(prefix + ["bug-list", *common]), 0)
            self.assertEqual(main(prefix + ["bug-report", *common]), 0)
            self.assertEqual(main(prefix + ["bug-snapshot", bug["id"], "ct-fix-cli-0001", *common]), 0)

    def test_existing_audit_ids_and_concurrent_reservations_are_not_overwritten(self):
        self.h._append("legacy_finding_reference", bug_id="BUG-0042")
        self.assertEqual(ingest(self.ctx, "next")["id"], "BUG-0043")
        original = self.intake._gate
        def gate(cid, tool, args, **kwargs):
            result = original(cid, tool, args, **kwargs)
            if tool == "triage.ingest":
                self.h._append("legacy_finding_reference", bug_id="BUG-0044")
            return result
        with patch.object(self.intake, "_gate", side_effect=gate):
            with self.assertRaisesRegex(ValueError, "concurrently"):
                ingest(self.ctx, "raced")
        self.assertEqual(len(self.intake.list()), 1)
        self.assertEqual(ingest(self.ctx, "retry")["id"], "BUG-0045")


if __name__ == "__main__":
    unittest.main()
