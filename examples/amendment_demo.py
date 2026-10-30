"""Isolated demo of amendment review, approval, evidence reuse and rollback.

Approval entries apply only to this explicitly requested demonstration.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ember_harness import Harness, canonical, content_hash, draft


def main():
    folder = Path(__file__).resolve().parents[1] / ".harness" / "demos" / ("amendments-" + uuid.uuid4().hex[:10])
    files = folder / "files"
    files.mkdir(parents=True)
    h = Harness(folder / "state")
    now = datetime.now(timezone.utc)
    glob = files.as_posix() + "/*.txt"
    target, message = files / "hello.txt", b"Hello from a versioned Ember Courier contract!\n"
    scope = draft("ct-amendment-scope-0001", "planner", "Demonstrate local amendments and forward rollback.", role="scope")
    scope["limits"] = {"max_calls": 8, "spend_usd": 0, "time_window": {"not_before": now.isoformat(), "not_after": (now + timedelta(hours=1)).isoformat()}}
    scope["allowed_paths"] = {"read": [], "write": [glob]}
    scope["allowed_actions"] = [{"action_id": "greeting", "tool": "fs.write", "class": "write", "args_constraints": {
        "path": {"path_within": glob}, "content": {"equals": message.decode()}}}]
    scope["required_evidence"] = {"greeting": [{"kind": "file_hash", "params": {"path": target.as_posix(), "sha256": sha256(message).hexdigest()}}]}
    worker = deepcopy(scope)
    worker.update(id="ct-amendment-worker-0001", agent="demo-writer")
    worker["extensions"]["orchestration"]["role"] = "coding"
    worker["limits"]["max_calls"] = 1
    quote = "Let's work on contract amendments and versioning next. Follow the architecture docs, test it, and show me a working demo."
    for contract, parent in ((scope, None), (worker, scope["id"])):
        h.save_draft(contract)
        h.approve(contract["id"], 1, approver="johnathan", quote=quote, expected_hash=content_hash(contract), parent_id=parent)
    action = {"agent": worker["agent"], "contract_id": worker["id"], "tool": "fs.write", "args": {"path": target.as_posix(), "content": message.decode()},
              "paths": {"read": [], "write": [target.as_posix()]}, "spend": 0}
    rows = []

    def show(label, outcome, detail):
        rows.append((label, outcome, detail))
        print(f"{label}: {outcome} ({detail})")

    def check(label, request, expected):
        result = h.check(request)
        assert result["decision"] == expected, result
        show(label, result["decision"].upper(), result["reason"])
        return result

    first = check("v1 first write", action, "allow")
    target.write_bytes(message)
    evidence = [{"kind": "file_hash", "params": {"path": target.as_posix(), "sha256": sha256(message).hexdigest()}}]
    assert h.verify_evidence(worker["id"], "greeting", evidence, decision_seq=first["audit_seq"])["status"] == "complete"
    check("v1 second write exceeds its one-call limit", action, "deny")
    proposal = {"reason": "Demo needs two attempts instead of one", "round": 1, "source": {"kind": "manual", "id": "DEMO-REVIEW-1"},
                "changes": [{"op": "replace", "pointer": "/limits/max_calls", "value": 2}]}
    amendment = h.amend(worker["id"], proposal, proposed_by="demo-writer")
    show("Compile amendment", "DRAFT v2", amendment["summary"]["warnings"][0])
    (folder / "v2-review.json").write_bytes(canonical(amendment))
    check("Pending v2 grants no extra calls", action, "deny")
    try:
        h.approve(worker["id"], 2, approver="johnathan", quote=quote, expected_hash=content_hash(amendment["contract"]))
        raise AssertionError("widening approval should fail without separate acknowledgement")
    except ValueError as error:
        assert "widening_ack_missing" in str(error)
        show("Approve v2 without widening acknowledgement", "REFUSED", "widening_ack_missing")
    ack = h.acknowledge_widening(worker["id"], 2, amendment["summary"]["widening_sha256"], approver="johnathan", quote=quote)
    show("Record separate demo widening acknowledgement", "RECORDED", f"audit #{ack['seq']}")
    approved = h.approve(worker["id"], 2, approver="johnathan", quote=quote, expected_hash=content_hash(amendment["contract"]))
    show("Approve amendment", "v2 APPROVED; v1 SUPERSEDED", f"audit #{approved['approval_seq']}")
    reused = h.carry_forward(worker["id"])
    assert reused["results"]["greeting"]["status"] == "complete"
    show("Recheck unchanged v1 evidence under v2", "COMPLETE", "carried forward without another tool call")
    check("Action pinned to superseded v1", {**action, "contract_version": 1}, "deny")
    check("Action under v2's fresh call budget", action, "allow")
    rollback = h.amend(worker["id"], {"reason": "Restore the original one-call limit", "round": 2,
                     "source": {"kind": "manual", "id": "DEMO-ROLLBACK-1"}, "rollback_to": 1}, proposed_by="demo-writer")
    assert not rollback["amendment_record"]["widening"]["items"]
    assert rollback["contract"]["version"] == 3
    h.approve(worker["id"], 3, approver="johnathan", quote=quote, expected_hash=content_hash(rollback["contract"]))
    show("Rollback to original terms", "v3 APPROVED", "new version; v1 and v2 stay superseded")
    check("v3 first write", action, "allow")
    check("v3 second write restores the one-call limit", action, "deny")
    versions, audit = h.history(worker["id"]), h.audit_verify()
    assert [v["status"] for v in versions] == ["superseded", "superseded", "approved"]
    show("Verify audit chain", "PASS", f"{audit['entries']} entries")
    lines = ["# Contract amendments: working demo", "",
             "This isolated demonstration uses demo-only approval records authorized by your request. No network or paid actions run.", "",
             "The worker starts with one allowed call. A proposed amendment raises the limit to two, requires a separate widening acknowledgement, and supersedes v1. Rollback creates v3 with the original one-call terms.", "",
             "| Demonstration | Result | Detail |", "|---|---|---|"]
    lines += [f"| {label} | **{outcome}** | {detail} |" for label, outcome, detail in rows]
    lines += ["", "| Version | Final status | Status basis |", "|---|---|---|"]
    lines += [f"| v{v['version']} | {v['status']} | audit #{v['status_basis']} |" for v in versions]
    lines += ["", f"[Computed v2 review](<{(folder / 'v2-review.json').as_posix()}>) · [Audit log](<{h.audit_path.as_posix()}>) · [Created file](<{target.as_posix()}>)", "",
              f"Audit head: `{audit['head']}`", "", "The displayed decisions and statuses come from this run's actual gate, amendment compiler, evidence verifier and audit log."]
    report = folder / "DEMO.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report: {report}")


if __name__ == "__main__":
    main()
