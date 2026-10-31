"""Human-readable round reports derived from verified audit entries."""
import json
from pathlib import Path

from .core import digest
from .contract_lock import verify
from .rounds import Rounds


def cell(value):
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def write_text_report(harness, path, lines):
    path = Path(path)
    resolved = path.resolve()
    if any(resolved.is_relative_to(harness.root / name) for name in ("contracts", "approvals", "audit", "evidence", "executions", "triage/reconciliations", "triage/fix_contracts", "muse_reviews", "agent-captures", "owner-review")) or resolved == harness.root / ".writer.lock":
        raise ValueError("report output cannot overwrite harness authority or evidence files")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path.resolve())


def write_intake_report(harness, root, output=None):
    from .intake import Intake
    bugs = Intake(harness, root).list()
    integrity = verify(harness.root)
    lines = ["# Bug intake and routing", "", f"Integrity: **{'PASS' if integrity['ok'] else 'FAIL'}**. Records: **{len(bugs)}**.", "",
             "This queue is reconstructed from audit records. Duplicate candidates are proposals; only a recorded QA review merges them. Review notes are self-reported attestations.", "",
             "| Bug | State | Severity | Owner | Code-fix policy | Duplicate candidates | Basis |", "|---|---|---|---|---|---|---|"]
    notes = []
    for bug in bugs:
        status = bug["state"] if integrity["ok"] else "claimed, unverified"
        severity = (bug["severity"] or bug["severity_proposed"]) + (" (QA reviewed)" if bug.get("severity_basis") == "qa_review" else " (review pending)" if bug["severity_review_required"] else " (proposed)")
        candidates = ", ".join(x["bug_id"] + " (" + x["reason"] + ")" for x in bug["duplicate_candidates"])
        policy = "use canonical " + bug["duplicate_of"] if bug["duplicate_of"] else "awaiting_fresh_triage" if bug["state"] == "reopened" else "needs_repro" if not bug["completeness"]["complete"] else "needs_severity_review" if bug["severity_review_required"] else bug["route"]["reason"]
        lines.append(f"| {bug['id']} | {status} | {cell(severity)} | {cell(bug['owner'])} | {cell(policy)} | {cell(candidates)} | {bug['status_basis']} |")
        if bug.get("review_provenance"):
            notes.append(f"- {bug['id']} review origin: {bug['review_provenance']['provider']} / {bug['review_provenance']['label']}; requires independent reproduction.")
        if bug["completeness"]["missing"]:
            notes.append(f"- {bug['id']} needs repro: {', '.join(bug['completeness']['missing'])}.")
        if bug["duplicate_of"]:
            notes.append(f"- {bug['id']} is a confirmed duplicate of **{bug['duplicate_of']}**.")
    if notes:
        lines += ["", *notes]
    if not integrity["ok"]:
        lines += ["", "Integrity errors:", ""] + ["- " + cell(e) for e in integrity["errors"]]
    return {"path": write_text_report(harness, output or harness.root / "triage/report/intake.md", lines), "bugs": len(bugs), "integrity_ok": integrity["ok"]}


def write_attempt_report(harness, bug_id, output=None):
    from .attempts import status as attempt_status
    entries = harness._entries()
    state = attempt_status(entries, bug_id)
    integrity = verify(harness.root)
    display = state["status"] if integrity["ok"] else "claimed, unverified"
    lines = [f"# {bug_id}: {display}", "", f"Attempt limit: **{state['attempt_limit']}**. Started: **{state['attempts_started']}**. Failed: **{state['failed_attempts']}**.", "",
             f"Status basis: audit **#{state['status_basis']}**. Integrity: **{'PASS' if integrity['ok'] else 'FAIL'}**.", "",
             "| Attempt | Original bug / number | Contract | Latest version | Outcome | Started | Outcome entry |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {a['number']} | {a.get('origin_bug_id', state['bug_id'])} / {a.get('origin_number', a['number'])} | {cell(a['contract_id'])} | {a['version']} | {a['status']} | {a['started_seq']} | {a['outcome_seq'] or 'pending'} |" for a in state["attempts"]]
    lines += ["", "## Owner decisions", "", "| Audit entry | Decision | Next attempt | Attribution | Note label |", "|---|---|---|---|---|"]
    for event in entries:
        if event["kind"] == "approval" and event.get("scope") == "attempt_escalation" and event.get("bug_id") in state.get("merged_bug_ids", [state["bug_id"]]):
            lines.append(f"| {event['seq']} | {event['choice']} | {event['next_attempt']} | recorded owner: {cell(event['actor'])} | self_reported |")
    reopening_events = [e for e in entries if e.get("operation") == "reopen" and e.get("bug_id") in state.get("merged_bug_ids", [state["bug_id"]])]
    if reopening_events:
        lines += ["", "## Reopening history", "", "| Reopened entry | Previous closure | QA identity | Recurrence reason |", "|---|---|---|---|"]
        for event in reopening_events:
            lines.append(f"| {event['seq']} | {event['closure_seq']} | {cell(event['agent'])} | {cell(event['reason'])} |")
        lines += ["", "Reopening retains successes and spent attempts. A fresh finding and snapshot are required before another fix; at the limit, a separate owner retry decision is required."]
    if state.get("merged_bug_ids"):
        lines += ["", "Reconciled family: " + ", ".join(state["merged_bug_ids"]),
                  "", "Owner-approved duplicate reconciliations (each cancels unused retry permissions):"]
        for event in entries:
            if event.get("scope") == "duplicate_reconciliation" and event["reconciliation"]["bugs"][0] in state["merged_bug_ids"]:
                lines.append(f"- Audit #{event['seq']}: reviewed plan `{event['plan_hash']}`; recorded owner {cell(event['actor'])} (self_reported).")
    lines += ["", "The count comes from the audit, across contract IDs, amendments and rounds. Retry permission grants exactly one new attempt; it does not erase failures or revive finished contracts.", "",
              f"Current decision-state hash: `{state['state_hash']}`", "",
              "Owner decisions are recorded through the trusted human-facing host. In demos they are explicit fixtures; the hash chain does not authenticate a person's identity."]
    if not integrity["ok"]:
        lines += ["", "Integrity errors:", ""] + ["- " + cell(error) for error in integrity["errors"]]
    path = output or harness.root / "triage" / "report" / (bug_id + "-attempts.md")
    return {"path": write_text_report(harness, path, lines), "bug_id": bug_id, "status": display, "status_basis": state["status_basis"], "integrity_ok": integrity["ok"]}


def write_round_report(harness, number, output=None):
    entries = harness._entries()  # A broken chain never produces a success report.
    state = Rounds(harness).status(number)
    integrity = verify(harness.root)
    status = state["status"] if integrity["ok"] else "claimed, unverified"
    lines = [f"# Round {number}: {status}", "", f"Status basis: audit **#{state['status_basis']}**. Integrity: **{'PASS' if integrity['ok'] else 'FAIL'}**.", "",
             "This report is derived from the audit log, not the editable round cache. Approvals record the trusted host's attribution; the log does not authenticate who typed a message.", "",
             "Checkpoint status is historical, as of its audit sequence. Use step-status for a fresh check of current file bytes.", "",
             "| Bug | Fix contract | Verifier contract | C1 reviewed | C2 verified |", "|---|---|---|---|---|"]
    for task in state["tasks"]:
        lines.append(f"| {cell(task['bug_id'])} | {cell(task['fix_contract_id'])} v{task['fix_version']} | {cell(task['verifier_contract_id'])} v{task['verifier_version']} | {task['checkpoints'].get('C1', 'pending')} | {task['checkpoints'].get('C2', 'pending')} |")
    lines += ["", "| Checkpoint | Audit entry | Recorded status |", "|---|---|---|"]
    for event in state["events"]:
        lines.append(f"| {event['detail']['checkpoint']} {cell(event.get('bug_id', ''))} | {event['seq']} | {cell(event['status'])} |")
    lines += ["", "## Approval provenance", "", "| Contract | Version | Approval entry | Attribution |", "|---|---|---|---|"]
    identities = {(t[k + '_contract_id'], t[k + '_version']) for t in state["tasks"] for k in ("fix", "verifier")}
    for event in entries:
        if event["kind"] == "approval" and event.get("scope") == "contract" and (event.get("contract_id"), event.get("contract_version")) in identities:
            lines.append(f"| {cell(event['contract_id'])} | {event['contract_version']} | {event['seq']} | approved by {cell(event['actor'])} |")
    low, high = state["events"][0]["seq"], state["events"][-1]["seq"]
    relevant = [e for e in entries if low <= e["seq"] <= high and (e.get("contract_id"), e.get("contract_version")) in identities]
    lines += ["", "## Action decisions", "", "| Audit entry | Tool | Outcome | Approval source | Reason |", "|---|---|---|---|---|"]
    for event in relevant:
        if event["kind"] != "decision":
            continue
        provenance = "contract permission"
        if event.get("resolved_by") == "approve_all":
            provenance = "auto-approved under approve_all"
        elif event.get("reason") == "one_time_approval_consumed":
            provenance = f"Johnathan action approval #{event['approval_ref']}"
        lines.append(f"| {event['seq']} | {cell(event['action']['tool'])} | {cell(event['decision'])} | {provenance} | {cell(event['reason'])} |")
    lines += ["", "## Evidence provenance", "", "| Audit entry | Kind | Check | Label |", "|---|---|---|---|"]
    for event in relevant:
        if event["kind"] != "evidence":
            continue
        ref = event["evidence_refs"][0]
        try:
            payload = json.loads((harness.root / "evidence" / (ref + ".json")).read_text(encoding="utf-8"))
            valid = digest(payload) == ref and isinstance(payload, dict) and isinstance(payload.get("items"), list)
        except (ValueError, OSError):
            payload, valid = {"items": []}, False
        if not valid:
            lines.append(f"| {event['seq']} | payload | failed integrity | unverified |")
        for item in payload.get("items", []) if isinstance(payload, dict) else []:
            label = "unverified" if not valid or item.get("result") != "pass" else ("self_reported" if item["kind"] in ("checklist", "reviewer_note", "url") else "verified")
            lines.append(f"| {event['seq']} | {cell(item['kind'])} | {cell(item['result'])} | {label} |")
    close = next((e for e in reversed(state["events"]) if e["detail"]["checkpoint"] == "C3"), None)
    if close:
        lines += ["", f"Push decision: **{close['push_decision']}**. Next round: {', '.join(close['next_round']) or 'no bugs queued'}.", "",
                  f"Audit head before C3: `{close['audit_head_before_close']}`"]
    from .attempts import status as attempt_status
    lines += ["", "## Fix attempt limits", "", "| Bug | Attempts started | Failed attempts | State at round checkpoint |", "|---|---|---|---|"]
    for task in state["tasks"]:
        attempt = attempt_status(entries[:high], task["bug_id"])
        lines.append(f"| {task['bug_id']} | {attempt['attempts_started']} | {attempt['failed_attempts']} | {attempt['status']} |")
    if not integrity["ok"]:
        lines += ["", "Integrity errors:", ""] + ["- " + cell(error) for error in integrity["errors"]]
    lines += ["", "The reviewer is an automated structural checker under a distinct read-only fixture identity. Self-reported reviewer notes are recorded attestations, not independent human or AI peer review.", ""]
    path = Path(output) if output else harness.root / "triage" / "report" / f"round-{number}.md"
    return {"path": write_text_report(harness, path, lines), "round": number, "status": status, "status_basis": state["status_basis"], "integrity_ok": integrity["ok"]}
