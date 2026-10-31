"""Actual failed regressions demonstrating the per-bug circuit breaker.

All approval/owner-decision entries are fixtures for this requested local demo.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import json
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ember_harness import Harness, canonical, content_hash, draft
from ember_harness.attempts import Attempts
from ember_harness.staged_fix import run_test


CANDIDATES = ["def reward(value):\n    return value - 1\n", "def reward(value):\n    return value + 1\n",
              "def reward(value):\n    return 0\n", "def reward(value):\n    return value * 2\n", "def reward(value):\n    return value\n"]
TEST = '''from pathlib import Path
import runpy
import unittest
reward = runpy.run_path(str(Path(__file__).resolve().parents[1] / "src/reward.py"))["reward"]
class Regression(unittest.TestCase):
    def test_reward(self):
        for value in (0, 1, 5):
            with self.subTest(value=value):
                self.assertEqual(reward(value), value)
if __name__ == "__main__":
    unittest.main()
'''


def setup(folder=None):
    folder = Path(folder) if folder else Path(__file__).resolve().parents[1] / ".harness/demos" / ("attempts-" + uuid.uuid4().hex[:10])
    for name in ("src", "scripts", "bugs"):
        (folder / name).mkdir(parents=True, exist_ok=True)
    source, script, bug = folder / "src/reward.py", folder / "scripts/regression.py", folder / "bugs/BUG-0042.json"
    source.write_bytes(CANDIDATES[0].encode())
    script.write_bytes(TEST.encode())
    bug.write_bytes(canonical({"id": "BUG-0042", "severity": "S2", "expected": 5, "actual": 4}))
    h = Harness(folder / "state")
    now = datetime.now(timezone.utc)
    scope = draft("ct-attempt-scope-0001", "planner", "Demonstrate bounded local fix attempts and owner escalation.", role="scope")
    scope["approval_mode"] = "approve_all"
    scope["limits"] = {"max_calls": 40, "spend_usd": 0, "time_window": {"not_before": now.isoformat(), "not_after": (now + timedelta(hours=1)).isoformat()}}
    scope["allowed_paths"] = {"read": [(folder / "src").as_posix() + "/*.py", (folder / "scripts").as_posix() + "/*.py", (folder / "bugs").as_posix() + "/*.json"], "write": [(folder / "src").as_posix() + "/*.py"]}
    scope["allowed_actions"] = [
        {"action_id": "edit", "tool": "fs.write", "class": "write", "args_constraints": {"path": {"equals": source.as_posix()}, "content": {"one_of": CANDIDATES}}, "allow_no_evidence": True},
        {"action_id": "regression", "tool": "test.run", "class": "compute", "args_constraints": {"script": {"equals": script.as_posix()}}, "allow_no_evidence": True}]
    h.save_draft(scope)
    h.approve(scope["id"], 1, approver="johnathan", quote="Demo fixture approval", expected_hash=content_hash(scope))
    return {"folder": folder, "h": h, "scope": scope, "source": source, "script": script, "bug": bug}


def contract(context, number, code=None, bug_id="BUG-0042"):
    code = code or CANDIDATES[min(number - 1, len(CANDIDATES) - 1)]
    c = deepcopy(context["scope"])
    c.update(id=f"ct-fix-{bug_id[4:]}-{number:04d}", agent=f"fix-worker-{bug_id}-{number}")
    c["extensions"]["orchestration"]["role"] = "coding"
    c["extensions"]["triage"] = {"bug_id": bug_id}
    bug_path = context["folder"] / "bugs" / (bug_id + ".json")
    if not bug_path.exists():
        bug_path.write_bytes(canonical({"id": bug_id, "severity": "S2"}))
    c["inputs"] = [{"name": name, "path": path.as_posix(), "sha256": sha256(path.read_bytes()).hexdigest()}
                   for name, path in (("regression", context["script"]), ("bug_snapshot", bug_path))]
    c["allowed_actions"][0]["args_constraints"]["content"] = {"equals": code}
    c["required_evidence"] = {"edit": [{"kind": "file_hash", "params": {"path": context["source"].as_posix(), "sha256": sha256(code.encode()).hexdigest()}}]}
    return c


def approve(context, c):
    h = context["h"]
    h.save_draft(c)
    result = h.approve(c["id"], c["version"], approver="johnathan", quote="Demo fixture contract approval", expected_hash=content_hash(c), parent_id=context["scope"]["id"])
    assert h.verify_inputs(c["id"])
    return result


def exercise(context, c):
    h, source = context["h"], context["source"]
    code = c["allowed_actions"][0]["args_constraints"]["content"]["equals"]
    action = {"agent": c["agent"], "contract_id": c["id"], "tool": "fs.write", "args": {"path": source.as_posix(), "content": code}, "paths": {"read": [], "write": [source.as_posix()]}, "spend": 0}
    decision = h.check(action)
    assert decision["decision"] == "allow", decision
    source.write_bytes(code.encode())
    evidence = h.verify_evidence(c["id"], "edit", [{"kind": "file_hash", "params": {"path": source.as_posix(), "sha256": sha256(code.encode()).hexdigest()}}], decision_seq=decision["audit_seq"])
    assert evidence["status"] == "complete"
    run = run_test(h, {"agent": c["agent"], "contract_id": c["id"], "tool": "test.run", "args": {"script": context["script"].as_posix()}, "paths": {"read": [source.as_posix(), context["script"].as_posix()], "write": []}, "spend": 0})
    return run, action


def main():
    ctx = setup()
    h, attempts, rows = ctx["h"], Attempts(ctx["h"]), []

    def show(label, result):
        rows.append((label, result))
        print(f"{label}: {result}")

    for number in range(1, 4):
        c = contract(ctx, number)
        approve(ctx, c)
        if number == 1:
            amended = h.amend(c["id"], {"reason": "Clarify this attempt's goal", "round": 1, "source": {"kind": "review", "id": "DEMO-1"}, "changes": [{"op": "replace", "pointer": "/goal", "value": "Test this one candidate for the same bug."}]}, proposed_by=c["agent"])
            c = amended["contract"]
            h.approve(c["id"], 2, approver="johnathan", quote="Demo fixture amendment approval", expected_hash=content_hash(c))
            assert h.verify_inputs(c["id"])
            assert attempts.status("BUG-0042")["attempts_started"] == 1
            show("Amend attempt 1 from v1 to v2", "still attempt 1; counter unchanged")
        run, last_action = exercise(ctx, c)
        assert run["returncode"] == 1 and "AssertionError" in run["stderr"]
        state = attempts.fail(c["id"], execution_seq=run["execution_seq"], reason=f"Candidate {number} fails the unchanged regression")
        show(f"Attempt {number}: real regression failure", f"failed attempts={state['failed_attempts']}; bug={state['status']}")
    fourth = contract(ctx, 4)
    try:
        approve(ctx, fourth)
        raise AssertionError("fourth attempt must be blocked")
    except ValueError as error:
        assert "awaiting_decision" in str(error)
        show("Approve attempt 4 under approve_all", "REFUSED — awaiting_decision")
    ctx["h"] = h = Harness(h.root)
    attempts = Attempts(h)
    assert attempts.status("BUG-0042")["failed_attempts"] == 3
    show("Restart harness", "three failures preserved from audit")
    assert h.check(last_action)["decision"] == "deny"
    show("Reuse a failed contract", "DENIED — attempt_failed")
    current = attempts.status("BUG-0042")
    try:
        attempts.decide("BUG-0042", choice="retry", expected_state_hash=current["state_hash"], approver="hack-lead", quote="Demo fixture AI request")
        raise AssertionError("agent cannot authorize escalation")
    except ValueError:
        show("Agent tries to authorize another attempt", "REFUSED — Johnathan's own decision required")
    stopped = attempts.decide("BUG-0042", choice="stop", expected_state_hash=current["state_hash"], approver="johnathan", quote="Demo fixture owner decision: stop this bug for review")
    assert stopped["status"] == "stopped"
    show("Record owner STOP fixture", "stopped; no attempt budget reset")
    retry = attempts.decide("BUG-0042", choice="retry", expected_state_hash=stopped["state_hash"], approver="johnathan", quote="Demo fixture owner decision: allow exactly one additional attempt")
    assert retry["status"] == "ready"
    approve(ctx, fourth)
    show("Record owner RETRY fixture and approve attempt 4", "ALLOWED — exactly one extra attempt")
    run, _ = exercise(ctx, fourth)
    final = attempts.fail(fourth["id"], execution_seq=run["execution_seq"], reason="The one owner-authorized retry also fails the regression")
    assert final["failed_attempts"] == 4 and final["status"] == "awaiting_decision"
    try:
        approve(ctx, contract(ctx, 5))
        raise AssertionError("one retry must not authorize a fifth attempt")
    except ValueError as error:
        assert "awaiting_decision" in str(error)
        show("Approve attempt 5", "REFUSED — fresh owner decision required")
    audit = h.audit_verify()
    show("Verify audit chain", f"PASS — {audit['entries']} entries")
    from ember_harness.reporting import write_attempt_report
    from ember_harness.contract_lock import verify
    lock = verify(h.root)
    assert lock["ok"], lock
    tracked_report = write_attempt_report(h, "BUG-0042")
    report = ctx["folder"] / "DEMO.md"
    lines = ["# Three-attempt limit and escalation", "",
             "This isolated demo uses actual Python assertion failures. Contract approvals and owner decisions are demo fixtures authorized by your request, not production permissions.", "",
             "| Check | Result |", "|---|---|"]
    lines += [f"| {label} | {result} |" for label, result in rows]
    lines += ["", "Final bug state: **awaiting_decision**, **4 failed attempts** including the one explicitly authorized extra attempt. No counter was reset.", "",
              f"[Audit-derived attempt history](<{tracked_report['path']}>)", "",
              f"[Audit log](<{h.audit_path.as_posix()}>) · [Regression script](<{ctx['script'].as_posix()}>)", "",
              f"Audit head: `{audit['head']}`", "", "No publishing, paid calls, network messages or engine edits occur."]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Report: " + str(report))
    return {**ctx, "final": final, "report": report}


if __name__ == "__main__":
    main()
