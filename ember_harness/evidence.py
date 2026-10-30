"""Evidence checks against approved requirements, never caller-supplied verdicts."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re
from urllib.parse import urlsplit

from .core import canonical, constraints_ok, digest, matches, normal


def evaluate(harness, contract, action_id, items, decision, entries, historical=False):
    action = next((a for a in contract["allowed_actions"] if a["action_id"] == action_id), None)
    if not action:
        raise ValueError("unknown action_id")
    request = decision.get("action", {})
    if (decision.get("decision") != "allow" or decision.get("contract_id") != contract["id"] or
            (decision.get("contract_version") != contract["version"] and not historical)):
        raise ValueError("evidence requires an allowed decision for this action and active version")
    if (request.get("tool") != action["tool"] or
            not constraints_ok(request["args"], action["args_constraints"], action.get("allow_extra_args", False))):
        if historical:
            return [{"kind": r["kind"], "params": {}, "result": "fail", "label": "unverified", "detail": "old action no longer fits active terms"}
                    for r in contract["required_evidence"].get(action_id, [])], "incomplete"
        raise ValueError("evidence requires an allowed decision for this action and active version")
    if not isinstance(items, list):
        raise ValueError("evidence items must be a list")
    requirements = contract["required_evidence"].get(action_id, [])
    results, machine_passes = [], 0

    def file_bytes(path):
        resolved = normal(path)
        if not any(matches(resolved, pattern) for mode in ("read", "write") for pattern in contract["allowed_paths"][mode]):
            raise ValueError("evidence path outside contract")
        return Path(resolved).read_bytes()

    def file_hash(path, expected):
        actual = sha256(file_bytes(path)).hexdigest()
        if actual != expected:
            raise ValueError("file hash mismatch")
        for source in contract["inputs"]:
            if "path" in source and normal(source["path"]) == normal(path):
                pinned = source.get("sha256")
                if source.get("late_bind"):
                    checks = [e for e in entries if e["kind"] == "input_check" and e.get("contract_id") == contract["id"] and e.get("contract_version") == contract["version"]]
                    if not checks or not checks[-1]["passed"]:
                        raise ValueError("late-bound input was not verified")
                    pinned = checks[-1]["late_bound"].get(source["name"])
                if pinned and actual != pinned:
                    raise ValueError("input changed since preflight")
        return actual

    for requirement in requirements:
        kind, rules = requirement["kind"], requirement["params"]
        # Each requirement consumes its own item; duplicate requirements cannot
        # be satisfied by reusing one claim.
        index = next((i for i, item in enumerate(items) if isinstance(item, dict) and isinstance(item.get("params"), dict) and item.get("kind") == kind and
                      ("label" not in rules or item.get("params", {}).get("label") == rules["label"])), None)
        params = deepcopy(items[index].get("params", {})) if index is not None else {}
        if index is not None:
            items = items[:index] + items[index + 1:]
        result = {"kind": kind, "params": params, "result": "fail", "label": "unverified"}
        try:
            if index is None or not isinstance(params, dict):
                raise ValueError("required evidence missing or malformed")
            for key, expected in rules.items():
                if key not in ("fields", "pattern", "items", "expect_count") and canonical(params.get(key)) != canonical(expected):
                    raise ValueError(f"evidence differs from approved requirement: {key}")
            if any(key not in params for key in rules.get("fields", [])):
                raise ValueError("required evidence fields missing")
            machine = True
            if kind == "file_hash":
                path = params["path"]
                # A result file must actually belong to the checked request.
                touched = request["paths"]["read"] + request["paths"]["write"]
                from .core import TOOLS
                touched += [request["args"][key] for key in TOOLS[action["tool"]]["paths"]]
                if normal(path) not in [normal(p) for p in touched]:
                    raise ValueError("file is unrelated to allowed action")
                file_hash(path, params["sha256"])
            elif kind == "source_dest_hash":
                src, dest = params["source_path"], params["dest_path"]
                if normal(src) != normal(request["args"]["src"]) or normal(dest) != normal(request["args"]["dest"]):
                    raise ValueError("copy evidence differs from allowed action")
                conversion = params.get("conversion")
                if conversion and action["tool"] != "image.convert_png":
                    raise ValueError("conversion requires a converting tool")
                source = file_hash(src, params.get("source_sha256", params.get("sha256")))
                destination = file_hash(dest, params.get("dest_sha256", params.get("sha256")))
                if not conversion and source != destination:
                    raise ValueError("pure copy hashes differ")
            elif kind == "file_list":
                files = params["files"]
                if not isinstance(files, list) or not files or len({normal(f["path"]) for f in files}) != len(files):
                    raise ValueError("file list empty or duplicated")
                if "expect_count" in rules and len(files) != rules["expect_count"]:
                    raise ValueError("file count mismatch")
                from .core import TOOLS
                touched = request["paths"]["read"] + request["paths"]["write"]
                touched += [request["args"][key] for key in TOOLS[action["tool"]]["paths"]]
                for file in files:
                    if normal(file["path"]) not in [normal(p) for p in touched]:
                        raise ValueError("listed file is unrelated to allowed action")
                    if type(file["size"]) is not int or len(file_bytes(file["path"])) != file["size"]:
                        raise ValueError("file size mismatch")
            elif kind == "output_snippet":
                pattern = rules.get("pattern")
                if not pattern or re.search(pattern, params["text"]) is None:
                    raise ValueError("output does not match approved pattern")
            elif kind == "checklist":
                machine = False
                if not rules.get("items") or not params.get("attested_by") or any(params.get("checks", {}).get(key) is not True for key in rules["items"]):
                    raise ValueError("checklist requires all named checks and an attester")
            elif kind == "reviewer_note":
                machine = False
                if not params.get("reviewer") or not params.get("role") or not params.get("note", "").strip():
                    raise ValueError("named reviewer, role and note required")
            elif kind == "url":
                machine = False
                url = urlsplit(params["url"])
                if url.scheme not in ("http", "https") or not url.netloc:
                    raise ValueError("invalid URL")
            else:
                raise ValueError("evidence kind not implemented; cannot establish completion")
            result.update(result="pass", label="verified" if machine else "self_reported")
            machine_passes += int(machine)
        except (ValueError, KeyError, TypeError, OSError) as error:
            result["detail"] = str(error)
        results.append(result)
    complete = bool(requirements) and all(r["result"] == "pass" for r in results) and machine_passes > 0
    return results, "complete" if complete else "incomplete"


def verify(harness, cid, action_id, evidence, decision_seq, carried_from=None):
    with harness._lock():
        entries = harness._entries()
        active = harness._active(entries)
        if cid not in active:
            raise ValueError("no active approved contract")
        contract = harness._authority(active[cid], active)
        decision = next((e for e in entries if e["seq"] == decision_seq and e["kind"] == "decision"), None)
        if decision is None:
            raise ValueError("allowed action decision required")
        historical = decision.get("contract_version", contract["version"]) < contract["version"]
        if historical and (decision["seq"] >= active[cid]["seq"] or not any(e["kind"] == "approval" and e.get("scope") == "contract" and
                e.get("contract_id") == cid and e.get("contract_version") == decision["contract_version"] for e in entries)):
            raise ValueError("historical decision was not under an approved predecessor")
        if carried_from is not None:
            record = active[cid].get("amendment_record")
            if not record or carried_from != record["from_version"] or action_id in record["affected_actions"]:
                raise ValueError("affected actions cannot be carried forward")
        results, status = evaluate(harness, contract, action_id, deepcopy(evidence), decision, entries, historical)
        payload = {"contract_id": cid, "contract_version": contract["version"], "action_id": action_id, "items": results}
        reference = digest(payload)
        folder = harness.root / "evidence"
        folder.mkdir(exist_ok=True)
        path = folder / f"{reference}.json"
        # Stored payloads are immutable content-addressed objects.
        if path.exists() and path.read_bytes() != canonical(payload):
            raise ValueError("stored evidence payload was tampered with")
        path.write_bytes(canonical(payload))
        entry = harness._append("evidence", contract_id=cid, contract_version=contract["version"],
                                action_id=action_id, decision_seq=decision_seq, evidence_refs=[reference],
                                status=status, machine_checked=any(r["label"] == "verified" for r in results),
                                late_under_superseded=historical, source_version=decision.get("contract_version"), carried_from=carried_from)
        return {"status": status, "status_basis": entry["seq"], "evidence_ref": reference, "items": results}


def refresh(harness, cid, action_id):
    """Recheck saved bytes before returning a fresh, audit-backed status."""
    entries = harness._entries()
    active = harness._active(entries)
    if cid not in active:
        raise ValueError("no active approved contract")
    events = [e for e in entries if e["kind"] == "evidence" and e.get("contract_id") == cid and
              e.get("contract_version") == active[cid]["contract_version"] and e.get("action_id") == action_id]
    if not events:
        return {"status": "incomplete", "status_basis": None, "reason": "no_verified_evidence"}
    event = events[-1]
    reference = event["evidence_refs"][0]
    import json
    payload = json.loads((harness.root / "evidence" / f"{reference}.json").read_text(encoding="utf-8"))
    if digest(payload) != reference:
        raise ValueError("evidence payload hash mismatch")
    return verify(harness, cid, action_id, payload["items"], event["decision_seq"])


def carry_forward(harness, cid):
    """Reverify unchanged results without consuming a new tool call."""
    import json
    entries = harness._entries()
    active = harness._active(entries)
    if cid not in active or not active[cid].get("amendment_record"):
        raise ValueError("approved amendment required")
    record = active[cid]["amendment_record"]
    latest = {}
    for event in entries:
        if event["kind"] == "evidence" and event.get("contract_id") == cid and event.get("contract_version") == record["from_version"]:
            latest[event["action_id"]] = event
    results = {}
    for action_id, event in latest.items():
        if action_id in record["affected_actions"] or event["status"] != "complete":
            continue
        reference = event["evidence_refs"][0]
        payload = json.loads((harness.root / "evidence" / f"{reference}.json").read_text(encoding="utf-8"))
        if digest(payload) != reference:
            raise ValueError("evidence payload hash mismatch")
        results[action_id] = verify(harness, cid, action_id, payload["items"], event["decision_seq"], carried_from=record["from_version"])
    return {"results": results, "rerun_actions": record["affected_actions"]}
