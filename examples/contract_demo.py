"""Run a self-contained gate demonstration in an isolated local directory.

Approval records are demonstration records; this script must never be used to
approve production contracts. The caller explicitly authorizes the demo run.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ember_harness import Harness, content_hash, draft, validate


def main():
    repo = Path(__file__).resolve().parents[1]
    folder = repo / ".harness" / "demos" / uuid.uuid4().hex[:10]
    data = folder / "files"
    data.mkdir(parents=True)
    h = Harness(folder / "state")
    now = datetime.now(timezone.utc)
    window = {"not_before": now.isoformat(), "not_after": (now + timedelta(hours=1)).isoformat()}
    message = "Hello from the approved Ember Courier contract!\n"
    glob = data.as_posix() + "/*.txt"
    scope = draft("ct-demo-scope-0001", "demo-planner", "Demonstrate one local text-file write; no network or spending.", role="scope")
    scope["limits"] = {"spend_usd": 0, "max_calls": 3, "time_window": window}
    scope["allowed_paths"] = {"read": [], "write": [glob]}
    scope["allowed_actions"] = [{"action_id": "write_greeting", "tool": "fs.write", "class": "write",
                                 "args_constraints": {"path": {"path_within": glob}, "content": {"equals": message}},
                                 "allow_no_evidence": False}]
    scope["required_evidence"] = {"write_greeting": [{"kind": "file_hash", "params": {
        "path": (data / "hello.txt").as_posix(), "sha256": sha256(message.encode("utf-8")).hexdigest()}}]}
    worker = deepcopy(scope)
    worker.update(id="ct-demo-worker-0001", agent="demo-writer")
    worker["extensions"]["orchestration"]["role"] = "coding"
    worker["goal"] = "Write the approved greeting to a text file in this isolated demo directory."
    worker["intent_text"] = worker["goal"]
    for name, contract in (("scope", scope), ("worker", worker)):
        validate(contract)
        (folder / f"{name}-draft.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")
        h.save_draft(contract)

    target = data / "hello.txt"
    action = {"agent": "demo-writer", "contract_id": worker["id"], "tool": "fs.write",
              "args": {"path": target.as_posix(), "content": message},
              "paths": {"read": [], "write": [target.as_posix()]}, "spend": 0}
    rows = []

    def check(label, request, expected):
        result = h.check(request)
        assert result["decision"] == expected, result
        rows.append((label, result["decision"], result["reason"], result["audit_seq"]))
        print(f"{label}: {result['decision'].upper()} ({result['reason']})")
        return result

    print(f"Demo directory: {folder}")
    print("Created and validated scope and worker drafts.")
    check("Before approval", action, "deny")
    # This run was explicitly requested by the user. Record that exact request,
    # with demo-only context; do not invent quoted approval wording.
    quote = "Run it and show me a working demo of creating a contract, approving it, and allowing or denying an action."
    approvals = []
    for contract, parent in ((scope, None), (worker, scope["id"])):
        reviewed = content_hash(contract)
        result = h.approve(contract["id"], 1, approver="johnathan", quote=quote,
                           expected_hash=reviewed, parent_id=parent)
        approvals.append({"id": contract["id"], "hash": result["contract"]["content_hash"], "seq": result["approval_seq"]})
        print(f"Approved demo contract {contract['id']} (audit #{result['approval_seq']})")
    allowed = check("Write inside approved directory", action, "allow")
    # Explicit tiny demo adapter. The gate itself never executes tools.
    target.write_bytes(message.encode("utf-8"))
    assert target.read_text(encoding="utf-8") == message
    print(f"Executed allowed write: {target}")
    evidence = [{"kind": "file_hash", "params": {"path": target.as_posix(), "sha256": sha256(message.encode("utf-8")).hexdigest()}}]
    verified = h.verify_evidence(worker["id"], "write_greeting", evidence, decision_seq=allowed["audit_seq"])
    assert verified["status"] == "complete"
    print(f"Expected file evidence: COMPLETE (audit #{verified['status_basis']})")
    target.write_text("Changed after verification\n", encoding="utf-8")
    changed = h.step_status(worker["id"], "write_greeting")
    assert changed["status"] == "incomplete"
    print(f"File changed after verification: INCOMPLETE (audit #{changed['status_basis']})")
    target.write_bytes(message.encode("utf-8"))
    restored = h.step_status(worker["id"], "write_greeting")
    assert restored["status"] == "complete"
    print(f"Expected file restored and rechecked: COMPLETE (audit #{restored['status_basis']})")
    outside = folder / "outside-scope.txt"
    denied = deepcopy(action)
    denied["args"]["path"] = outside.as_posix()
    denied["paths"]["write"] = [outside.as_posix()]
    check("Write outside approved directory", denied, "deny")
    assert not outside.exists()
    forbidden = deepcopy(action)
    forbidden.update(tool="network.post", args={}, paths={"read": [], "write": []})
    check("Attempt a network post", forbidden, "deny")
    audit = h.audit_verify()
    assert audit["ok"]
    print(f"Audit verified: {audit['entries']} entries, intact hash chain")
    lines = ["# Working contract demo", "", "This is an isolated demonstration, authorized by your request. All approvals apply only to these demo contracts.", "",
             "Created a scope contract and a worker contract. Both were validated, then approved against their exact reviewed hashes.", "",
             "| Action | Result | Gate reason | Audit entry |", "|---|---|---|---|"]
    lines.extend(f"| {label} | **{decision.upper()}** | `{reason}` | {seq} |" for label, decision, reason, seq in rows)
    lines += ["", "The allowed write was executed by the demo's small file-writing adapter. The denied write was not executed; its target file does not exist.", "",
              "| Evidence check | Step status | Audit entry |", "|---|---|---|",
              f"| File matches the approved SHA-256 | **COMPLETE** | {verified['status_basis']} |",
              f"| File modified, saved evidence rechecked | **INCOMPLETE** | {changed['status_basis']} |",
              f"| Expected file restored and rechecked | **COMPLETE** | {restored['status_basis']} |", "",
              f"Created file: [hello.txt](<{target.as_posix()}>)", "", "```text", message.rstrip(), "```", "",
              f"Audit: **verified**, {audit['entries']} entries.", "", f"Audit head: `{audit['head']}`", "",
              f"[Raw audit log](<{h.audit_path.as_posix()}>)", "", "Demo approvals:", ""]
    lines.extend(f"- `{a['id']}`: audit #{a['seq']}, content hash `{a['hash']}`" for a in approvals)
    report = folder / "DEMO.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report: {report}")


if __name__ == "__main__":
    main()
