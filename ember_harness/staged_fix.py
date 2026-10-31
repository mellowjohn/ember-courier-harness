"""Trusted local adapters for a staged fix. Test code is trusted, not sandboxed."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

from .core import canonical, digest, normal


def run_test(harness, action, *, timeout=30):
    """Gate a fixed Python test script, capture its actual output and byte inputs."""
    if action.get("tool") != "test.run":
        raise ValueError("test.run required")
    decision = harness.check(action)
    if decision["decision"] != "allow":
        raise ValueError("test execution denied: " + decision["reason"])
    script = normal(action["args"]["script"])
    active = harness._active(harness._entries())
    c = harness._authority(active[action["contract_id"]], active)
    pinned = next((i.get("sha256") for i in c["inputs"] if i.get("path") and normal(i["path"]) == script), None)
    if not pinned or sha256(Path(script).read_bytes()).hexdigest() != pinned:
        raise ValueError("test script must be pinned to approved input bytes")
    paths = sorted(set(action["paths"]["read"] + [script]))
    before = {normal(p): sha256(Path(p).read_bytes()).hexdigest() for p in paths}
    completed = subprocess.run([sys.executable, "-I", "-B", script], cwd=str(Path(script).parent),
                               capture_output=True, text=True, timeout=timeout)
    after = {normal(p): sha256(Path(p).read_bytes()).hexdigest() for p in paths}
    payload = {"script": script, "script_sha256": pinned, "returncode": completed.returncode,
               "stdout": completed.stdout, "stderr": completed.stderr, "inputs": before, "inputs_unchanged": before == after}
    reference = digest(payload)
    with harness._lock():
        folder = harness.root / "executions"
        folder.mkdir(exist_ok=True)
        (folder / f"{reference}.json").write_bytes(canonical(payload))
        entry = harness._append("execution", contract_id=c["id"], contract_version=c["version"],
                                agent=c["agent"], decision_seq=decision["audit_seq"], output_ref=reference,
                                returncode=completed.returncode, inputs_unchanged=before == after)
    return {"execution_seq": entry["seq"], "decision_seq": decision["audit_seq"], "output_ref": reference, **payload}


def execution(harness, seq):
    entries = harness._entries()
    event = next((e for e in entries if e["seq"] == seq and e["kind"] == "execution"), None)
    if event is None:
        raise ValueError("captured execution required")
    payload = json.loads((harness.root / "executions" / (event["output_ref"] + ".json")).read_text(encoding="utf-8"))
    if digest(payload) != event["output_ref"] or not payload["inputs_unchanged"]:
        raise ValueError("execution bytes changed or were tampered with")
    decision = next((e for e in entries if e["seq"] == event["decision_seq"]), {})
    if decision.get("kind") != "decision" or decision.get("decision") != "allow" or decision.get("contract_id") != event["contract_id"] or decision.get("contract_version") != event["contract_version"]:
        raise ValueError("execution is not bound to its allowed decision")
    return event, payload


def close_bug(harness, *, bug_id, severity, fix_id, verifier_id, source_path, pre_seq, post_seq, review_seq, verify_seq, build, pre_build, repo):
    """Close only the staged reproducible bug; all witnesses are captured runs.

    Review is an automated structural check under a distinct identity. It is
    not presented as an independent human or AI peer review.
    """
    from .contract_lock import git, verify as lock
    active = harness._active(harness._entries())
    fix = harness._authority(active[fix_id], active)
    verifier = harness._authority(active[verifier_id], active)
    if not active[fix_id].get("bug_attempt") or fix.get("extensions", {}).get("orchestration", {}).get("role") not in ("coding", "worker"):
        raise ValueError("tracked approved fix attempt required for bug closure")
    from .attempts import action_block
    attempt_reason = action_block(harness._entries(), active[fix_id])
    if attempt_reason and attempt_reason != "attempt_succeeded":
        raise ValueError(attempt_reason)
    from .attempts import status as attempt_status
    current_attempts = attempt_status(harness._entries(), bug_id)
    reopened_seq = current_attempts.get("last_reopened_seq", 0)
    if reopened_seq:
        attempt = next((a for a in current_attempts["attempts"] if a["contract_id"] == fix_id), None)
        if not attempt or attempt["started_seq"] <= reopened_seq or attempt["status"] != "running":
            raise ValueError("fresh approved fix attempt required after reopening")
        if min(pre_seq, post_seq, review_seq, verify_seq) <= reopened_seq:
            raise ValueError("fresh closure evidence required after reopening")
    if fix["agent"] == verifier["agent"] or verifier["allowed_paths"]["write"]:
        raise ValueError("verifier must differ from author and have no write paths")
    snapshot = next((item for item in fix["inputs"] if item["name"] == "bug_snapshot"), None)
    if not snapshot or sha256(Path(snapshot["path"]).read_bytes()).hexdigest() != snapshot.get("sha256"):
        raise ValueError("approved frozen bug snapshot required")
    bug = json.loads(Path(snapshot["path"]).read_text(encoding="utf-8"))
    if bug.get("id") != bug_id or bug.get("severity") != severity:
        raise ValueError("closure bug/severity differs from approved snapshot")
    runs = [execution(harness, seq) for seq in (pre_seq, post_seq, review_seq, verify_seq)]
    pre, post, review, qa = [payload for _, payload in runs]
    if runs[0][0]["contract_id"] not in (fix_id, verifier_id) or [event["contract_id"] for event, _ in runs[1:]] != [fix_id, verifier_id, verifier_id]:
        raise ValueError("test/review witnesses are bound to the wrong contract")
    if any(event["contract_version"] != (fix if event["contract_id"] == fix_id else verifier)["version"] for event, _ in runs):
        raise ValueError("stale execution contract version")
    if not pre_seq < post_seq < review_seq < verify_seq:
        raise ValueError("repro, fix, review and verification must occur in order")
    if pre["returncode"] != 1 or "AssertionError" not in pre["stderr"] or any(p["returncode"] != 0 for p in (post, review, qa)):
        raise ValueError("requires a failing assertion before the fix and passing checks after")
    if "REVIEW PASS" not in review["stdout"] or "OK" not in post["stderr"] or "OK" not in qa["stderr"]:
        raise ValueError("captured outputs must show passing review and regression")
    if pre["script_sha256"] != post["script_sha256"] or post["script_sha256"] != qa["script_sha256"]:
        raise ValueError("regression test changed between repro and verification")
    path = normal(source_path)
    actual = sha256(Path(path).read_bytes()).hexdigest()
    relative = Path(path).relative_to(Path(repo).resolve()).as_posix()
    triage = verifier.get("extensions", {}).get("triage", {})
    verification_repo, repro_repo = triage.get("verification_repo"), triage.get("repro_repo")
    verified_path = normal(str(Path(verification_repo) / relative)) if verification_repo else path
    before_path = normal(str(Path(repro_repo) / relative)) if repro_repo and runs[0][0]["contract_id"] == verifier_id else path
    if pre["inputs"].get(before_path) == actual or post["inputs"].get(path) != actual or any(p["inputs"].get(verified_path) != actual for p in (review, qa)):
        raise ValueError("evidence does not describe the current fixed source")
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    if build != head or sha256(git(repo, "show", f"{head}:{relative}")).hexdigest() != actual:
        raise ValueError("named verification build does not match current source commit")
    if sha256(git(repo, "show", f"{pre_build}:{relative}")).hexdigest() != pre["inputs"].get(before_path):
        raise ValueError("pre-fix source does not match named pre-fix commit")
    for commit in (pre_build, head):
        relative_test = Path(post["script"]).relative_to(Path(repo).resolve()).as_posix()
        if sha256(git(repo, "show", f"{commit}:{relative_test}")).hexdigest() != post["script_sha256"]:
            raise ValueError("regression must be unchanged on both named commits")
    if verification_repo:
        for checkout, expected_build in ((verification_repo, build), (repro_repo, pre_build)):
            if not checkout or git(checkout, "rev-parse", "HEAD").decode().strip() != expected_build or git(checkout, "status", "--porcelain"):
                raise ValueError("verifier checkouts must be clean and on named commits")
    index = json.loads((harness.root / "triage" / "regression" / "index.json").read_text(encoding="utf-8"))
    if not any(item.get("bug_id") == bug_id and item.get("test_path") == post["script"] and item.get("build_introduced") == head for item in index):
        raise ValueError("registered regression test for the named build required")
    if not lock(harness.root, repo=repo, base=pre_build)["ok"]:
        raise ValueError("contract-lock failed")
    for contract in (fix, verifier):
        for action_id in contract["required_evidence"]:
            if harness.step_status(contract["id"], action_id)["status"] != "complete":
                raise ValueError("required fix/verifier evidence is incomplete")
    if attempt_status(harness._entries(), bug_id)["status"] == "closed":
        raise ValueError("bug is already closed")
    action = {"agent": verifier["agent"], "contract_id": verifier_id, "tool": "triage.close",
              "args": {"bug_id": bug_id, "severity": severity}, "paths": {"read": [], "write": []}, "spend": 0}
    decision = harness.check(action)
    if decision["decision"] != "allow":
        return {"status": decision["decision"], "reason": decision["reason"], "status_basis": decision["audit_seq"]}
    with harness._lock():
        current = harness._active(harness._entries())
        for contract in (fix, verifier):
            if contract["id"] not in current or harness._authority(current[contract["id"]], current)["version"] != contract["version"]:
                raise ValueError("closure contract changed before state transition")
        if sha256(Path(path).read_bytes()).hexdigest() != actual:
            raise ValueError("source changed before closure")
        if attempt_status(harness._entries(), bug_id)["status"] == "closed":
            raise ValueError("bug is already closed")
        latest = attempt_status(harness._entries(), bug_id)
        if latest.get("last_reopened_seq", 0) != reopened_seq:
            raise ValueError("bug lifecycle changed before closure")
        record = harness._append("state_transition", bug_id=bug_id, severity=severity, status="closed", build=build,
                                 fix_contract_id=fix_id, fix_version=fix["version"], verifier_contract_id=verifier_id,
                                 verifier_version=verifier["version"],
                                 author=fix["agent"], reviewer=verifier["agent"], review_kind="automated_structural_check",
                                 execution_seqs=[pre_seq, post_seq, review_seq, verify_seq], decision_seq=decision["audit_seq"])
    return {"status": "closed", "status_basis": record["seq"], "build": build, "review_kind": record["review_kind"]}
