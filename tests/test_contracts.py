"""Mechanical acceptance tests; approval fixtures simulate the trusted host.

No fixture is a real approval from Johnathan and no external tool is executed.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import ValidationError
from ember_harness import Harness, canonical, content_hash, draft, validate
from ember_harness.core import matches, subset


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.data = self.base / "data"
        self.data.mkdir()
        self.now = datetime(2026, 10, 29, 16, tzinfo=timezone.utc)
        self.h = Harness(self.base / "state", clock=lambda: self.now)
        self.scope = self.make("ct-scope-0001", "scope-agent", "scope")
        self.scope["approval_mode"] = "approve_all"
        self.scope["limits"]["max_calls"] = 100
        self.approve(self.scope)
        self.contract = self.make("ct-coding-0001", "worker", "coding")

    def make(self, cid, agent, role):
        c = draft(cid, agent, "Test the local contract gate", role=role)
        glob = self.data.as_posix() + "/*.txt"
        c["allowed_paths"] = {"read": [glob], "write": [glob]}
        c["allowed_actions"] = [
            {"action_id": "read", "tool": "fs.read", "class": "read", "args_constraints": {"path": {"path_within": glob}}, "allow_no_evidence": True},
            {"action_id": "write", "tool": "fs.write", "class": "write", "args_constraints": {"path": {"path_within": glob}, "content": {"pattern": "^.{0,100}$"}}, "allow_no_evidence": True},
            {"action_id": "pr", "tool": "git.open_pr", "class": "push", "args_constraints": {"branch": {"equals": "contract/test"}, "base": {"equals": "main"}, "force": {"equals": False}, "commit": {"pattern": "^[0-9a-f]{40}$"}}, "allow_no_evidence": True},
            {"action_id": "accept", "tool": "asset.accept", "class": "asset_acceptance", "args_constraints": {"path": {"path_within": glob}, "sha256": {"pattern": "^[0-9a-f]{64}$"}}, "allow_no_evidence": True},
            {"action_id": "close", "tool": "triage.close", "class": "bug_close", "args_constraints": {"bug_id": {"equals": "BUG-0001"}, "severity": {"one_of": ["S0", "S1", "S2", "S3"]}}, "allow_no_evidence": True},
        ]
        return c

    def approve(self, c, **extra):
        self.h.save_draft(c)
        return self.h.approve(c["id"], c["version"], approver="johnathan", quote="Fixture approval only",
                              expected_hash=content_hash(c), parent_id=None if c is self.scope else self.scope["id"], **extra)

    def ready(self):
        self.contract["allowed_actions"] = [a for a in self.contract["allowed_actions"] if a["tool"] != "git.open_pr"]
        return self.approve(self.contract)

    def action(self, tool="fs.read", args=None):
        return {"agent": "worker", "tool": tool, "args": args if args is not None else {"path": (self.data / "a.txt").as_posix()},
                "paths": {"read": [], "write": []}, "spend": 0, "contract_id": self.contract["id"]}

    def decision(self, a):
        return self.h.check(a)["decision"]

    def test_CT01_CT02_no_contract_and_draft(self):
        self.assertEqual(self.decision(self.action()), "deny")
        self.h.save_draft(self.contract)
        self.assertEqual(self.decision(self.action()), "deny")

    def test_allow_and_audit(self):
        self.ready()
        self.assertEqual(self.decision(self.action()), "allow")
        self.assertTrue(self.h.audit_verify()["ok"])

    def test_CT03_tamper_content_and_forged_status(self):
        self.ready()
        path = self.h._path(self.contract["id"], 1)
        c = json.loads(path.read_text())
        c["extensions"]["recon"] = {"network_hosts": ["example.com"]}
        path.write_bytes(canonical(c))
        self.assertEqual(self.decision(self.action()), "deny")

    def test_CT04_extra_args_wrong_types_and_CT05_undeclared_paths(self):
        self.ready()
        for args in ({"path": (self.base / "secret.txt").as_posix()},
                     {"path": (self.data / "a.txt").as_posix(), "surprise": True}, {"path": 4}):
            with self.subTest(args=args):
                self.assertEqual(self.decision(self.action(args=args)), "deny")
        a = self.action()
        a["paths"]["write"] = [(self.base / "secret.txt").as_posix()]
        self.assertEqual(self.decision(a), "deny")

    def test_CT05_traversal_and_nested_paths(self):
        self.ready()
        for path in (self.data / ".." / "secret.txt", self.data / "nested" / "a.txt"):
            self.assertEqual(self.decision(self.action(args={"path": path.as_posix()})), "deny")

    def test_CT05_symlink_escape(self):
        target = self.base / "secret.txt"
        target.write_text("secret")
        try:
            (self.data / "link.txt").symlink_to(target)
        except OSError:
            self.skipTest("Windows requires symlink privilege; traversal and undeclared-path checks still run")
        self.ready()
        self.assertEqual(self.decision(self.action(args={"path": (self.data / "link.txt").as_posix()})), "deny")

    def test_CT06_forbidden_wins(self):
        self.contract["forbidden_actions"].append({"tool": "fs.read"})
        self.ready()
        self.assertEqual(self.decision(self.action()), "deny")

    def test_CT07_CT50_baseline_and_spend(self):
        self.contract["approval_mode"] = "approve_all"
        self.ready()
        for tool in ("network.post", "publish.x", "submit.x", "deploy.x", "payment.pay", "fs.delete", "git.push", "git.merge_pr", "unknown.tool"):
            self.assertEqual(self.decision(self.action(tool, {})), "deny")
        for spend in (0.05, -1, float("nan"), float("inf"), True):
            a = self.action()
            a["spend"] = spend
            self.assertEqual(self.decision(a), "deny")

    def test_CT09_limits_survive_restart_and_denies_do_not_count(self):
        self.contract["limits"]["max_calls"] = 1
        self.ready()
        self.assertEqual(self.decision(self.action("unknown.tool", {})), "deny")
        self.assertEqual(self.decision(self.action()), "allow")
        self.h = Harness(self.base / "state", clock=lambda: self.now)
        self.assertEqual(self.decision(self.action()), "deny")

    def test_CT09_window_before_and_after(self):
        self.ready()
        self.now -= timedelta(seconds=1)
        self.assertEqual(self.decision(self.action()), "deny")
        self.now += timedelta(hours=5)
        self.assertEqual(self.decision(self.action()), "deny")

    def test_CT10_chain_corruption_fails_closed(self):
        self.ready()
        self.h.audit_path.write_text(self.h.audit_path.read_text().replace('"scope"', '"spoof"', 1))
        with self.assertRaises(ValueError):
            self.h.audit_verify()
        self.assertEqual(self.decision(self.action()), "deny")

    def test_CT12_audit_failure_and_concurrent_writer(self):
        self.ready()
        with patch.object(self.h, "_append", side_effect=OSError("disk full")):
            self.assertEqual(self.decision(self.action()), "deny")
        with self.h._lock():
            self.assertEqual(self.decision(self.action()), "deny")

    def test_CT13_CT14_selection_and_agent_identity(self):
        self.ready()
        second = deepcopy(self.contract)
        second["id"] = "ct-coding-0002"
        self.approve(second)
        a = self.action()
        del a["contract_id"]
        self.assertEqual(self.h.check(a)["reason"], "contract_id_required")
        a = self.action()
        a["agent"] = "impostor"
        self.assertEqual(self.decision(a), "deny")

    def test_CT17_schema_and_intrinsic_class(self):
        for mutate in (lambda c: c["requires_approval"].remove("push"),
                       lambda c: c.update(extra=True),
                       lambda c: c["limits"].update(max_images=3),
                       lambda c: c["allowed_actions"][0].update(**{"class": "compute"}),
                       lambda c: c["allowed_paths"].update(write=["relative/*"]),
                       lambda c: c["required_evidence"].update(unknown=[])):
            c = deepcopy(self.contract)
            mutate(c)
            with self.assertRaises((ValueError, ValidationError)):
                validate(c)

    def test_CT21_CT22_inputs_and_late_binding(self):
        path = self.data / "a.txt"
        path.write_text("original")
        self.contract["inputs"] = [{"name": "source", "path": path.as_posix(), "sha256": sha256(b"original").hexdigest()}]
        self.ready()
        self.assertEqual(self.h.check(self.action())["reason"], "inputs_unverified")
        self.assertTrue(self.h.verify_inputs(self.contract["id"]))
        self.assertEqual(self.decision(self.action()), "allow")
        path.write_text("changed")
        self.assertFalse(self.h.verify_inputs(self.contract["id"]))
        self.assertEqual(self.decision(self.action()), "deny")

    def test_CT30_one_time_approval_exact_and_consumed(self):
        self.ready()
        a = self.action("triage.close", {"bug_id": "BUG-0001", "severity": "S1"})
        self.assertEqual(self.decision(a), "needs_approval")
        self.h.approve_action(a, approver="johnathan", quote="Fixture only")
        other = deepcopy(a)
        other["args"]["severity"] = "S0"
        self.assertEqual(self.decision(other), "needs_approval")
        self.assertEqual(self.decision(a), "allow")
        self.assertEqual(self.decision(a), "needs_approval")

    def test_CT46_IT18_scope_required_and_subset(self):
        h = Harness(self.base / "no-scope")
        h.save_draft(self.contract)
        with self.assertRaisesRegex(ValueError, "scope"):
            h.approve(self.contract["id"], 1, approver="johnathan", quote="Fixture", expected_hash=content_hash(self.contract))
        self.contract["limits"]["max_calls"] = 101
        with self.assertRaisesRegex(ValueError, "exceeds scope"):
            self.ready()

    def test_CT47_parent_revocation_and_own_revocation(self):
        self.ready()
        self.h.revoke(self.scope["id"], approver="johnathan", reason="fixture")
        self.assertEqual(self.decision(self.action()), "deny")

    def test_CT50_CT55_auto_approval_exceptions(self):
        self.contract["approval_mode"] = "approve_all"
        self.ready()
        for severity in ("S0", "S1"):
            self.assertEqual(self.decision(self.action("triage.close", {"bug_id": "BUG-0001", "severity": severity})), "needs_approval")
        a = self.action("triage.close", {"bug_id": "BUG-0001", "severity": "S2"})
        self.assertEqual(self.h.check(a)["reason"], "approve_all")
        self.assertEqual(self.decision(self.action("asset.accept", {"path": (self.data / "a.txt").as_posix(), "sha256": "0" * 64})), "needs_approval")
        self.assertTrue(any(e.get("scope") == "auto_resolution" for e in self.h._entries()))

    def test_review_hash_binding_and_human_required(self):
        self.h.save_draft(self.contract)
        with self.assertRaises(ValueError):
            self.h.approve(self.contract["id"], 1, approver="worker", quote="yes", expected_hash=content_hash(self.contract))
        with self.assertRaises(ValueError):
            self.h.approve(self.contract["id"], 1, approver="johnathan", quote="yes", expected_hash="0" * 64)

    def test_CT51_amendment_widening_and_terminal_versions(self):
        result = self.ready()
        amendment = self.h.amend(self.contract["id"], {"reason": "Change approval mode", "round": 1,
                    "source": {"kind": "manual", "id": "test"}, "changes": [{"op": "replace", "pointer": "/approval_mode", "value": "approve_all"}]}, proposed_by="worker")
        c = amendment["contract"]
        kwargs = dict(approver="johnathan", quote="fixture", expected_hash=content_hash(c), parent_id=self.scope["id"])
        with self.assertRaisesRegex(ValueError, "widening"):
            self.h.approve(c["id"], 2, **kwargs)
        self.h.acknowledge_widening(c["id"], 2, amendment["summary"]["widening_sha256"], approver="johnathan", quote="Fixture widening acknowledgement")
        self.h.approve(c["id"], 2, **kwargs)
        a = self.action()
        a["contract_version"] = 1
        self.assertEqual(self.h.check(a)["reason"], "contract_superseded")
        with self.assertRaises(ValueError):
            self.h.save_draft(self.contract)

    def test_CT34_supersession_voids_unconsumed_one_time_approval(self):
        self.ready()
        action = self.action("triage.close", {"bug_id": "BUG-0001", "severity": "S1"})
        self.assertEqual(self.decision(action), "needs_approval")
        self.h.approve_action(action, approver="johnathan", quote="Fixture action approval")
        result = self.h.amend(self.contract["id"], {"reason": "Clarify completion", "round": 1,
                    "source": {"kind": "review", "id": "review-1"}, "changes": [{"op": "replace", "pointer": "/goal", "value": "Updated completion description"}]}, proposed_by="worker")
        self.h.approve(self.contract["id"], 2, approver="johnathan", quote="Fixture amendment approval", expected_hash=content_hash(result["contract"]))
        self.assertEqual(self.decision(action), "needs_approval")

    def test_canonical_unicode_and_hash_exclusions(self):
        a = {"b": "火", "a": 1}
        self.assertEqual(canonical(a), canonical({"a": 1, "b": "火"}))
        c = deepcopy(self.contract)
        c["status"] = "revoked"
        self.assertEqual(content_hash(c), content_hash(self.contract))
        c["approval_mode"] = "approve_all"
        self.assertNotEqual(content_hash(c), content_hash(self.contract))

    def test_glob_dialect(self):
        self.assertTrue(matches("/a/x.txt", "/a/*.txt"))
        self.assertFalse(matches("/a/b/x.txt", "/a/*.txt"))
        self.assertTrue(matches("/a/x.txt", "/a/**/*.txt"))
        self.assertTrue(matches("/a/b/x.txt", "/a/**/*.txt"))
        self.assertFalse(matches("/a/X.TXT", "/a/*.txt"))
        with self.assertRaises(ValueError):
            matches("/a/b", "/a/{b,c}")

    def test_CT52_CT53_PR_modes_and_constraints(self):
        self.approve(self.contract)
        a = self.action("git.open_pr", {"branch": "contract/test", "base": "main", "force": False, "commit": "a" * 40})
        self.assertEqual(self.decision(a), "needs_approval")
        self.h.approve_action(a, approver="johnathan", quote="Fixture only")
        self.assertEqual(self.decision(a), "allow")
        self.assertEqual(self.decision(a), "needs_approval")
        for key, value in (("branch", "other"), ("base", "other"), ("force", True), ("force", 0)):
            other = deepcopy(a)
            other["args"][key] = value
            self.assertEqual(self.decision(other), "deny")
        c = deepcopy(self.contract)
        c.update(id="ct-coding-0002", approval_mode="approve_all")
        self.approve(c)
        a["contract_id"] = c["id"]
        self.assertEqual(self.h.check(a)["reason"], "approve_all")

    def test_CT54_pipeline_PR_rejected(self):
        self.contract["extensions"]["orchestration"]["role"] = "asset-step"
        with self.assertRaisesRegex(ValueError, "only coding"):
            self.approve(self.contract)

    def test_pending_draft_never_grants_authority(self):
        self.ready()
        successor = deepcopy(self.contract)
        successor.update(version=2, approval_mode="approve_all")
        self.h.save_draft(successor)
        a = self.action("triage.close", {"bug_id": "BUG-0001", "severity": "S2"})
        self.assertEqual(self.decision(a), "needs_approval")

    def test_CT20_overwrite_integrity(self):
        from ember_harness.core import constraints_ok
        path = self.data / "a.txt"
        rule = {"dest": {"no_overwrite_unless_same_hash": True}}
        args = {"dest": path.as_posix()}
        self.assertTrue(constraints_ok(args, rule, True))
        path.write_bytes(b"content")
        self.assertFalse(constraints_ok(args, rule, True))
        args["expected_sha256"] = sha256(b"content").hexdigest()
        self.assertTrue(constraints_ok(args, rule, True))

    def test_schema_is_valid_and_source_extensions_unchanged(self):
        from jsonschema import Draft202012Validator
        from ember_harness.core import SCHEMA
        Draft202012Validator.check_schema(SCHEMA)
        ext = {"pipeline": {"nested": {"untouched": [1, "火"]}}}
        c = draft("ct-asset-0001", "worker", "Intent", role="asset-step", extensions=ext)
        self.assertEqual(c["extensions"]["pipeline"], ext["pipeline"])
        c["extensions"]["pipeline"]["nested"]["untouched"].append(2)
        self.assertEqual(ext["pipeline"]["nested"]["untouched"], [1, "火"])

    def test_late_bound_inputs_record_actual_bytes(self):
        path = self.data / "a.txt"
        path.write_bytes(b"bound at start")
        self.contract["inputs"] = [{"name": "chained", "path": path.as_posix(), "sha256": None, "late_bind": True}]
        self.ready()
        self.assertEqual(self.decision(self.action()), "deny")
        self.assertTrue(self.h.verify_inputs(self.contract["id"]))
        record = self.h._entries()[-1]
        self.assertEqual(record["kind"], "input_check")
        self.assertEqual(record["late_bound"]["chained"], sha256(b"bound at start").hexdigest())
        self.assertEqual(self.decision(self.action()), "allow")

    def test_cli_draft_review_save_and_check(self):
        import contextlib
        import io
        from ember_harness.__main__ import main
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["draft", "ct-cli-0001", "cli-agent", "Intent", "--role", "scope"]), 0)
        c = json.loads(output.getvalue())
        path = self.base / "cli.json"
        path.write_bytes(canonical(c))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["review", str(path)]), 0)
        self.assertEqual(json.loads(output.getvalue())["reviewed_hash"], content_hash(c))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--store", str(self.base / "cli-store"), "save", str(path)]), 0)
        action = self.base / "action.json"
        action.write_bytes(canonical(self.action()))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--store", str(self.base / "cli-store"), "check", str(action)]), 1)


if __name__ == "__main__":
    unittest.main()
