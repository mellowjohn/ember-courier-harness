"""Read-only contract history and local Git verifier. Never runs hooks or writes Git."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

from .core import Harness, canonical, content_hash, digest, matches, normal, subset, validate
from .amendments import compile_proposal, record_path


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout


def trailers(message):
    required = ("Round", "Contract-Id", "Contract-Version", "Contract-Hash", "Subsystem")
    result = {}
    # Trailer block must be last, separated from the subject/body by a blank line.
    block = message.strip().split("\n\n")[-1]
    for line in block.splitlines():
        match = re.fullmatch(r"([A-Za-z-]+): (.+)", line)
        if match:
            if match[1] in result:
                raise ValueError("duplicate commit trailer")
            result[match[1]] = match[2]
    if any(key not in result for key in required):
        raise ValueError("commit requires Round, Contract-Id, Contract-Version, Contract-Hash and Subsystem trailers")
    if not result["Round"].isdecimal() or int(result["Round"]) < 1 or not result["Contract-Version"].isdecimal():
        raise ValueError("invalid numeric trailer")
    return result


def check_commit(contracts, repo, base, message, paths, branch, store_prefix="", blobs=None):
    """Check prospective staged changes or one existing non-merge commit."""
    meta = trailers(message)
    key = (meta["Contract-Id"], int(meta["Contract-Version"]))
    if key not in contracts:
        raise ValueError("commit references missing contract")
    c = contracts[key]
    if c["status"] == "draft" or c["content_hash"] != meta["Contract-Hash"]:
        raise ValueError("commit contract version/hash is not approved")
    if branch.startswith("contract/"):
        expected = f"contract/{c['id']}/v{c['version']}"
        if branch != expected:
            raise ValueError("wrong amendment branch")
        for path in paths:
            prefix = store_prefix.rstrip("/") + "/" if store_prefix else ""
            if not (path.startswith(prefix + f"contracts/{c['id']}/") or path.startswith(prefix + "approvals/")):
                raise ValueError("amendment branch touches files outside contracts/approvals")
    else:
        expected = f"round/{meta['Round']}/{c['id']}"
        if branch != expected:
            raise ValueError("worker commit is on the wrong branch")
        for relative in paths:
            path = normal(str(Path(repo) / relative))
            if not any(matches(path, pattern) for pattern in c["allowed_paths"]["write"]):
                raise ValueError(f"worker diff outside allowed write paths: {relative}")
            raw = blobs.get(relative) if blobs is not None else ((Path(repo) / relative).read_bytes() if (Path(repo) / relative).is_file() else b"")
            cap = c.get("extensions", {}).get("git", {}).get("thresholds", {}).get("max_plain_file_bytes", 1024 * 1024)
            if raw and len(raw) > cap:
                raise ValueError(f"plain Git file exceeds size guard: {relative}")
    triage = c.get("extensions", {}).get("triage", {})
    for field in ("bug_id", "author", "reviewer"):
        if field in triage and triage[field] not in message:
            raise ValueError(f"fix commit message missing {field}")
    if triage.get("author") and triage.get("author") == triage.get("reviewer"):
        raise ValueError("reviewer must differ from author")
    return meta


def asset_check(path, expected):
    raw = Path(path).read_bytes()
    pointer = re.fullmatch(rb"version https://git-lfs.github.com/spec/v1\r?\noid sha256:([0-9a-f]{64})\r?\nsize ([0-9]+)\r?\n?", raw)
    if pointer:
        if pointer[1].decode() != expected:
            raise ValueError("LFS pointer oid mismatch")
        return {"basis": "lfs_pointer", "label": "self_reported", "size": int(pointer[2])}
    if sha256(raw).hexdigest() != expected:
        raise ValueError("asset hash mismatch")
    return {"basis": "content", "label": "verified", "size": len(raw)}


def verify(store, *, repo=None, base=None, staged_message=None):
    """Return diagnostics. Schema, hashes, caches and Git data are all untrusted."""
    root = Path(store).resolve()
    errors, checks, assets = [], [], []
    if not root.is_dir():
        return {"name": "contract-lock", "ok": False, "errors": ["store does not exist"], "checks": []}
    h = Harness(root)
    try:
        entries = h._entries()
    except (ValueError, KeyError, OSError) as error:
        return {"name": "contract-lock", "ok": False, "errors": [f"audit: {error}"], "checks": []}
    approvals = {(e["contract_id"], e["contract_version"]): e for e in entries if e["kind"] == "approval" and e.get("scope") == "contract"}
    contracts = {}
    for path in sorted((root / "contracts").glob("*/v*.json")):
        try:
            c = json.loads(path.read_text(encoding="utf-8"))
            validate(c)
            key = (c["id"], c["version"])
            if path != h._path(*key):
                raise ValueError("identity differs from version filename")
            contracts[key] = c
            if c["status"] != "draft":
                if content_hash(c) != c["content_hash"]:
                    raise ValueError("content_hash mismatch")
                approval = approvals.get(key)
                if not approval or approval["actor"] != "johnathan" or approval["actor_type"] != "human" or approval["content_hash"] != c["content_hash"]:
                    raise ValueError("missing or mismatched audit approval")
                saved = json.loads((root / "approvals" / f"{c['id']}-v{c['version']}.json").read_text(encoding="utf-8"))
                if saved != approval:
                    raise ValueError("approval record differs from audit")
                state = next(v for v in h.history(c["id"]) if v["version"] == c["version"])
                if state["status"] != c["status"]:
                    raise ValueError("contract status differs from audit")
            checks.append(f"schema/hash/approval: {c['id']} v{c['version']}")
        except Exception as error:
            # jsonschema.ValidationError is intentionally included; one broken
            # file should not hide the rest of the report.
            errors.append(f"{path.relative_to(root)}: {error}")
    if not contracts:
        errors.append("no contracts found")
    for key in approvals:
        if key not in contracts:
            errors.append(f"approved contract file missing: {key}")
    for cid in sorted({key[0] for key in contracts}):
        versions = sorted(v for name, v in contracts if name == cid)
        if versions != list(range(1, max(versions) + 1)):
            errors.append(f"version gap: {cid}")
        if sum(contracts[cid, v]["status"] == "approved" for v in versions) > 1:
            errors.append(f"multiple approved versions: {cid}")
        for version in versions:
            c = contracts[cid, version]
            try:
                approval = approvals.get((cid, version))
                if version > 1:
                    old = contracts[cid, version - 1]
                    record = json.loads(record_path(h, cid, version).read_text(encoding="utf-8"))
                    event = approval or next(e for e in reversed(entries) if e["kind"] == "amendment_draft" and e.get("contract_id") == cid and e.get("contract_version") == version)
                    if record != event["amendment_record"]:
                        raise ValueError("amendment record differs from audit")
                    relative = Path(record["proposal_ref"]["path"])
                    if relative.is_absolute() or ".." in relative.parts:
                        raise ValueError("unsafe proposal reference")
                    proposal = json.loads((root / relative).read_text(encoding="utf-8"))
                    if digest(proposal) != record["proposal_ref"]["sha256"]:
                        raise ValueError("proposal hash mismatch")
                    historical = contracts.get((cid, proposal.get("rollback_to")))
                    rebuilt, computed, _ = compile_proposal(old, proposal, record["proposed_by"]["actor"], historical)
                    for field in ("from_version", "to_version", "from_hash", "draft_hash", "diff", "changed_fields", "widening", "widening_sha256", "affected_actions"):
                        if record[field] != computed[field]:
                            raise ValueError(f"amendment {field} mismatch")
                    resolved = deepcopy(rebuilt)
                    if "ttl_hours" in resolved["limits"]["time_window"] and approval:
                        from datetime import timedelta
                        from .core import timestamp
                        start = timestamp(c["approved_at"])
                        ttl = resolved["limits"]["time_window"]["ttl_hours"]
                        resolved["limits"]["time_window"] = {"not_before": start.isoformat(), "not_after": (start + timedelta(hours=ttl)).isoformat()}
                    if content_hash(resolved) != content_hash(c):
                        raise ValueError("contract differs from recomputed amendment")
                    if approval and record["to_hash"] != c["content_hash"]:
                        raise ValueError("amendment to_hash mismatch")
                    if proposal.get("rollback_to") and c["extensions"]["lineage"]["amendment_log"][-1].get("reason") != "rollback":
                        raise ValueError("rollback lineage missing")
                    if approval and record["widening"]["items"]:
                        seq = approval.get("widening_ack_seq")
                        ack = next((e for e in entries if e["seq"] == seq), {})
                        if (ack.get("scope") != "widening_ack" or ack.get("actor") != "johnathan" or ack.get("actor_type") != "human" or
                                ack.get("contract_id") != cid or ack.get("for_version") != version or ack.get("widening_sha256") != record["widening_sha256"] or
                                ack.get("reviewed_hash") != record["draft_hash"] or ack["seq"] >= approval["seq"]):
                            raise ValueError("missing or mismatched separate widening acknowledgement")
                if approval and approval.get("parent_id"):
                    parent = contracts[approval["parent_id"], approval["parent_version"]]
                    if not subset(c, parent) or c.get("art_direction") != parent.get("art_direction"):
                        raise ValueError("child exceeds approved parent")
            except Exception as error:
                errors.append(f"lineage/scope {cid} v{version}: {error}")
    for entry in entries:
        if entry["kind"] == "execution":
            try:
                reference = entry["output_ref"]
                if re.fullmatch(r"[0-9a-f]{64}", reference) is None:
                    raise ValueError("invalid execution reference")
                if digest(json.loads((root / "executions" / f"{reference}.json").read_bytes())) != reference:
                    raise ValueError("execution payload hash mismatch")
            except (ValueError, KeyError, OSError) as error:
                errors.append(f"execution audit #{entry['seq']}: {error}")
        for reference in entry.get("evidence_refs", []):
            try:
                if re.fullmatch(r"[0-9a-f]{64}", reference) is None:
                    raise ValueError("invalid evidence reference")
                raw = (root / "evidence" / f"{reference}.json").read_bytes()
                if sha256(raw).hexdigest() != reference or digest(json.loads(raw)) != reference:
                    raise ValueError("evidence payload hash mismatch")
            except (ValueError, OSError) as error:
                errors.append(f"evidence audit #{entry['seq']}: {error}")
    heads = {e["entry_hash"] for e in entries}
    try:
        from .intake import validate_history as validate_intake
        intake_count = validate_intake(h, entries)
        if intake_count:
            checks.append("intake decisions, canonical bug records, evidence copies and frozen snapshots")
    except Exception as error:
        errors.append(f"intake history: {error}")
        intake_count = 0
    try:
        from .attempts import validate_history
        attempt_states = validate_history(h, entries)
        if attempt_states:
            checks.append("per-bug attempt allocation, outcomes and owner escalation")
    except Exception as error:
        errors.append(f"attempt history: {error}")
        attempt_states = []
    try:
        from .muse_reviews import validate_history as validate_muse_reviews
        if validate_muse_reviews(h, entries):
            checks.append("Muse review captures, pinned inputs and unverified finding provenance")
    except Exception as error:
        errors.append(f"Muse review history: {error}")
    try:
        from .assets import validate_history as validate_assets
        if validate_assets(h, entries):
            checks.append("Concept snapshots, explicit owner selections, ingests and asset acceptances")
    except Exception as error:
        errors.append(f"Asset history: {error}")
    try:
        from .local_agent import validate_history as validate_agent
        if validate_agent(h, entries):
            checks.append("Local agent captures and approved inference decisions")
    except Exception as error:
        errors.append(f"Local agent history: {error}")
    try:
        from .owner_review import validate_history as validate_owner
        if validate_owner(h, entries):
            checks.append("Owner review packets, responses and exact approval receipts")
    except Exception as error:
        errors.append(f"Owner review history: {error}")
    for anchor in (root / "audit" / "anchors").glob("*.txt"):
        if anchor.read_text().strip() not in heads:
            errors.append(f"anchor not in audit chain: {anchor.name}")
    asset_root = Path(repo).resolve() if repo else root
    manifest = asset_root / "assets" / "manifest.json"
    if manifest.exists():
        try:
            records = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(records, dict):
                records = records["files"]
            for item in records:
                path = (asset_root / item["path"]).resolve()
                path.relative_to(asset_root)
                result = asset_check(path, item["sha256"])
                if result["size"] != item["size"]:
                    raise ValueError("manifest asset size mismatch")
                assets.append({"path": item["path"], **result})
        except Exception as error:
            errors.append(f"asset manifest: {error}")
    if repo is not None:
        try:
            repository = Path(repo).resolve()
            if not base:
                raise ValueError("Git checks require an explicit base ref")
            base_id = git(repository, "rev-parse", "--verify", f"{base}^{{commit}}").decode().strip()
            # Compare every previously tracked non-draft version to the actual
            # base blob, so deleting or replacing a whole history cannot hide it.
            try:
                store_relative = root.relative_to(repository).as_posix()
                if store_relative == ".":
                    store_relative = ""
            except ValueError:
                store_relative = None
            if store_relative is not None:
                prefix = store_relative + "/" if store_relative else ""
                listed = git(repository, "ls-tree", "-r", "--name-only", base_id, "--", prefix + "contracts").decode().splitlines()
                for name in listed:
                    if not re.search(r"/v[0-9]+\.json$", name):
                        continue
                    before = json.loads(git(repository, "show", f"{base_id}:{name}"))
                    if before["status"] == "draft":
                        continue
                    after = json.loads((repository / name).read_text(encoding="utf-8"))
                    if {k: v for k, v in before.items() if k != "status"} != {k: v for k, v in after.items() if k != "status"}:
                        raise ValueError(f"base approved bytes changed: {name}")
                    allowed = {"approved": {"approved", "superseded", "revoked"}, "superseded": {"superseded"}, "revoked": {"revoked"}}
                    if after["status"] not in allowed[before["status"]]:
                        raise ValueError(f"illegal base status transition: {name}")
            branch = git(repository, "branch", "--show-current").decode().strip()
            if staged_message is not None:
                paths = git(repository, "diff", "--cached", "--name-only", "--no-renames", "-z").decode().strip("\x00").split("\x00")
                if store_relative is not None:
                    for path in paths:
                        if (not store_relative or path.startswith(store_relative + "/")) and git(repository, "show", ":" + path) != (repository / path).read_bytes():
                            raise ValueError(f"staged store bytes differ from verified files: {path}")
                blobs = {}
                for path in [p for p in paths if p]:
                    try:
                        blobs[path] = git(repository, "show", ":" + path)
                    except subprocess.CalledProcessError:
                        blobs[path] = b""  # deletion
                check_commit(contracts, repository, base_id, staged_message, [p for p in paths if p], branch, store_relative or "", blobs)
                checks.append("staged paths and five commit trailers")
            else:
                for commit in git(repository, "rev-list", "--reverse", f"{base_id}..HEAD").decode().splitlines():
                    if len(git(repository, "rev-list", "--parents", "-n", "1", commit).split()) != 2:
                        raise ValueError("merge/root commits are outside worker commit checks")
                    message = git(repository, "show", "-s", "--format=%B", commit).decode()
                    paths = git(repository, "diff-tree", "--no-commit-id", "--name-only", "--no-renames", "-r", "-z", commit).decode().strip("\x00").split("\x00")
                    blobs = {}
                    for path in [p for p in paths if p]:
                        try:
                            blobs[path] = git(repository, "show", f"{commit}:{path}")
                        except subprocess.CalledProcessError:
                            blobs[path] = b""
                    check_commit(contracts, repository, base_id, message, [p for p in paths if p], branch, store_relative or "", blobs)
                checks.append("Git base immutability, worker paths and five commit trailers")
        except Exception as error:
            errors.append(f"git: {error}")
    return {"name": "contract-lock", "ok": not errors, "errors": errors, "checks": checks, "contracts": len(contracts), "audit_entries": len(entries), "assets": assets, "bug_attempts": attempt_states, "intake_bugs": intake_count}


def main():
    import sys
    from .__main__ import main as cli
    # Keep the installed command and module command on the same implementation.
    args = sys.argv[1:]
    store = ".harness"
    if "--store" in args:
        index = args.index("--store")
        if index + 1 >= len(args):
            raise SystemExit("--store requires a directory")
        store = args[index + 1]
        args = args[:index] + args[index + 2:]
    raise SystemExit(cli(["--store", store, "contract-lock", *args]))
