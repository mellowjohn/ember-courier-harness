"""Contract-gated intake; bug caches are data, audit records are authoritative."""
from copy import deepcopy
from difflib import SequenceMatcher
from hashlib import sha256
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker
from .core import SCHEMA_DIR, canonical, digest, normal

FINDING_SCHEMA = json.loads((SCHEMA_DIR / "finding.schema.json").read_text())
AREAS = {
    "Engine": {"rendering", "physics", "crash", "performance", "engine", "engine_code"},
    "Editor": {"tools", "editor", "level_editing", "world_editing", "asset_import"},
    "QA": {"repro", "verification", "regression_tests"},
    "Narrative": {"dialogue", "quest_text", "lore", "lore_consistency"},
    "Concept Artist": {"visual_look", "vfx", "palette", "palette_mismatch", "concept"},
    "Herald": {"store_pages", "announcements", "public_posts"},
    "Comms": {"messages", "community", "messages_to_users"},
    "Systems Designer": {"balance", "crafting", "loot", "progression"},
}


def tag(value):
    return re.sub(r"[\s-]+", "_", (value or "").strip().casefold())


def route(area):
    owner = next((name for name, values in AREAS.items() if tag(area) in values), "Hack Lead")
    allowed = owner not in ("Engine", "Herald", "Comms", "Hack Lead")
    return {"owner": owner, "code_fix_allowed": allowed,
            "reason": "engine_pause" if owner == "Engine" else "non_code_work" if owner in ("Herald", "Comms") else "needs_assignment" if owner == "Hack Lead" else "within_approved_fix_scope_only"}


def normalize_log(text):
    text = re.sub(r"\d{4}-\d\d-\d\d[T ][0-9:.+Z-]+", "", text)
    text = re.sub(r"0x[0-9a-fA-F]+", "<address>", text)
    text = re.sub(r"\d+", "#", text)
    return " ".join(text.casefold().split())


def fingerprint(finding):
    if finding["source"] == "log":
        subsystem = tag(finding.get("subsystem") or finding.get("area"))
        frames = finding.get("stack_frames") or finding.get("log_excerpt", "").splitlines()
        detail = [normalize_log(x) for x in frames[:3] if x.strip()]
        if finding.get("error_code"):
            detail = [normalize_log(finding["error_code"])]
        return digest(["log", subsystem, detail]) if subsystem and detail else None
    values = [tag(finding.get("area")), tag(finding.get("symptom_tag")), finding.get("build_family") or finding.get("build_id")]
    return digest(["code_review" if finding["source"] == "code_review" else "visual_playtest", *values]) if all(values) else None


def seal(record, seq):
    record.update(status_basis=seq, updated_seq=seq)
    record["record_hash"] = digest({k: v for k, v in record.items() if k != "record_hash"})
    return record


def records(entries, root=None):
    result = {}
    for event in entries:
        if event.get("detail", {}).get("scope") == "bug_intake" and (root is None or event.get("intake_root") == str(root)):
            for record in event.get("records", []):
                if digest({k: v for k, v in record.items() if k != "record_hash"}) != record["record_hash"] or record["status_basis"] != event["seq"]:
                    raise ValueError("bug record hash or status basis mismatch")
                result[record["id"]] = deepcopy(record)
        elif event["kind"] == "state_transition" and event.get("status") == "closed" and event.get("bug_id") in result:
            bug = result[event["bug_id"]]
            bug["state"] = "closed"
            seal(bug, event["seq"])
    return result


def canonical_bug_id(entries, bug_id):
    bugs, seen = records(entries), set()
    while bug_id in bugs and bugs[bug_id].get("duplicate_of"):
        if bug_id in seen:
            raise ValueError("duplicate cycle")
        seen.add(bug_id)
        bug_id = bugs[bug_id]["duplicate_of"]
    return bug_id


def next_bug_id(entries):
    known = set(records(entries)) | {e["bug_id"] for e in entries if isinstance(e.get("bug_id"), str)} | {e["bug_attempt"]["bug_id"] for e in entries if e.get("bug_attempt")}
    number = max((int(b[4:]) for b in known if re.fullmatch(r"BUG-[0-9]+", b)), default=0) + 1
    return f"BUG-{number:04d}"


def check_evidence(bug, root):
    expected_root = Path(root) / "evidence"
    for item in bug["evidence"]:
        path = Path(normal(item["path"]))
        if path.parent != expected_root or path.name != item["sha256"] + ".bin" or sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("intake evidence copy hash or path mismatch")


def classify(record, reviewed=False):
    missing = [key for key in ("build_id", "expected", "actual", "frequency", "evidence", "area") if not record.get(key)]
    if record["source"] == "code_review":
        missing.append("independent_repro")
    log_crash = record["source"] == "log" and (record.get("impact") in ("crash", "hang", "data_loss", "blocks_demo") or tag(record.get("area")) == "crash") and record.get("log_excerpt", "").strip()
    if not log_crash and not record.get("steps"):
        missing.append("steps")
    record["completeness"] = {"complete": not missing, "missing": missing}
    record["route"] = route(record.get("area"))
    if reviewed:
        record["severity_review_required"] = False
    record["state"] = "needs_repro" if missing else "new" if record["severity_review_required"] else "triaged"
    record["owner"] = "QA" if missing or record["severity_review_required"] else record["route"]["owner"]
    severity = record["severity"] or record["severity_proposed"]
    record["priority"] = 0 if severity == "S0" else 1 if severity == "S1" and record["demo_impact"] else 2 if severity == "S1" else 3 if severity == "S2" and record["demo_impact"] else 4 if severity == "S2" else 5
    return record


def merge_records(a, b):
    if a["route"] != b["route"]:
        raise ValueError("conflicting routes require explicit classification before merging")
    oldest, duplicate = sorted(deepcopy((a, b)), key=lambda x: x["created_seq"])
    oldest["evidence"] = list({(e["path"], e["sha256"]): e for e in oldest["evidence"] + duplicate["evidence"]}.values())
    oldest["finding_refs"] = list(dict.fromkeys(oldest["finding_refs"] + duplicate["finding_refs"]))
    oldest["duplicate_count"] += 1 + duplicate["duplicate_count"]
    severity = min(x["severity"] or x["severity_proposed"] for x in (oldest, duplicate))
    oldest.update(severity_proposed=severity, severity=severity,
                  severity_review_required=any(x["severity_review_required"] for x in (oldest, duplicate)),
                  demo_impact=oldest["demo_impact"] or duplicate["demo_impact"])
    if oldest["severity_review_required"]:
        oldest.update(severity=None, severity_basis="merged_proposal")
    classify(oldest)
    duplicate.update(state="duplicate", duplicate_of=oldest["id"], owner=oldest["owner"])
    return oldest, duplicate


class Intake:
    def __init__(self, harness, root):
        self.h = harness
        self.root = Path(normal(str(root)))
        if self.root.is_relative_to(harness.root) or harness.root.is_relative_to(self.root):
            raise ValueError("intake workspace must be separate from harness authority files")

    def _contract(self, cid, reviewer=False):
        active = self.h._active(self.h._entries())
        if cid not in active:
            raise ValueError("active approved intake contract required")
        c = self.h._authority(active[cid], active)
        if reviewer and not (c.get("extensions", {}).get("orchestration", {}).get("role") == "verifier" and c.get("extensions", {}).get("triage", {}).get("review_role") == "QA"):
            raise ValueError("approved QA reviewer contract required")
        return c

    def _gate(self, cid, tool, args, read=None, write=None):
        c = self._contract(cid)
        action = {"agent": c["agent"], "contract_id": cid, "tool": tool, "args": args,
                  "paths": {"read": [str(x) for x in (read or [])], "write": [str(x) for x in (write or [])]}, "spend": 0}
        decision = self.h.check(action)
        if decision["decision"] != "allow":
            raise ValueError("intake action denied: " + decision["reason"])
        return c, decision

    def list(self):
        return sorted(records(self.h._entries(), self.root.as_posix()).values(), key=lambda b: (b["priority"], b["created_seq"]))

    def get(self, bug_id):
        bugs = records(self.h._entries(), self.root.as_posix())
        if bug_id not in bugs:
            raise ValueError("bug not found in intake workspace")
        return bugs[bug_id]

    def _commit(self, cid, decision, operation, changed, *, event_kind="state_transition", **extra):
        entries = self.h._entries()
        for bug in changed:
            seal(bug, len(entries) + 1)
        entry = self.h._append(event_kind, detail={"scope": "bug_intake"}, operation=operation,
                               intake_root=self.root.as_posix(), contract_id=cid, contract_version=decision["contract_version"],
                               agent=decision["agent"], decision_seq=decision["seq"], records=changed, **extra)
        warnings = []
        for bug in changed:
            try:
                path = self.root / "bugs" / (bug["id"] + ".json")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(canonical(bug))
            except OSError as error:
                warnings.append(str(error))
        return {"bugs": changed, "status_basis": entry["seq"], "cache_warnings": warnings}

    def ingest(self, source, *, contract_id, bug_id=None, expected_hash=None):
        source = normal(str(source))
        self._gate(contract_id, "triage.inspect", {"path": source})
        if Path(source).stat().st_size > 128 * 1024:
            raise ValueError("finding exceeds 128 KiB")
        raw = Path(source).read_bytes()
        if len(raw) > 128 * 1024:
            raise ValueError("finding exceeds 128 KiB")
        finding = json.loads(raw)
        Draft202012Validator(FINDING_SCHEMA, format_checker=FormatChecker()).validate(finding)
        if finding.get("review_provenance"):
            from .muse_reviews import validate_finding
            validate_finding(self.h, finding)
        if not finding["summary"].strip() or any(not step.strip() for step in finding.get("steps", [])):
            raise ValueError("summary and supplied steps cannot be blank")
        entries = self.h._entries()
        existing = records(entries, self.root.as_posix())
        prior = existing.get(bug_id) if bug_id else None
        if bug_id and (not prior or prior["state"] in ("duplicate", "closed") or prior["record_hash"] != expected_hash):
            raise ValueError("update requires the current canonical open bug hash")
        assigned = bug_id or next_bug_id(entries)
        path = self.root / "bugs" / (assigned + ".json")
        if not prior and path.exists():
            raise ValueError("untracked bug cache collision; will not overwrite")
        copies = [(normal(e["path"]), e["sha256"], self.root / "evidence" / (e["sha256"] + ".bin")) for e in finding.get("evidence", [])]
        actor, gated = self._gate(contract_id, "triage.ingest", {"source": source, "dest": path.as_posix()}, read=[source] + [x[0] for x in copies], write=[path.as_posix()] + [x[2].as_posix() for x in copies])
        with self.h._lock():
            current = records(self.h._entries(), self.root.as_posix())
            if not prior and assigned != next_bug_id(self.h._entries()) or prior and current[assigned]["record_hash"] != expected_hash:
                raise ValueError("intake changed concurrently; retry against the latest state")
            if Path(source).read_bytes() != raw:
                raise ValueError("finding changed after inspection")
            evidence = []
            for original, expected, destination in copies:
                data = Path(original).read_bytes()
                if sha256(data).hexdigest() != expected:
                    raise ValueError("source evidence hash mismatch")
                if destination.exists() and destination.read_bytes() != data:
                    raise ValueError("evidence overwrite refused")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                evidence.append({"path": destination.as_posix(), "sha256": expected, "source_path": original})
            impact_severity = {"crash": "S0", "hang": "S0", "data_loss": "S0", "blocks_demo": "S0", "core_loop_broken": "S1", "degraded": "S2", "cosmetic": "S3"}.get(finding.get("impact"))
            if finding["source"] == "log" and tag(finding.get("area")) == "crash":
                impact_severity = "S0"
            proposal = min([x for x in (finding.get("severity"), impact_severity) if x] or ["S2"])
            demo = finding.get("demo_impact", False)
            review_required = proposal == "S0" or bool(prior and prior["severity_proposed"] == "S0" and proposal != "S0") or bool(prior and (prior["demo_impact"] or demo) and (prior["severity_proposed"] != proposal or prior["demo_impact"] != demo))
            reviewed = bool(prior and prior.get("severity_basis") == "qa_review" and not prior["severity_review_required"] and prior["severity"] == proposal and prior["demo_impact"] == demo)
            bug = {"id": assigned, "title": finding["summary"].strip(), "source": finding["source"], "timestamp": finding.get("timestamp") or self.h.clock().isoformat(),
                   **{key: finding[key].strip() if isinstance(finding.get(key), str) else deepcopy(finding.get(key)) for key in ("build_id", "area", "symptom_tag", "expected", "actual", "frequency", "impact")},
                   "steps": finding.get("steps", []), "log_excerpt": finding.get("log_excerpt", ""), "evidence": evidence,
                   "severity_proposed": proposal, "severity": proposal if reviewed or not review_required else None,
                   "severity_basis": "qa_review" if reviewed else "reported_proposal" if finding.get("severity") == proposal else "rule_based_proposal",
                   "severity_review_required": review_required and not reviewed, "demo_impact": demo,
                   "fingerprint": fingerprint(finding), "duplicate_of": None, "duplicate_count": prior["duplicate_count"] if prior else 0,
                   "created_by": prior["created_by"] if prior else actor["agent"],
                   "created_seq": prior["created_seq"] if prior else len(self.h._entries()) + 1,
                   "finding_refs": (prior["finding_refs"] if prior else []) + [digest(finding)]}
            if finding.get("review_provenance"):
                bug["review_provenance"] = deepcopy(finding["review_provenance"])
            if prior:
                for field in ("reopen_count", "last_reopened_seq", "last_closure_seq"):
                    if field in prior:
                        bug[field] = prior[field]
                bug["evidence"] = list({(e["path"], e["sha256"]): e for e in prior["evidence"] + evidence}.values())
            classify(bug)
            candidates = []
            for other in current.values():
                if other["id"] == assigned or other["state"] in ("duplicate", "closed", "wontfix"):
                    continue
                if bug["fingerprint"] and bug["fingerprint"] == other["fingerprint"]:
                    candidates.append({"bug_id": other["id"], "reason": "fingerprint"})
                elif tag(bug.get("area")) and tag(bug.get("area")) == tag(other.get("area")) and SequenceMatcher(None, bug["title"].casefold(), other["title"].casefold()).ratio() >= 0.85:
                    candidates.append({"bug_id": other["id"], "reason": "text_similarity_hint"})
            bug["duplicate_candidates"] = candidates
            decision = next(e for e in self.h._entries() if e["seq"] == gated["audit_seq"])
            return self._commit(contract_id, decision, "update" if prior else "ingest", [bug], finding=finding, finding_ref=digest(finding))

    def _reviewer(self, contract_id, bugs):
        c = self._contract(contract_id, reviewer=True)
        if any(c["agent"] == bug["created_by"] for bug in bugs):
            raise ValueError("reviewer must differ from intake author")
        return c

    def confirm_duplicate(self, bug_id, target_id, *, contract_id, bug_hash, target_hash, note):
        a, b = self.get(bug_id), self.get(target_id)
        self._reviewer(contract_id, [a, b])
        if not isinstance(note, str) or not note.strip():
            raise ValueError("reviewer note required")
        paths = [self.root / "bugs" / (bug["id"] + ".json") for bug in (a, b)]
        _, gate = self._gate(contract_id, "triage.confirm_duplicate", {"path": paths[0].as_posix(), "target": paths[1].as_posix(), "note": note})
        with self.h._lock():
            a, b = self.get(bug_id), self.get(target_id)
            self._reviewer(contract_id, [a, b])
            if a["record_hash"] != bug_hash or b["record_hash"] != target_hash or a["id"] == b["id"] or any(x["state"] in ("duplicate", "closed", "reopened") for x in (a, b)):
                raise ValueError("duplicate confirmation requires current open records")
            if not any(x["bug_id"] == b["id"] for x in a["duplicate_candidates"]) and not any(x["bug_id"] == a["id"] for x in b["duplicate_candidates"]):
                raise ValueError("no duplicate candidate to confirm")
            from .attempts import status as attempt_status
            if any(attempt_status(self.h._entries(), bug["id"])["attempts_started"] for bug in (a, b)):
                raise ValueError("attempt history requires owner reconciliation before a late merge")
            oldest, duplicate = merge_records(a, b)
            decision = next(e for e in self.h._entries() if e["seq"] == gate["audit_seq"])
            return self._commit(contract_id, decision, "confirm_duplicate", [oldest, duplicate], reviewer_note={"reviewer": decision["agent"], "role": "QA", "note": note, "label": "self_reported"})

    def review_severity(self, bug_id, *, contract_id, expected_hash, severity, demo_impact, note):
        bug = self.get(bug_id)
        self._reviewer(contract_id, [bug])
        if severity not in ("S0", "S1", "S2", "S3") or type(demo_impact) is not bool or not isinstance(note, str) or not note.strip():
            raise ValueError("severity, demo impact and reviewer note required")
        _, gate = self._gate(contract_id, "triage.review_severity", {"path": (self.root / "bugs" / (bug_id + ".json")).as_posix(), "severity": severity, "demo_impact": demo_impact, "note": note})
        with self.h._lock():
            bug = self.get(bug_id)
            self._reviewer(contract_id, [bug])
            if bug["record_hash"] != expected_hash or bug["state"] in ("duplicate", "closed", "reopened"):
                raise ValueError("severity review requires current open bug hash")
            bug.update(severity=severity, severity_proposed=severity, demo_impact=demo_impact, severity_basis="qa_review")
            classify(bug, reviewed=True)
            decision = next(e for e in self.h._entries() if e["seq"] == gate["audit_seq"])
            return self._commit(contract_id, decision, "review_severity", [bug], reviewer_note={"reviewer": decision["agent"], "role": "QA", "note": note, "label": "self_reported"})

    def reopen(self, bug_id, *, contract_id, expected_hash, expected_state_hash, reason):
        from .reopening import reopen
        return reopen(self, bug_id, contract_id=contract_id, expected_hash=expected_hash,
                      expected_state_hash=expected_state_hash, reason=reason)

    def snapshot(self, bug_id, fix_contract_id):
        with self.h._lock():
            canonical_id = canonical_bug_id(self.h._entries(), bug_id)
            bug = self.get(canonical_id)
            if bug["state"] != "triaged" or bug["severity_review_required"] or not bug["route"]["code_fix_allowed"]:
                raise ValueError("bug is not ready for an in-scope code fix")
            check_evidence(bug, self.root)
            self.h._path(fix_contract_id, 1)
            path = self.h.root / "triage" / "fix_contracts" / fix_contract_id / "bug_snapshot.json"
            data = canonical(bug)
            if path.exists() and path.read_bytes() != data:
                raise ValueError("frozen snapshot cannot be overwritten")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            ref = sha256(data).hexdigest()
            event = self.h._append("bug_snapshot", bug_id=canonical_id, fix_contract_id=fix_contract_id, source_hash=bug["record_hash"], snapshot_path=path.as_posix(), snapshot_sha256=ref)
            return {"id": canonical_id, "path": path.as_posix(), "sha256": ref, "status_basis": event["seq"]}


def fix_identity_allowed(entries, bug_id, snapshot_input=None):
    canonical_id = canonical_bug_id(entries, bug_id)
    if canonical_id != bug_id:
        raise ValueError("fix snapshot must use the canonical duplicate bug ID")
    bug = records(entries).get(bug_id)
    if bug and (bug["state"] != "triaged" or bug["severity_review_required"] or not bug["route"]["code_fix_allowed"]):
        raise ValueError("intake bug is not ready for an in-scope code fix")
    if snapshot_input is not None:
        reopened = max((e["seq"] for e in entries if e.get("operation") == "reopen" and canonical_bug_id(entries, e.get("bug_id")) == bug_id), default=0)
        if reopened and not any(e["kind"] == "bug_snapshot" and e["seq"] > reopened and
                e["snapshot_path"] == snapshot_input.get("path") and e["snapshot_sha256"] == snapshot_input.get("sha256") and
                e["source_hash"] == bug["record_hash"] for e in entries):
            raise ValueError("new fix requires a fresh current snapshot after reopening")
    if bug:
        root = next(e["intake_root"] for e in entries if e.get("detail", {}).get("scope") == "bug_intake" and any(r["id"] == bug_id for r in e["records"]))
        check_evidence(bug, root)


def validate_history(harness, entries):
    bugs = records(entries)
    for event in entries:
        if event.get("detail", {}).get("scope") == "bug_intake":
            decision = next((e for e in entries if e["seq"] == event["decision_seq"]), {})
            tools = {"ingest": "triage.ingest", "update": "triage.ingest", "confirm_duplicate": "triage.confirm_duplicate", "reconcile_duplicates": "triage.confirm_duplicate", "reopen": "triage.reopen", "review_severity": "triage.review_severity"}
            if decision.get("decision") != "allow" or decision.get("action", {}).get("tool") != tools.get(event["operation"]):
                raise ValueError("bug mutation lacks its matching allowed intake decision")
            if event.get("finding", {}).get("review_provenance"):
                from .muse_reviews import validate_finding
                validate_finding(harness, event["finding"], entries[:event["seq"] - 1])
            for bug in event["records"]:
                canonical_bug_id(entries, bug["id"])
                check_evidence(bug, event["intake_root"])
        elif event["kind"] == "bug_snapshot":
            harness._path(event["fix_contract_id"], 1)
            expected = harness.root / "triage" / "fix_contracts" / event["fix_contract_id"] / "bug_snapshot.json"
            if event["snapshot_path"] != expected.as_posix() or sha256(expected.read_bytes()).hexdigest() != event["snapshot_sha256"]:
                raise ValueError("frozen intake snapshot hash or path mismatch")
            snap = json.loads(expected.read_text(encoding="utf-8"))
            if snap["record_hash"] != event["source_hash"] or snap["id"] != event["bug_id"]:
                raise ValueError("snapshot differs from its intake source")
    from .reopening import validate_history as validate_reopening
    validate_reopening(harness, entries)
    return len(bugs)
