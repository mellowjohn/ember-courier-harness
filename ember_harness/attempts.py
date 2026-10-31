"""Per-bug fix attempts and owner escalation, derived only from the audit."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re

from .core import canonical, digest, normal, constraints_ok, content_hash

LIMIT = 3


def snapshot(state):
    running = next((a for a in state["attempts"] if a["status"] == "running"), None)
    if state["stopped"]:
        status = "stopped"
    elif state["attempts"] and state["attempts"][-1]["status"] == "succeeded" and state["attempts"][-1]["outcome_seq"] > state.get("reopened_seq", 0):
        status = "closed"
    elif running:
        status = "in_progress"
    elif len(state["attempts"]) >= LIMIT and state["retry_ref"] is None:
        status = "awaiting_decision"
    else:
        status = "ready"
    result = {"bug_id": state["bug_id"], "status": status, "attempt_limit": LIMIT,
              "attempts_started": len(state["attempts"]), "failed_attempts": sum(a["status"] == "failed" for a in state["attempts"]),
              "attempts": deepcopy(state["attempts"]), "status_basis": state["basis"],
              "retry_approval_ref": state["retry_ref"], "next_attempt": len(state["attempts"]) + 1}
    if state.get("reopened_seq"):
        result["last_reopened_seq"] = state["reopened_seq"]
    if state.get("members"):
        result["merged_bug_ids"] = sorted(state["members"])
    result["state_hash"] = digest(result)
    return result


def status(entries, bug_id):
    """Replay all ledgers chronologically so merges preserve historical decision hashes."""
    if not isinstance(bug_id, str) or re.fullmatch(r"BUG-[0-9]+", bug_id) is None:
        raise ValueError("canonical bug ID required")
    states, aliases, by_id = {}, {}, {}
    def resolve(identity):
        while identity in aliases:
            identity = aliases[identity]
        return identity
    def get(identity):
        identity = resolve(identity)
        return states.setdefault(identity, {"bug_id": identity, "attempts": [], "basis": None, "retry_ref": None, "stopped": False})
    for event in entries:
        if event.get("scope") == "duplicate_reconciliation":
            merge = event["reconciliation"]
            a, b = (get(x) for x in merge["bugs"])
            if a is b or event.get("actor") != "johnathan" or event.get("actor_type") != "human" or not event.get("quote", "").strip():
                raise ValueError("invalid owner reconciliation")
            if [snapshot(x)["state_hash"] for x in (a, b)] != merge["state_hashes"]:
                raise ValueError("stale reconciliation attempt history")
            if any(snapshot(st)["status"] in ("in_progress", "closed") for st in (a, b)):
                raise ValueError("running or closed attempts cannot be reconciled")
            for st in (a, b):
                for item in st["attempts"]:
                    item.setdefault("origin_bug_id", st["bug_id"])
                    item.setdefault("origin_number", item["number"])
            a["attempts"] = sorted(a["attempts"] + b["attempts"], key=lambda x: x["started_seq"])
            for number, item in enumerate(a["attempts"], 1):
                item["number"] = number
            a.update(basis=event["seq"], retry_ref=None, stopped=a["stopped"] or b["stopped"],
                     members=set(a.get("members", [a["bug_id"]])) | set(b.get("members", [b["bug_id"]])))
            reopened = max(a.get("reopened_seq", 0), b.get("reopened_seq", 0))
            if reopened:
                a["reopened_seq"] = reopened
            aliases[b["bug_id"]] = a["bug_id"]
            continue
        binding = event.get("bug_attempt")
        identity = binding["bug_id"] if binding else event.get("bug_id")
        state = get(identity) if identity else None
        if event.get("operation") == "reopen" and event.get("detail", {}).get("scope") == "bug_intake":
            before = snapshot(state)
            if before["status"] != "closed" or before["state_hash"] != event["expected_state_hash"] or state["attempts"][-1]["outcome_seq"] != event["closure_seq"]:
                raise ValueError("reopening requires the current closed attempt state")
            state.update(reopened_seq=event["seq"], basis=event["seq"], retry_ref=None)
        elif event["kind"] == "approval" and event.get("scope") == "contract" and binding:
            cid = event["contract_id"]
            if cid in by_id:
                item = by_id[cid]
                if item not in state["attempts"] or item["status"] != "running" or binding["number"] != item["number"]:
                    raise ValueError("amendment cannot revive or renumber a finished attempt")
                item["version"] = event["contract_version"]
            else:
                before = snapshot(state)
                if before["status"] != "ready" or binding["number"] != before["next_attempt"]:
                    raise ValueError("attempt allocation violates the per-bug limit or sequential order")
                if binding["number"] > LIMIT:
                    if not state["retry_ref"] or binding.get("escalation_ref") != state["retry_ref"]:
                        raise ValueError("extra attempt lacks its own owner decision")
                    state["retry_ref"] = None
                item = {"number": binding["number"], "contract_id": cid, "version": event["contract_version"],
                        "status": "running", "started_seq": event["seq"], "outcome_seq": None}
                state["attempts"].append(item)
                by_id[cid] = item
            state["basis"] = event["seq"]
        elif event["kind"] == "state_transition" and event.get("detail", {}).get("scope") == "bug_attempt":
            item = by_id.get(event["contract_id"])
            if not item or item not in state["attempts"] or item["status"] != "running" or event["attempt_number"] != item.get("origin_number", item["number"]):
                raise ValueError("duplicate or unbound attempt outcome")
            item.update(status="failed", outcome_seq=event["seq"])
            state["basis"] = event["seq"]
        elif event["kind"] == "state_transition" and event.get("status") == "closed" and event.get("fix_contract_id") in by_id:
            item = by_id[event["fix_contract_id"]]
            if item not in state["attempts"] or item["status"] != "running":
                raise ValueError("finished or unbound attempt cannot close a bug")
            item.update(status="succeeded", outcome_seq=event["seq"])
            state["basis"] = event["seq"]
        elif event["kind"] == "revocation" or event.get("revoked_children"):
            ids = [event["contract_id"]] if event["kind"] == "revocation" else []
            ids += [c["id"] for c in event.get("revoked_children", [])]
            for cid in ids:
                if cid in by_id and by_id[cid]["status"] == "running":
                    by_id[cid].update(status="abandoned", outcome_seq=event["seq"])
                    get(next(e["bug_attempt"]["bug_id"] for e in entries if e.get("contract_id") == cid and e.get("bug_attempt")))["basis"] = event["seq"]
        if event["kind"] == "approval" and event.get("scope") == "attempt_escalation":
            before = snapshot(state)
            if (event.get("actor") != "johnathan" or event.get("actor_type") != "human" or not isinstance(event.get("quote"), str) or not event["quote"].strip() or before["status"] not in ("awaiting_decision", "stopped") or
                    event.get("expected_state_hash") != before["state_hash"] or event.get("next_attempt") != before["next_attempt"]):
                raise ValueError("escalation decision is not bound to the current blocked bug")
            if event["choice"] == "retry":
                state["stopped"], state["retry_ref"] = False, event["seq"]
            elif event["choice"] == "stop" and not state["stopped"]:
                state["stopped"], state["retry_ref"] = True, None
            else:
                raise ValueError("invalid or duplicate owner decision")
            state["basis"] = event["seq"]
    return snapshot(get(bug_id))


def bug_identity(contract):
    if contract.get("extensions", {}).get("orchestration", {}).get("role") not in ("coding", "worker"):
        return None
    declared = contract.get("extensions", {}).get("triage", {}).get("bug_id")
    pinned = next((i for i in contract["inputs"] if i["name"] == "bug_snapshot"), None)
    if not declared and not pinned:
        if contract["id"].startswith("ct-fix-"):
            raise ValueError("fix contracts require their pinned bug_snapshot identity")
        return None
    if not pinned or not pinned.get("sha256") or not pinned.get("path") or pinned.get("late_bind"):
        raise ValueError("fix attempts require a pinned bug_snapshot input")
    raw = Path(pinned["path"]).read_bytes()
    if sha256(raw).hexdigest() != pinned["sha256"]:
        raise ValueError("bug snapshot hash mismatch")
    bug = json.loads(raw)
    cid = bug.get("id")
    if not isinstance(cid, str) or re.fullmatch(r"BUG-[0-9]+", cid) is None or (declared and declared != cid):
        raise ValueError("declared bug differs from approved snapshot")
    return cid


def approval_binding(harness, contract, entries, old_approval=None):
    bug_id = bug_identity(contract)
    old_binding = old_approval.get("bug_attempt") if old_approval else None
    if old_binding and old_binding["bug_id"] != bug_id:
        raise ValueError("amendment cannot change or remove a fix attempt's bug identity")
    derived = contract.get("extensions", {}).get("lineage", {}).get("derived_from")
    derived_id = derived.get("id", derived.get("contract_id")) if isinstance(derived, dict) else derived
    if derived_id:
        ancestor = next((e.get("bug_attempt") for e in reversed(entries) if e.get("contract_id") == derived_id and e.get("bug_attempt")), None)
        if ancestor and ancestor["bug_id"] != bug_id:
            raise ValueError("derived fix contract cannot change its bug identity")
    if not bug_id:
        return None
    from .intake import fix_identity_allowed
    fix_identity_allowed(entries, bug_id, snapshot_input=next((i for i in contract["inputs"] if i["name"] == "bug_snapshot"), None) if not old_binding else None)
    current = status(entries, bug_id)
    if old_binding:
        attempt = next(a for a in current["attempts"] if a["contract_id"] == contract["id"])
        if attempt["status"] != "running":
            raise ValueError("finished fix attempt cannot be reopened by an amendment")
        return deepcopy(old_binding)
    if old_approval:
        raise ValueError("legacy fix approval requires explicit migration; it cannot gain a free attempt")
    if current["status"] != "ready":
        raise ValueError("attempt_limit_reached: awaiting_decision" if current["status"] == "awaiting_decision" else "bug attempt is " + current["status"])
    return {"bug_id": bug_id, "number": current["next_attempt"], "escalation_ref": current["retry_approval_ref"]}


def action_block(entries, approval):
    binding = approval.get("bug_attempt")
    if not binding:
        return None
    current = status(entries, binding["bug_id"])
    attempt = next(a for a in current["attempts"] if a["contract_id"] == approval["contract_id"])
    return None if attempt["status"] == "running" else "attempt_" + attempt["status"]


def failure_proof(harness, entries, contract_id, version, execution_seq, required_edit_seq=None):
    """Check captured failure against the approved script and prior edited bytes."""
    from .staged_fix import execution
    event, payload = execution(harness, execution_seq)
    c = json.loads(harness._path(contract_id, version).read_text(encoding="utf-8"))
    approval = next((e for e in entries if e["kind"] == "approval" and e.get("scope") == "contract" and e.get("contract_id") == contract_id and e.get("contract_version") == version), {})
    if content_hash(c) != approval.get("content_hash"):
        raise ValueError("failure contract differs from its approved hash")
    decision = next((e for e in entries if e["seq"] == event["decision_seq"]), {})
    if (event["contract_id"] != contract_id or event["contract_version"] != version or payload["returncode"] != 1 or
            "AssertionError" not in payload["stderr"] or decision.get("action", {}).get("tool") != "test.run" or
            normal(decision["action"]["args"]["script"]) != payload["script"]):
        raise ValueError("captured failing regression from the current attempt version required")
    if not any(i.get("path") and normal(i["path"]) == payload["script"] and i.get("sha256") == payload["script_sha256"] for i in c["inputs"]):
        raise ValueError("failure was not produced by the approved pinned script")
    for evidence in reversed(entries):
        if evidence["kind"] != "evidence" or evidence.get("contract_id") != contract_id or evidence.get("contract_version") != version or evidence.get("status") != "complete" or evidence["seq"] >= execution_seq:
            continue
        if required_edit_seq is not None and evidence["seq"] != required_edit_seq:
            continue
        written = next((e for e in entries if e["seq"] == evidence["decision_seq"]), {})
        args = written.get("action", {}).get("args", {})
        if written.get("decision") != "allow" or written.get("action", {}).get("tool") != "fs.write" or not isinstance(args.get("content"), str):
            continue
        permitted = next((a for a in c["allowed_actions"] if a["action_id"] == evidence["action_id"] and a["tool"] == "fs.write"), None)
        if not permitted or not constraints_ok(args, permitted["args_constraints"], permitted.get("allow_extra_args", False)):
            continue
        ref = evidence["evidence_refs"][0]
        data = json.loads((harness.root / "evidence" / (ref + ".json")).read_text(encoding="utf-8"))
        if digest(data) != ref:
            raise ValueError("edit evidence was tampered with")
        actual = sha256(args["content"].encode("utf-8")).hexdigest()
        if any(i["kind"] == "file_hash" and i["result"] == "pass" and normal(i["params"]["path"]) == normal(args["path"]) and
               i["params"]["sha256"] == actual and payload["inputs"].get(normal(args["path"])) == actual for i in data["items"]):
            return event, payload, evidence
    raise ValueError("verified source edit before the failing regression required; baseline repro is not a failed fix")


def validate_history(harness, entries):
    bugs, allocated = set(), set()
    for index, event in enumerate(entries):
        if event["kind"] == "approval" and event.get("scope") == "contract":
            c = json.loads(harness._path(event["contract_id"], event["contract_version"]).read_text(encoding="utf-8"))
            identity = bug_identity(c)
            binding = event.get("bug_attempt")
            derived = c.get("extensions", {}).get("lineage", {}).get("derived_from")
            derived_id = derived.get("id", derived.get("contract_id")) if isinstance(derived, dict) else derived
            ancestor = next((e.get("bug_attempt") for e in entries if e.get("contract_id") == derived_id and e.get("bug_attempt")), None) if derived_id else None
            if ancestor and identity != ancestor["bug_id"]:
                raise ValueError("derived fix contract changed its bug identity")
            if identity and (not binding or binding["bug_id"] != identity):
                raise ValueError("fix approval lacks its immutable bug-attempt binding")
            if binding:
                if event["contract_id"] not in allocated:
                    from .intake import fix_identity_allowed
                    fix_identity_allowed(entries[:index], identity, snapshot_input=next((i for i in c["inputs"] if i["name"] == "bug_snapshot"), None))
                    allocated.add(event["contract_id"])
                if identity != binding["bug_id"]:
                    raise ValueError("attempt binding differs from contract snapshot")
                bugs.add(binding["bug_id"])
        elif event["kind"] == "state_transition" and event.get("detail", {}).get("scope") == "bug_attempt":
            if event.get("attempt_status") != "failed":
                raise ValueError("invalid attempt outcome")
            source, _, proof = failure_proof(harness, entries, event["contract_id"], event["contract_version"], event["execution_seq"], event["edit_evidence_seq"])
            if event["seq"] <= source["seq"] or event["evidence_refs"] != proof["evidence_refs"] or event["output_ref"] != source["output_ref"]:
                raise ValueError("failure outcome differs from captured proof")
        elif event["kind"] == "approval" and event.get("scope") == "attempt_escalation":
            bugs.add(event["bug_id"])
            expected = {"bug_id": event["bug_id"], "state_hash": event["expected_state_hash"], "choice": event["choice"],
                        "items": [{"kind": "reviewer_note", "params": {"reviewer": "johnathan", "role": "owner", "note": event["quote"]}, "result": "pass", "label": "self_reported"}]}
            if event.get("evidence_refs") != [digest(expected)]:
                raise ValueError("owner decision lacks its matching reviewer note")
    from .reconciliation import validate_history as validate_reconciliations
    validate_reconciliations(harness, entries)
    results = {status(entries, bug)["bug_id"]: status(entries, bug) for bug in sorted(bugs)}
    return list(results.values())


class Attempts:
    def __init__(self, harness):
        self.h = harness

    def status(self, bug_id):
        entries = self.h._entries()
        from .intake import canonical_bug_id
        canonical_id = canonical_bug_id(entries, bug_id)
        result = status(entries, canonical_id)
        if canonical_id != bug_id:
            result["requested_bug_id"] = bug_id
        return result

    def fail(self, contract_id, *, execution_seq, reason):
        """Finalize one failed fix using captured regression and verified edit proof.

        Baseline repro or a transient test failure alone is not a fix attempt.
        """
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("failure reason required")
        with self.h._lock():
            entries = self.h._entries()
            active = self.h._active(entries)
            approval = active.get(contract_id)
            if not approval or not approval.get("bug_attempt"):
                raise ValueError("active tracked fix attempt required")
            c = self.h._authority(approval, active)
            blocked = action_block(entries, approval)
            if blocked:
                raise ValueError(blocked)
            event, payload, proof = failure_proof(self.h, entries, contract_id, c["version"], execution_seq)
            binding = approval["bug_attempt"]
            result = self.h._append("state_transition", detail={"scope": "bug_attempt"}, bug_id=binding["bug_id"],
                                    contract_id=contract_id, contract_version=c["version"], attempt_number=binding["number"],
                                    attempt_status="failed", status="awaiting_decision" if binding["number"] >= LIMIT else "failed",
                                    execution_seq=execution_seq, edit_evidence_seq=proof["seq"], reason=reason,
                                    evidence_refs=proof["evidence_refs"], output_ref=event["output_ref"])
            return {"outcome_seq": result["seq"], **self.status(binding["bug_id"])}

    def decide(self, bug_id, *, choice, expected_state_hash, approver, quote):
        if approver != "johnathan" or not isinstance(quote, str) or not quote.strip():
            raise ValueError("Johnathan's own recorded decision required")
        if choice not in ("retry", "stop"):
            raise ValueError("decision must be retry or stop")
        with self.h._lock():
            current = self.status(bug_id)
            bug_id = current["bug_id"]
            if current["status"] not in ("awaiting_decision", "stopped") or (current["status"] == "stopped" and choice == "stop"):
                raise ValueError("bug is not awaiting an owner decision")
            if expected_state_hash != current["state_hash"]:
                raise ValueError("escalation state changed; review the current state hash")
            note = {"bug_id": bug_id, "state_hash": expected_state_hash, "choice": choice,
                    "items": [{"kind": "reviewer_note", "params": {"reviewer": "johnathan", "role": "owner", "note": quote}, "result": "pass", "label": "self_reported"}]}
            ref = digest(note)
            folder = self.h.root / "evidence"
            folder.mkdir(exist_ok=True)
            (folder / (ref + ".json")).write_bytes(canonical(note))
            event = self.h._append("approval", scope="attempt_escalation", bug_id=bug_id, choice=choice,
                                   next_attempt=current["next_attempt"], expected_state_hash=expected_state_hash,
                                   actor_type="human", actor=approver, channel="local_host", quote=quote, evidence_refs=[ref])
            return {"decision_seq": event["seq"], **self.status(bug_id)}
