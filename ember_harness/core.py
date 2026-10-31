"""In-process gate; the caller must execute only actions returned as allow.

Approval methods belong to a trusted human-facing host, never an agent toolset.
"""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import time

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

SCHEMA_DIR = Path(__file__).parent / "schema"
SCHEMA = json.loads((SCHEMA_DIR / "contract.schema.json").read_text())
TOOLS = json.loads((SCHEMA_DIR / "tools.json").read_text())
MANDATORY = ["live", "publish", "spend", "push", "submit", "send_message"]
BASELINE = ["network.*", "publish.*", "submit.*", "payment.*", "fs.delete", "deploy.*", "git.push", "git.force", "git.remote", "git.merge_pr"]
EXCLUDED = {"status", "approved_by", "approved_at", "content_hash"}
GENESIS = "0" * 64


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(value):
    return sha256(canonical(value)).hexdigest()


def content_hash(contract):
    return digest({k: v for k, v in contract.items() if k not in EXCLUDED})


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timezone required")
    return result


def normal(path):
    if not isinstance(path, str) or not Path(path).is_absolute() or "\x00" in path:
        raise ValueError("absolute local path required")
    # resolve follows symlinks and Windows junctions, including existing ancestors.
    return Path(path).resolve().as_posix()


def glob_regex(pattern):
    if any(c in pattern for c in "{}[]\\") or "***" in pattern:
        raise ValueError("unsupported glob syntax")
    parts, i = [], 0
    while i < len(pattern):
        if pattern[i:i + 3] == "**/":
            parts.append("(?:.*/)?")
            i += 3
        elif pattern[i:i + 2] == "**":
            parts.append(".*")
            i += 2
        else:
            parts.append({"*": "[^/]*", "?": "[^/]"}.get(pattern[i], re.escape(pattern[i])))
            i += 1
    return "".join(parts)


def matches(value, pattern):
    return isinstance(value, str) and re.fullmatch(glob_regex(pattern), value) is not None


def valid_glob(pattern):
    if not Path(pattern).is_absolute() or not any(c in pattern for c in "*?"):
        raise ValueError("absolute path glob required")
    if any(p in (".", "..") for p in pattern.split("/")):
        raise ValueError("glob must be normalized")
    glob_regex(pattern)
    # Literal prefix must itself be canonical (no symlink aliases).
    prefix = pattern[:min([pattern.find(c) for c in "*?" if c in pattern])]
    prefix = prefix.rsplit("/", 1)[0] or "/"
    if normal(prefix).rstrip("/") != prefix.rstrip("/"):
        raise ValueError("glob prefix must be resolved")


def validate(contract):
    canonical(contract)  # Reject NaN and infinity, even inside open extensions.
    Draft202012Validator(SCHEMA, format_checker=FormatChecker()).validate(contract)
    actions = contract["allowed_actions"]
    ids = [a["action_id"] for a in actions]
    if len(ids) != len(set(ids)) or set(contract["required_evidence"]) - set(ids):
        raise ValueError("duplicate action id or evidence for unknown action")
    for group in contract["allowed_paths"].values():
        for pattern in group:
            valid_glob(pattern)
    for item in contract["inputs"]:
        if "path" in item:
            path = normal(item["path"])
            if not any(matches(path, p) for p in contract["allowed_paths"]["read"]):
                raise ValueError("input is outside read scope")
        elif item.get("sha256") or item.get("late_bind"):
            raise ValueError("hashed inputs require a path")
    for action in actions:
        tool = TOOLS.get(action["tool"])
        if tool is None or tool["class"] != action["class"]:
            raise ValueError("unknown tool or incorrect intrinsic class")
        constraints = action["args_constraints"]
        if set(constraints) - set(tool["args"]) or set(tool["paths"]) - set(constraints):
            raise ValueError("unknown argument or unconstrained path argument")
        for rule in constraints.values():
            if "pattern" in rule:
                # Explicit regex dialect: anchored expressions only.
                if not rule["pattern"].startswith("^") or not rule["pattern"].endswith("$"):
                    raise ValueError("patterns must be anchored regexes")
                re.compile(rule["pattern"])
            if "path_within" in rule:
                valid_glob(rule["path_within"])
        if not contract["required_evidence"].get(action["action_id"]) and not action.get("allow_no_evidence"):
            raise ValueError("evidence required unless explicitly waived")
        if action["tool"] == "git.open_pr":
            if any(set(constraints.get(k, {})) != {"equals"} for k in ("branch", "base", "force")):
                raise ValueError("PR branch, base and force require equals constraints")
            if constraints["force"]["equals"] is not False:
                raise ValueError("force push forbidden")
        if action["tool"] in ("git.add", "git.commit"):
            if set(constraints.get("branch", {})) != {"equals"}:
                raise ValueError("local Git operations require a fixed branch")
    window = contract["limits"]["time_window"]
    if "ttl_hours" in window and contract["status"] != "draft":
        raise ValueError("only drafts may have unresolved windows")
    if "ttl_hours" not in window:
        duration = timestamp(window["not_after"]) - timestamp(window["not_before"])
        if not timedelta(0) < duration <= timedelta(hours=24):
            raise ValueError("window must be positive and at most 24 hours")


def draft(contract_id, agent, intent_text, *, role="coding", extensions=None):
    """Safe empty template. Caller must explicitly populate scope before approval."""
    if role not in ("scope", "coding", "asset-step", "triage", "worker", "verifier", "orchestrator"):
        raise ValueError("unknown role")
    ext = deepcopy(extensions or {})
    ext.setdefault("orchestration", {})["role"] = role
    ext.setdefault("lineage", {"supersedes": None, "amendment_log": [], "derived_from": None})
    return {"id": contract_id, "version": 1, "agent": agent, "intent_text": intent_text,
            "goal": intent_text, "inputs": [], "allowed_actions": [],
            "forbidden_actions": [{"tool": t} for t in BASELINE],
            "allowed_paths": {"read": [], "write": []},
            "limits": {"spend_usd": 0, "max_calls": 12 if role == "asset-step" else 50,
                       "time_window": {"not_before": None, "not_after": None, "ttl_hours": 4}},
            "required_evidence": {}, "requires_approval": MANDATORY + ["engine_change", "direction_selection", "asset_acceptance", "bug_close"],
            "extensions": ext, "approval_mode": "each", "status": "draft",
            "approved_by": None, "approved_at": None, "content_hash": None}


def subset(child, parent):
    """Conservative scope proof. Unknown inclusions fail closed.

    Initially supports identical constraints and literal equals under one_of,
    regex, numeric bounds or path_within. More complex glob inclusion is deferred.
    """
    if not set(parent["requires_approval"]) <= set(child["requires_approval"]):
        return False
    if any(x not in child["forbidden_actions"] for x in parent["forbidden_actions"]):
        return False
    if child.get("approval_mode", "each") == "approve_all" and parent.get("approval_mode", "each") != "approve_all":
        return False
    for mode in ("read", "write"):
        if any(p not in parent["allowed_paths"][mode] for p in child["allowed_paths"][mode]):
            return False
    if any(child["limits"][k] > parent["limits"][k] for k in ("max_calls", "spend_usd")):
        return False
    cw, pw = child["limits"]["time_window"], parent["limits"]["time_window"]
    if "ttl_hours" in cw or "ttl_hours" in pw:
        return False  # Inclusion is unknowable until the human approves a window.
    if timestamp(cw["not_before"]) < timestamp(pw["not_before"]) or timestamp(cw["not_after"]) > timestamp(pw["not_after"]):
        return False
    for action in child["allowed_actions"]:
        candidates = [a for a in parent["allowed_actions"] if a["tool"] == action["tool"] and a["class"] == action["class"]]
        def narrower(p):
            if any(item not in child["required_evidence"].get(action["action_id"], [])
                   for item in parent["required_evidence"].get(p["action_id"], [])):
                return False
            if action.get("allow_extra_args", False) and not p.get("allow_extra_args", False):
                return False
            if not p.get("allow_extra_args", False) and set(action["args_constraints"]) - set(p["args_constraints"]):
                return False
            for key, rule in p["args_constraints"].items():
                own = action["args_constraints"].get(key)
                if own == rule:
                    continue
                if own is None:
                    return False
                if set(own) == {"equals"} and constraints_ok({key: own["equals"]}, {key: rule}, True):
                    continue
                for constraint, value in rule.items():
                    candidate = own.get(constraint)
                    if constraint == "one_of" and isinstance(candidate, list):
                        if all(any(canonical(x) == canonical(y) for y in value) for x in candidate):
                            continue
                    elif constraint == "max" and type(candidate) in (int, float) and candidate <= value:
                        continue
                    elif constraint == "min" and type(candidate) in (int, float) and candidate >= value:
                        continue
                    elif constraint in own and canonical(candidate) == canonical(value):
                        continue
                    return False
            return True
        if not any(narrower(p) for p in candidates):
            return False
    return True


def constraints_ok(args, rules, allow_extra=False):
    if not allow_extra and set(args) - set(rules):
        return False
    for key, rule in rules.items():
        if key not in args:
            return False
        value = args[key]
        if "equals" in rule and canonical(value) != canonical(rule["equals"]):
            return False
        if "one_of" in rule and not any(canonical(value) == canonical(x) for x in rule["one_of"]):
            return False
        if "pattern" in rule and (not isinstance(value, str) or re.fullmatch(rule["pattern"], value) is None):
            return False
        for bound in ("min", "max"):
            if bound in rule and (type(value) not in (int, float) or not math.isfinite(value) or
                                  (value < rule[bound] if bound == "min" else value > rule[bound])):
                return False
        if "path_within" in rule and not matches(normal(value), rule["path_within"]):
            return False
        if rule.get("no_overwrite_unless_same_hash") and Path(value).exists():
            expected = args.get("expected_sha256")
            if expected is None and "src" in args:
                expected = sha256(Path(args["src"]).read_bytes()).hexdigest()
            if not expected or sha256(Path(value).read_bytes()).hexdigest() != expected:
                return False
    return True


class Harness:
    def amend(self, contract_id, proposal, *, proposed_by, replace_pending=False):
        from .amendments import amend
        return amend(self, contract_id, proposal, proposed_by, replace_pending)

    def acknowledge_widening(self, contract_id, version, widening_sha256, *, approver, quote):
        from .amendments import acknowledge
        return acknowledge(self, contract_id, version, widening_sha256, approver, quote)

    def carry_forward(self, contract_id):
        from .evidence import carry_forward
        return carry_forward(self, contract_id)

    def history(self, contract_id):
        entries = self._entries()
        approvals = [e for e in entries if e["kind"] == "approval" and e.get("scope") == "contract" and e.get("contract_id") == contract_id]
        active = self._active(entries)
        result = []
        for entry in approvals:
            status = "approved" if active.get(contract_id, {}).get("contract_version") == entry["contract_version"] else "superseded"
            basis = entry["seq"]
            for later in entries[entry["seq"]:]:
                if later["kind"] == "revocation" and later.get("contract_id") == contract_id and later.get("contract_version") == entry["contract_version"]:
                    status, basis = "revoked", later["seq"]
                    break
                if any(c["id"] == contract_id and c["version"] == entry["contract_version"] for c in later.get("revoked_children", [])):
                    status, basis = "revoked", later["seq"]
                    break
                if later["kind"] == "approval" and later.get("scope") == "contract" and later.get("contract_id") == contract_id:
                    basis = later["seq"]
                    break
            result.append({"version": entry["contract_version"], "status": status, "content_hash": entry["content_hash"], "status_basis": basis})
        return result

    def _sync_caches(self, cid):
        """Derived status caches. The audit remains authoritative if this fails."""
        history = self.history(cid)
        for item in history:
            path = self._path(cid, item["version"])
            c = json.loads(path.read_text(encoding="utf-8"))
            c["status"] = item["status"]
            path.write_bytes(canonical(c))
        if history:
            (self._path(cid, 1).parent / "STATE.json").write_bytes(canonical({"versions": history}))

    def verify_evidence(self, contract_id, action_id, evidence, *, decision_seq):
        from .evidence import verify
        return verify(self, contract_id, action_id, evidence, decision_seq)

    def step_status(self, contract_id, action_id):
        from .evidence import refresh
        return refresh(self, contract_id, action_id)

    def __init__(self, root, *, clock=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.audit_path = self.root / "audit" / "audit.jsonl"
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @contextmanager
    def _lock(self):
        # Exclusive across processes; a crashed host leaves a fail-closed lock.
        path = self.root / ".writer.lock"
        deadline = time.monotonic() + 2
        while True:
            try:
                path.open("x").close()
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.02)
        try:
            yield
        finally:
            path.unlink()

    def _entries(self):
        entries, previous = [], GENESIS
        if not self.audit_path.exists():
            return entries
        for seq, line in enumerate(self.audit_path.read_text(encoding="utf-8").splitlines(), 1):
            entry = json.loads(line)
            hashed = {k: v for k, v in entry.items() if k != "entry_hash"}
            if entry["seq"] != seq or entry["prev_hash"] != previous or digest(hashed) != entry["entry_hash"]:
                raise ValueError(f"audit chain broken at seq {seq}")
            previous = entry["entry_hash"]
            entries.append(entry)
        return entries

    def audit_verify(self):
        entries = self._entries()
        return {"ok": True, "entries": len(entries), "head": entries[-1]["entry_hash"] if entries else GENESIS}

    def _append(self, kind, **fields):
        import os
        entries = self._entries()
        entry = {"seq": len(entries) + 1, "ts": self.clock().isoformat(), "kind": kind,
                 "actor_type": "system", "actor": "harness", "approval_ref": None,
                 "evidence_refs": [], "prev_hash": entries[-1]["entry_hash"] if entries else GENESIS,
                 **fields}
        entry["entry_hash"] = digest(entry)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("ab") as stream:
            stream.write(canonical(entry) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        return entry

    def _path(self, cid, version):
        if re.fullmatch(r"ct-[a-z]+(-[a-z0-9]+)*-[0-9]+", cid) is None or type(version) is not int or version < 1:
            raise ValueError("invalid contract identity")
        return self.root / "contracts" / cid / f"v{version}.json"

    def save_draft(self, contract):
        validate(contract)
        if contract["status"] != "draft":
            raise ValueError("agents may save drafts only")
        with self._lock():
            path = self._path(contract["id"], contract["version"])
            active = self._active(self._entries())
            if contract["version"] > 1 and (contract["id"] not in active or contract["version"] != active[contract["id"]]["contract_version"] + 1):
                raise ValueError("only one successor version may be drafted")
            if any(e.get("contract_id") == contract["id"] and e.get("contract_version") == contract["version"]
                   and e["kind"] == "approval" and e.get("scope") == "contract" for e in self._entries()):
                raise ValueError("approved versions are immutable; create a successor")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(canonical(contract))

    def _active(self, entries):
        state = {}
        for entry in entries:
            if entry["kind"] == "approval" and entry.get("scope") == "contract":
                state[entry["contract_id"]] = entry
            if entry["kind"] == "revocation":
                state.pop(entry["contract_id"], None)
            for child in entry.get("revoked_children", []):
                state.pop(child["id"], None)
            for child in entry.get("rebound_children", []):
                if child["id"] in state:
                    state[child["id"]] = {**state[child["id"]], "parent_version": child["parent_version"]}
        return state

    def _load(self, approval):
        c = json.loads(self._path(approval["contract_id"], approval["contract_version"]).read_text(encoding="utf-8"))
        validate(c)
        if (c["id"] != approval["contract_id"] or c["version"] != approval["contract_version"] or
                c["status"] != "approved" or content_hash(c) != approval["content_hash"] or c["content_hash"] != approval["content_hash"]):
            raise ValueError("contract_hash_mismatch")
        return c

    def _authority(self, approval, active):
        c = self._load(approval)
        parent = approval.get("parent_id")
        if parent:
            if parent not in active or active[parent]["contract_version"] != approval["parent_version"]:
                raise ValueError("scope_inactive")
            self._load(active[parent])
        return c

    def approve(self, cid, version, *, approver, quote, expected_hash, parent_id=None, widening_ack=None):
        """Trusted host only. expected_hash is the hash shown to the human reviewer.

        Resolved window hash is returned in the approval record. Conservative
        amendments require separate acknowledgement of every unproven narrowing.
        """
        if approver != "johnathan" or not quote.strip():
            raise ValueError("Johnathan's explicit approval is required")
        with self._lock():
            entries = self._entries()
            active = self._active(entries)
            c = json.loads(self._path(cid, version).read_text(encoding="utf-8"))
            validate(c)
            if c["id"] != cid or c["version"] != version or c["status"] != "draft" or content_hash(c) != expected_hash:
                raise ValueError("reviewed draft changed")
            seen = [e for e in entries if e["kind"] == "approval" and e.get("scope") == "contract" and e["contract_id"] == cid]
            if seen and (cid not in active or version != active[cid]["contract_version"] + 1):
                raise ValueError("only the active head may have a successor")
            if not seen and version != 1:
                raise ValueError("first version must be 1")
            if any(e["contract_version"] == version for e in seen):
                raise ValueError("terminal versions cannot be reapproved")
            original_draft = deepcopy(c)
            old = self._load(active[cid]) if cid in active else None
            record, ack = None, None
            if old:
                from .amendments import prepared
                record = prepared(self, old, c, entries)
                if c.get("extensions", {}).get("orchestration", {}).get("role") != active[cid].get("role"):
                    raise ValueError("contract role cannot change across versions")
                if record["widening"]["items"]:
                    ack = next((e for e in reversed(entries) if e["kind"] == "approval" and e.get("scope") == "widening_ack" and
                                e.get("contract_id") == cid and e.get("for_version") == version and e.get("actor_type") == "human" and e.get("actor") == "johnathan" and
                                e.get("widening_sha256") == record["widening_sha256"] and e.get("reviewed_hash") == expected_hash), None)
                    if ack is None:
                        raise ValueError("widening_ack_missing: separate widening acknowledgement required")
                if parent_id is None:
                    parent_id = active[cid].get("parent_id")
            now = self.clock()
            window = c["limits"]["time_window"]
            if "ttl_hours" in window:
                c["limits"]["time_window"] = {"not_before": now.isoformat(), "not_after": (now + timedelta(hours=window["ttl_hours"])).isoformat()}
            role = c.get("extensions", {}).get("orchestration", {}).get("role")
            if role != "scope":
                if not parent_id or parent_id == cid or parent_id not in active or active[parent_id].get("role") != "scope":
                    raise ValueError("approved scope contract required")
                parent = self._authority(active[parent_id], active)
                if not subset(c, parent):
                    raise ValueError("build contract exceeds scope (or inclusion cannot be proven)")
                if c.get("art_direction") != parent.get("art_direction"):
                    raise ValueError("build must inherit scope art_direction")
            elif parent_id:
                raise ValueError("scope contract must be root")
            if any(a["tool"] == "git.open_pr" for a in c["allowed_actions"]) and role not in ("coding", "scope"):
                raise ValueError("only coding contracts may open PRs")
            # Reserved store cannot be writable through an agent contract.
            for pattern in c["allowed_paths"]["write"]:
                prefix = re.split(r"[*?]", pattern, maxsplit=1)[0].rstrip("/")
                import os
                prefix = os.path.normcase(prefix).replace("\\", "/")
                store = os.path.normcase(self.root.as_posix()).replace("\\", "/")
                if prefix == store or prefix.startswith(store + "/") or store.startswith(prefix + "/"):
                    raise ValueError("agents may not write harness system files")
            if widening_ack is not None:
                raise ValueError("use acknowledge_widening before approval; inline acknowledgement is not accepted")
            from .attempts import approval_binding
            bug_attempt = approval_binding(self, c, entries, active.get(cid))
            c.update(status="approved", approved_by=approver, approved_at=now.isoformat())
            c["content_hash"] = content_hash(c)
            validate(c)
            revoked_children, rebound_children = [], []
            for child_id, approval in active.items():
                if approval.get("parent_id") == cid:
                    child = self._load(approval)
                    if subset(child, c) and child.get("art_direction") == c.get("art_direction"):
                        rebound_children.append({"id": child_id, "parent_version": version})
                    else:
                        revoked_children.append({"id": child_id, "version": child["version"], "reason": "parent_narrowed"})
            if record:
                record = {**record, "to_hash": c["content_hash"], "approved_by": approver,
                          "approved_at": now.isoformat(), "approval_seq": len(entries) + 1}
            self._path(cid, version).write_bytes(canonical(c))
            # Audit is authoritative: a crash before this append grants no rights.
            try:
                entry = self._append("approval", scope="contract", contract_id=cid, contract_version=version,
                                 content_hash=c["content_hash"], role=role, parent_id=parent_id,
                                 parent_version=active[parent_id]["contract_version"] if parent_id else None,
                                 actor_type="human", actor=approver, quote=quote, reviewed_hash=expected_hash,
                                 bug_attempt=bug_attempt,
                                 widening_ack_seq=ack["seq"] if ack else None, supersedes=old["version"] if old else None,
                                 amendment_record=record, revoked_children=revoked_children, rebound_children=rebound_children)
            except OSError:
                self._path(cid, version).write_bytes(canonical(original_draft))
                raise
            warning = None
            try:
                if record:
                    from .amendments import record_path
                    record_path(self, cid, version).write_bytes(canonical(record))
                approval_folder = self.root / "approvals"
                approval_folder.mkdir(exist_ok=True)
                (approval_folder / f"{cid}-v{version}.json").write_bytes(canonical(entry))
                self._sync_caches(cid)
                for child in revoked_children:
                    self._sync_caches(child["id"])
            except (OSError, ValueError) as error:
                warning = str(error)
            return {"contract": c, "approval_seq": entry["seq"], "audit_head": entry["entry_hash"], "cache_warning": warning}

    def revoke(self, cid, *, approver, reason):
        if approver != "johnathan" or not reason.strip():
            raise ValueError("Johnathan's revocation required")
        with self._lock():
            active = self._active(self._entries())
            if cid not in active:
                raise ValueError("no active contract")
            children = [{"id": key, "version": value["contract_version"], "reason": "parent_revoked"} for key, value in active.items() if value.get("parent_id") == cid]
            self._append("revocation", contract_id=cid, contract_version=active[cid]["contract_version"],
                         actor_type="human", actor=approver, reason=reason, revoked_children=children)
            self._sync_caches(cid)
            for child in children:
                self._sync_caches(child["id"])

    def verify_inputs(self, cid):
        with self._lock():
            entries = self._entries()
            active = self._active(entries)
            c = self._authority(active[cid], active)
            prior = next((e for e in entries if e["kind"] == "input_check" and e.get("contract_id") == cid and
                          e.get("contract_version") == c["version"] and e.get("passed")), None)
            hashes, ok = {}, True
            for item in c["inputs"]:
                if item.get("sha256") or item.get("late_bind"):
                    try:
                        if not any(matches(normal(item["path"]), p) for p in c["allowed_paths"]["read"]):
                            raise OSError("input escaped read scope")
                        actual = sha256(Path(item["path"]).read_bytes()).hexdigest()
                        ok &= not item.get("sha256") or actual == item["sha256"]
                        if item.get("late_bind") and prior:
                            ok &= actual == prior["late_bound"].get(item["name"])
                        hashes[item["name"]] = actual
                    except OSError:
                        ok = False
            self._append("input_check", contract_id=cid, contract_version=c["version"], passed=bool(ok), late_bound=hashes)
            return bool(ok)

    def _evaluate(self, action, entries):
        canonical(action)
        if set(action) - {"agent", "tool", "args", "paths", "spend", "contract_id", "contract_version"}:
            return "deny", "invalid_action", None, None
        if not isinstance(action.get("args"), dict) or set(action.get("paths", {})) != {"read", "write"}:
            return "deny", "invalid_action", None, None
        if any(not isinstance(v, list) for v in action["paths"].values()) or type(action.get("spend")) not in (int, float) or action["spend"] < 0:
            return "deny", "invalid_action", None, None
        active = self._active(entries)
        candidates = [e for e in active.values() if self._load(e)["agent"] == action.get("agent")]
        cid = action.get("contract_id")
        if not cid and len(candidates) > 1:
            return "deny", "contract_id_required", None, None
        approval = active.get(cid) if cid else (candidates[0] if candidates else None)
        if not approval:
            return "deny", "contract_not_found", None, None
        c = self._authority(approval, active)
        if c["agent"] != action.get("agent"):
            return "deny", "contract_not_found", None, None
        if approval.get("role") == "scope" and action.get("tool") != "scope.select":
            return "deny", "scope_is_ceiling_only", c, None
        if action.get("contract_version", c["version"]) != c["version"]:
            return "deny", "contract_superseded", c, None
        from .attempts import action_block
        attempt_reason = action_block(entries, approval)
        if attempt_reason:
            return "deny", attempt_reason, c, None
        if approval.get("role") in ("coding", "worker") and not approval.get("bug_attempt") and any(i["name"] == "bug_snapshot" for i in c["inputs"]):
            return "deny", "attempt_tracking_required", c, None
        inputs = [e for e in entries if e["kind"] == "input_check" and e.get("contract_id") == c["id"] and e.get("contract_version") == c["version"]]
        if any(i.get("sha256") or i.get("late_bind") for i in c["inputs"]) and (not inputs or not inputs[-1]["passed"]):
            return "deny", "inputs_unverified", c, None
        window = c["limits"]["time_window"]
        if not timestamp(window["not_before"]) <= self.clock() <= timestamp(window["not_after"]):
            return "deny", "outside_time_window", c, None
        tool_name = action.get("tool")
        if not isinstance(tool_name, str):
            return "deny", "invalid_action", c, None
        if any(matches(tool_name, p) for p in BASELINE):
            return "deny", "baseline_forbidden", c, None
        if tool_name == "review.muse" and action["args"].get("provider") not in ("echo", "manual"):
            return "deny", "muse_credit_limit_unavailable", c, None
        for forbidden in c["forbidden_actions"]:
            if matches(tool_name, forbidden["tool"]) and constraints_ok(action["args"], forbidden.get("args_constraints", {}), True):
                return "deny", "forbidden_action", c, None
        allowed = next((a for a in c["allowed_actions"] if a["tool"] == tool_name and constraints_ok(action["args"], a["args_constraints"], a.get("allow_extra_args", False))), None)
        if not allowed or tool_name not in TOOLS:
            return "deny", "no_matching_allowed_action", c, None
        for mode in ("read", "write"):
            touched = list(action["paths"][mode])
            # Never trust a caller to enumerate path arguments correctly.
            touched += [action["args"][arg] for arg, access in TOOLS[tool_name]["paths"].items() if access == mode]
            for path in touched:
                if not any(matches(normal(path), p) for p in c["allowed_paths"][mode]):
                    return "deny", "path_outside_scope", c, None
        used = [e for e in entries if e["kind"] == "decision" and e.get("contract_id") == c["id"] and e.get("contract_version") == c["version"] and e.get("decision") == "allow"]
        if action["spend"] > 0 or len(used) >= c["limits"]["max_calls"]:
            return "deny", "limit_exceeded", c, None
        exact = digest({k: action[k] for k in ("agent", "tool", "args", "paths", "spend")})
        consumed = {e.get("approval_ref") for e in entries if e["kind"] == "decision" and e.get("decision") == "allow"}
        one_time = next((e for e in entries if e["kind"] == "approval" and e.get("scope") == "action" and e.get("contract_id") == c["id"] and e.get("contract_version") == c["version"] and e.get("action_hash") == exact and e["seq"] not in consumed), None)
        prompt = allowed["class"] in c["requires_approval"] or tool_name in ("asset.accept", "scope.select", "concept.select", "triage.close")
        if prompt:
            if one_time:
                return "allow", "one_time_approval_consumed", c, one_time["seq"]
            never_auto = tool_name in ("asset.accept", "scope.select", "concept.select") or (tool_name == "triage.close" and action["args"].get("severity") not in ("S2", "S3"))
            if c.get("approval_mode", "each") == "approve_all" and not never_auto and allowed["class"] in c["requires_approval"]:
                return "allow", "approve_all", c, approval["seq"]
            return "needs_approval", "human_approval_required", c, None
        return "allow", "within_contract", c, None

    def check(self, action):
        try:
            with self._lock():
                entries = self._entries()
                try:
                    decision, reason, c, ref = self._evaluate(action, entries)
                except (ValueError, KeyError, TypeError, OSError, ValidationError) as error:
                    decision, reason, c, ref = "deny", str(error), None, None
                if reason == "approve_all":
                    self._append("approval", scope="auto_resolution", contract_id=c["id"], contract_version=c["version"],
                                 approval_ref=ref, resolved_by="approve_all", quote=next(e["quote"] for e in entries if e["seq"] == ref))
                record = self._append("decision", action=action, agent=action.get("agent"), actor_type="ai", actor=action.get("agent"),
                                      contract_id=c["id"] if c else action.get("contract_id"), contract_version=c["version"] if c else None,
                                      decision=decision, outcome=decision, reason=reason, approval_ref=ref,
                                      content_hash=c["content_hash"] if c else None,
                                      approval_mode=c.get("approval_mode", "each") if c else None,
                                      resolved_by="approve_all" if reason == "approve_all" else None)
                return {"decision": decision, "reason": reason, "audit_seq": record["seq"]}
        except (OSError, ValueError, KeyError, TypeError):
            return {"decision": "deny", "reason": "audit_unavailable", "audit_seq": None}

    def approve_action(self, action, *, approver, quote):
        if approver != "johnathan" or not quote.strip():
            raise ValueError("Johnathan's explicit approval is required")
        with self._lock():
            entries = self._entries()
            outcome, _, c, _ = self._evaluate(action, entries)
            if outcome != "needs_approval":
                raise ValueError("only a pending approvable action can be approved")
            # Exact submitted action and active version, never a class-wide grant.
            return self._append("approval", scope="action", actor_type="human", actor=approver,
                                quote=quote, contract_id=c["id"], contract_version=c["version"],
                                action_hash=digest({k: action[k] for k in ("agent", "tool", "args", "paths", "spend")}))
