"""Proposal compilation and audit-bound amendment review. No approval authority."""
from copy import deepcopy
import json

from .core import EXCLUDED, canonical, content_hash, digest, subset, validate

PROTECTED = {"id", "version", "intent_text", "status", "approved_by", "approved_at", "content_hash"}


def terms(contract):
    result = {k: deepcopy(v) for k, v in contract.items() if k not in EXCLUDED | {"version"}}
    result.get("extensions", {}).pop("lineage", None)
    return result


def diff(old, new, pointer=""):
    if canonical(old) == canonical(new):
        return []
    if isinstance(old, dict) and isinstance(new, dict):
        result = []
        for key in sorted(old.keys() | new.keys()):
            path = pointer + "/" + key.replace("~", "~0").replace("/", "~1")
            if key not in old:
                result.append({"op": "add", "pointer": path, "old": None, "new": new[key]})
            elif key not in new:
                result.append({"op": "remove", "pointer": path, "old": old[key], "new": None})
            else:
                result.extend(diff(old[key], new[key], path))
        return result
    return [{"op": "replace", "pointer": pointer, "old": old, "new": new}]


def patch(document, changes):
    if not isinstance(changes, list):
        raise ValueError("changes must be a JSON-pointer operation list")
    for change in changes:
        if not isinstance(change, dict) or change.get("op") not in ("add", "replace", "remove"):
            raise ValueError("only add, replace and remove operations are supported")
        pointer = change.get("pointer", change.get("path"))
        if not isinstance(pointer, str) or not pointer.startswith("/") or "//" in pointer:
            raise ValueError("invalid JSON pointer")
        import re
        if re.search(r"~(?![01])", pointer):
            raise ValueError("invalid JSON pointer escape")
        keys = [k.replace("~1", "/").replace("~0", "~") for k in pointer[1:].split("/")]
        if keys[0] in PROTECTED or keys == ["extensions"] or keys[:2] in (["extensions", "lineage"], ["extensions", "orchestration"]):
            raise ValueError("identity, original intent, lineage and role are harness-managed")
        target = document
        for key in keys[:-1]:
            if isinstance(target, list):
                if not key.isdecimal() or (key != "0" and key.startswith("0")):
                    raise ValueError("invalid array index")
                target = target[int(key)]
            else:
                target = target[key]
        key, op = keys[-1], change["op"]
        if op != "remove" and "value" not in change:
            raise ValueError("operation value required")
        if isinstance(target, list):
            if key == "-" and op == "add":
                index = len(target)
            elif key.isdecimal() and (key == "0" or not key.startswith("0")):
                index = int(key)
            else:
                raise ValueError("invalid array index")
            if index > len(target) or (op != "add" and index == len(target)):
                raise ValueError("array index out of range")
            if op == "add":
                target.insert(index, deepcopy(change["value"]))
            elif op == "remove":
                target.pop(index)
            else:
                target[index] = deepcopy(change["value"])
        elif isinstance(target, dict):
            if op != "add" and key not in target:
                raise ValueError("pointer target missing")
            if op == "remove":
                del target[key]
            else:
                target[key] = deepcopy(change["value"])
        else:
            raise ValueError("pointer parent is not a container")
    return document


def affected(old, new):
    all_ids = {a["action_id"] for a in old["allowed_actions"] + new["allowed_actions"]}
    global_keys = ("agent", "inputs", "allowed_paths", "forbidden_actions", "requires_approval", "approval_mode", "art_direction")
    if any(old.get(k) != new.get(k) for k in global_keys):
        return sorted(all_ids)
    # Unknown extension changes may alter step semantics; rerun conservatively.
    if terms(old).get("extensions") != terms(new).get("extensions"):
        return sorted(all_ids)
    from .core import timestamp
    ow, nw = old["limits"]["time_window"], new["limits"]["time_window"]
    if "ttl_hours" in nw:
        return sorted(all_ids)
    if (any(new["limits"][k] < old["limits"][k] for k in ("max_calls", "spend_usd")) or
            timestamp(nw["not_before"]) > timestamp(ow["not_before"]) or timestamp(nw["not_after"]) < timestamp(ow["not_after"])):
        return sorted(all_ids)
    oa = {a["action_id"]: a for a in old["allowed_actions"]}
    na = {a["action_id"]: a for a in new["allowed_actions"]}
    return sorted(key for key in all_ids if oa.get(key) != na.get(key) or old["required_evidence"].get(key) != new["required_evidence"].get(key))


def compile_proposal(old, proposal, actor, historical=None):
    if not isinstance(proposal, dict) or not isinstance(proposal.get("reason"), str) or not proposal["reason"].strip():
        raise ValueError("amendment reason required")
    if type(proposal.get("round")) is not int or proposal["round"] < 1:
        raise ValueError("positive round required")
    source = proposal.get("source", {})
    if source.get("kind") not in ("bug", "playtest", "review", "manual", "pipeline") or not isinstance(source.get("id"), str) or not source["id"]:
        raise ValueError("source kind and id required")
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("proposing actor required")
    rollback = proposal.get("rollback_to")
    if rollback is not None:
        if proposal.get("changes"):
            raise ValueError("rollback cannot include additional changes")
        if historical is None:
            raise ValueError("approved historical version required")
        new = deepcopy(historical)
    else:
        new = patch(deepcopy(old), proposal.get("changes", []))
    new.update(version=old["version"] + 1, status="draft", approved_by=None, approved_at=None, content_hash=None)
    new["intent_text"] = old["intent_text"]
    log = deepcopy(old.get("extensions", {}).get("lineage", {}).get("amendment_log", []))
    item = {"to_version": new["version"], "round": proposal["round"], "reason": "rollback" if rollback else proposal["reason"],
            "source_id": source["id"], "from_hash": old["content_hash"]}
    if rollback:
        item["rollback_to"] = rollback
    if "failing_step" in proposal:
        if not isinstance(proposal["failing_step"], str) or not proposal["failing_step"]:
            raise ValueError("failing_step must be a step id")
        item["failing_step"] = proposal["failing_step"]
    log.append(item)
    new.setdefault("extensions", {})["lineage"] = {"supersedes": {"version": old["version"], "content_hash": old["content_hash"]},
                                                  "amendment_log": log, "derived_from": None}
    validate(new)
    changes = diff(terms(old), terms(new))
    if not changes:
        raise ValueError("amendment must change contract terms")
    wider = not subset(new, old) or new.get("art_direction") != old.get("art_direction")
    extension_changes = [change for change in changes if change["pointer"].startswith("/extensions/")]
    widening_items = changes if wider else extension_changes
    record = {"contract_id": old["id"], "from_version": old["version"], "to_version": new["version"],
              "from_hash": old["content_hash"], "to_hash": None, "draft_hash": content_hash(new),
              "changed_fields": [change["pointer"] for change in changes], "diff": changes,
              "widening": {"computed": True, "items": widening_items}, "widening_sha256": digest(widening_items),
              "reason": proposal["reason"], "source": source, "round": proposal["round"],
              "proposed_by": {"actor": actor, "actor_type": "ai"}, "affected_actions": affected(old, new),
              "approved_by": None, "approved_at": None, "approval_seq": None}
    if rollback:
        record["rollback_to"] = rollback
    summary = {"from_version": old["version"], "to_version": new["version"], "diff": changes,
               "warnings": ["WIDER THAN USUAL: " + change["pointer"] + "; needs your separate acknowledgement" for change in widening_items],
               "widening_sha256": record["widening_sha256"], "affected_actions": record["affected_actions"]}
    return new, record, summary


def record_path(harness, cid, version):
    return harness._path(cid, version).parent / "amendments" / f"v{version - 1}-to-v{version}.json"


def prepared(harness, old, new, entries):
    record = json.loads(record_path(harness, old["id"], new["version"]).read_text(encoding="utf-8"))
    event = next((e for e in reversed(entries) if e["kind"] == "amendment_draft" and e.get("contract_id") == old["id"] and e.get("contract_version") == new["version"]), None)
    if not event or digest(record) != event["record_hash"] or record["draft_hash"] != content_hash(new) or record["from_hash"] != old["content_hash"]:
        raise ValueError("amendment record or reviewed draft changed; recompile the proposal")
    proposal = json.loads((harness.root / record["proposal_ref"]["path"]).read_text(encoding="utf-8"))
    if digest(proposal) != record["proposal_ref"]["sha256"]:
        raise ValueError("proposal hash mismatch")
    return record


def amend(harness, cid, proposal, actor, replace_pending=False):
    with harness._lock():
        entries = harness._entries()
        active = harness._active(entries)
        if cid not in active:
            raise ValueError("only an active head may be amended")
        # A child invalidated by a scope change is terminal; no silent revival.
        old = harness._authority(active[cid], active)
        version = old["version"] + 1
        path = harness._path(cid, version)
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if not replace_pending or existing["status"] != "draft":
                raise ValueError("a successor draft already exists")
        historical = None
        if "rollback_to" in proposal:
            target = proposal["rollback_to"]
            if type(target) is not int or not 1 <= target < old["version"]:
                raise ValueError("rollback target must be an earlier approved version")
            approval = next((e for e in entries if e["kind"] == "approval" and e.get("scope") == "contract" and e.get("contract_id") == cid and e.get("contract_version") == target), None)
            if not approval:
                raise ValueError("rollback target was never approved")
            historical = json.loads(harness._path(cid, target).read_text(encoding="utf-8"))
            validate(historical)
            if content_hash(historical) != approval["content_hash"]:
                raise ValueError("historical contract hash mismatch")
        new, record, summary = compile_proposal(old, proposal, actor, historical)
        relative = f"triage/amendments/{cid}.v{old['version']}-to-v{version}.{digest(proposal)}.json"
        record["proposal_ref"] = {"path": relative, "sha256": digest(proposal)}
        proposal_path = harness.root / relative
        proposal_path.parent.mkdir(parents=True, exist_ok=True)
        proposal_path.write_bytes(canonical(proposal))
        rp = record_path(harness, cid, version)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_bytes(canonical(record))
        path.write_bytes(canonical(new))
        harness._append("amendment_draft", contract_id=cid, contract_version=version, actor_type="ai", actor=actor,
                        from_version=old["version"], record_hash=digest(record), proposal_ref=record["proposal_ref"], amendment_record=record)
        return {"contract": new, "amendment_record": record, "summary": summary}


def acknowledge(harness, cid, version, widening_sha256, approver, quote):
    if approver != "johnathan" or not quote.strip():
        raise ValueError("Johnathan's separate widening acknowledgement required")
    with harness._lock():
        entries = harness._entries()
        active = harness._active(entries)
        if cid not in active or version != active[cid]["contract_version"] + 1:
            raise ValueError("only the pending successor may be acknowledged")
        old = harness._load(active[cid])
        new = json.loads(harness._path(cid, version).read_text(encoding="utf-8"))
        record = prepared(harness, old, new, entries)
        if not record["widening"]["items"] or widening_sha256 != record["widening_sha256"]:
            raise ValueError("widening hash does not match computed items")
        return harness._append("approval", scope="widening_ack", **{"class": "widening_ack"}, contract_id=cid,
                               contract_version=version, for_version=version, widening_sha256=widening_sha256,
                               reviewed_hash=content_hash(new), actor_type="human", actor=approver, quote=quote, channel="local_host")
