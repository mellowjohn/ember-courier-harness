"""Local finding intake, confirmed deduplication and routing demonstration."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import json
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ember_harness import Harness, canonical, content_hash, draft
from ember_harness.intake import Intake


def setup(folder=None, *, harness=None, approve=True):
    folder = Path(folder) if folder else Path(__file__).resolve().parents[1] / ".harness/demos" / ("intake-" + uuid.uuid4().hex[:10])
    inputs, data = folder / "inputs", folder / "triage"
    inputs.mkdir(parents=True)
    h = harness if harness is not None else Harness(folder / "state")
    evidence = inputs / "playtest.log"
    evidence.write_bytes(b"Delivery: expected five reward coins; observed four.\n")
    now = datetime.now(timezone.utc)
    scope = draft("ct-intake-scope-0001", "planner", "Normalize findings, confirm duplicates with QA and route locally.", role="scope")
    scope["limits"] = {"max_calls": 100, "spend_usd": 0, "time_window": {"not_before": now.isoformat(), "not_after": (now + timedelta(hours=1)).isoformat()}}
    scope["allowed_paths"] = {"read": [inputs.as_posix() + "/*"], "write": [(data / "bugs").as_posix() + "/BUG-*.json", (data / "evidence").as_posix() + "/*.bin"]}
    bugs, findings = (data / "bugs").as_posix() + "/BUG-*.json", inputs.as_posix() + "/*.json"
    note = {"pattern": "^[\\s\\S]{1,2000}$"}
    scope["allowed_actions"] = [
        {"action_id": "inspect", "tool": "triage.inspect", "class": "read", "args_constraints": {"path": {"path_within": findings}}, "allow_no_evidence": True},
        {"action_id": "ingest", "tool": "triage.ingest", "class": "write", "args_constraints": {"source": {"path_within": findings}, "dest": {"path_within": bugs}}, "allow_no_evidence": True},
        {"action_id": "duplicate", "tool": "triage.confirm_duplicate", "class": "write", "args_constraints": {"path": {"path_within": bugs}, "target": {"path_within": bugs}, "note": note}, "allow_no_evidence": True},
        {"action_id": "severity", "tool": "triage.review_severity", "class": "write", "args_constraints": {"path": {"path_within": bugs}, "severity": {"one_of": ["S0", "S1", "S2", "S3"]}, "demo_impact": {"one_of": [True, False]}, "note": note}, "allow_no_evidence": True}]
    scope["allowed_actions"].append({"action_id": "reopen", "tool": "triage.reopen", "class": "write", "args_constraints": {"path": {"path_within": bugs}, "reason": note}, "allow_no_evidence": True})
    intake, reviewer = deepcopy(scope), deepcopy(scope)
    intake.update(id="ct-intake-0001", agent="demo-intake")
    intake["extensions"]["orchestration"]["role"] = "triage"
    intake["allowed_actions"] = [a for a in intake["allowed_actions"] if a["action_id"] in ("inspect", "ingest")]
    reviewer.update(id="ct-intake-reviewer-0001", agent="demo-qa")
    reviewer["extensions"]["orchestration"]["role"] = "verifier"
    reviewer["extensions"]["triage"] = {"review_role": "QA"}
    reviewer["allowed_actions"] = [a for a in reviewer["allowed_actions"] if a["action_id"] in ("duplicate", "severity", "reopen")]
    reviewer["allowed_paths"]["write"] = [bugs]
    for c, parent in ((scope, None), (intake, scope["id"]), (reviewer, scope["id"])) if approve else ():
        h.save_draft(c)
        h.approve(c["id"], 1, approver="johnathan", quote="Demo fixture approval for local intake and QA review", expected_hash=content_hash(c), parent_id=parent)
    finding = {"source": "playtest", "build_id": "dev-42", "build_family": "demo-builds", "summary": "Delivery reward loses a coin",
               "area": "balance", "symptom_tag": "reward_loss", "steps": ["Deliver five coins", "Inspect reward"], "expected": "Five coins", "actual": "Four coins", "frequency": "always", "impact": "degraded",
               "evidence": [{"path": evidence.as_posix(), "sha256": sha256(evidence.read_bytes()).hexdigest()}]}
    return {"folder": folder, "inputs": inputs, "data": data, "h": h, "scope": scope, "contract": intake, "reviewer": reviewer, "intake": Intake(h, data), "finding": finding}


def ingest(ctx, name, finding=None, **kwargs):
    path = ctx["inputs"] / (name + ".json")
    path.write_bytes(canonical(finding if finding is not None else ctx["finding"]))
    return ctx["intake"].ingest(path, contract_id=ctx["contract"]["id"], **kwargs)["bugs"][0]


def main():
    ctx = setup()
    intake, rows = ctx["intake"], []

    def show(label, bug):
        detail = f"{bug['id']}: {bug['state']}, owner={bug['owner']}, severity={bug['severity'] or bug['severity_proposed'] + ' proposed'}"
        rows.append((label, detail))
        print(f"{label}: {detail}")

    first = ingest(ctx, "complete")
    assert first["state"] == "triaged" and first["owner"] == "Systems Designer"
    show("Complete playtest finding", first)
    partial = deepcopy(ctx["finding"])
    partial.update(summary="Editor import panel is blank", area="asset_import", symptom_tag="blank_panel")
    partial.pop("steps"); partial.pop("expected")
    incomplete = ingest(ctx, "incomplete", partial)
    assert incomplete["state"] == "needs_repro" and "steps" in incomplete["completeness"]["missing"]
    show("Incomplete finding returns to QA", incomplete)
    partial.update(steps=["Open the import panel"], expected="Visible import controls")
    completed = ingest(ctx, "completed", partial, bug_id=incomplete["id"], expected_hash=incomplete["record_hash"])
    assert completed["state"] == "triaged" and completed["owner"] == "Editor"
    show("Add missing repro details", completed)
    duplicate = ingest(ctx, "duplicate", {**ctx["finding"], "summary": "Delivery still awards one fewer coin"})
    assert duplicate["duplicate_candidates"] and duplicate["duplicate_of"] is None
    show("Matching fingerprint only proposes a duplicate", duplicate)
    merged = intake.confirm_duplicate(duplicate["id"], first["id"], contract_id=ctx["reviewer"]["id"], bug_hash=duplicate["record_hash"], target_hash=first["record_hash"], note="Automated demo QA fixture confirms the same reproduction and symptom")
    first = intake.get(first["id"])
    assert first["duplicate_count"] == 1 and intake.get(duplicate["id"])["duplicate_of"] == first["id"]
    show("QA confirmation preserves the oldest canonical bug", first)
    crash = deepcopy(ctx["finding"])
    crash.update(source="log", summary="Crash while loading demo", area="crash", subsystem="renderer", impact="crash", severity="S3", log_excerpt="2026-10-29T12:00:00Z crash at 0xDEADBEEF frame 42", stack_frames=["Renderer::Load at 0x1234:42"], error_code="ERR_100")
    crash.pop("steps")
    critical = ingest(ctx, "crash", crash)
    assert critical["severity_proposed"] == "S0" and critical["severity_review_required"]
    show("Crash cannot downgrade itself to S3", critical)
    critical = intake.review_severity(critical["id"], contract_id=ctx["reviewer"]["id"], expected_hash=critical["record_hash"], severity="S0", demo_impact=True, note="Demo QA fixture confirms a crash on the demo load path")["bugs"][0]
    assert critical["owner"] == "Engine" and not critical["route"]["code_fix_allowed"]
    show("QA confirms S0; engine pause remains", critical)
    comms = ingest(ctx, "community", {**ctx["finding"], "summary": "Community welcome message has a typo", "area": "messages", "symptom_tag": "welcome_typo", "impact": "cosmetic"})
    assert comms["owner"] == "Comms" and not comms["route"]["code_fix_allowed"]
    show("Non-code finding routes to Comms", comms)
    for blocked in (critical, comms):
        try:
            intake.snapshot(blocked["id"], "ct-fix-blocked-0001")
            raise AssertionError("blocked routes must not produce a code-fix snapshot")
        except ValueError:
            pass
    snapshot = intake.snapshot(duplicate["id"], "ct-fix-0001-0001")
    assert snapshot["id"] == first["id"]
    rows.append(("Snapshot requested through a duplicate alias", "canonical " + snapshot["id"] + "; frozen bytes ready for an approved fix contract"))
    from ember_harness.contract_lock import verify
    from ember_harness.reporting import write_intake_report
    result = verify(ctx["h"].root)
    assert result["ok"], result
    queue = write_intake_report(ctx["h"], ctx["data"])
    audit = ctx["h"].audit_verify()
    report = ctx["folder"] / "DEMO.md"
    lines = ["# Bug intake, deduplication and routing", "", "This isolated demo uses approved fixture contracts and a separate QA fixture identity. Findings are data; no message, post, paid call or engine edit occurs.", "",
             "| Case | Actual result |", "|---|---|"]
    lines += [f"| {label} | {detail} |" for label, detail in rows]
    lines += ["", f"Contract-lock: **PASS**. Audit chain: **PASS**, {audit['entries']} entries.", "",
              f"[Audit-backed bug queue](<{Path(queue['path']).as_posix()}>) · [Raw audit log](<{ctx['h'].audit_path.as_posix()}>)", "",
              "Duplicate confirmation and severity review are recorded QA attestations, not independently authenticated human judgments."]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Report: " + str(report))
    return {**ctx, "report": report}


if __name__ == "__main__":
    main()
