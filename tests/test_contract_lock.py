from copy import deepcopy
import json
from pathlib import Path
import subprocess
import unittest

from ember_harness import canonical
from ember_harness.contract_lock import asset_check, check_commit, git, trailers, verify
import test_amendments as amendment_fixtures


class LockTests(unittest.TestCase):
    setUp = amendment_fixtures.AmendmentTests.setUp
    setup_contract = amendment_fixtures.AmendmentTests.setup_contract
    start = amendment_fixtures.AmendmentTests.start
    proposal = amendment_fixtures.AmendmentTests.proposal
    propose = amendment_fixtures.AmendmentTests.propose
    approve = amendment_fixtures.AmendmentTests.approve
    hash_item = amendment_fixtures.AmendmentTests.hash_item
    evidence_verify = amendment_fixtures.AmendmentTests.verify

    def assert_bad(self, phrase):
        result = verify(self.h.root)
        self.assertFalse(result["ok"], result)
        self.assertIn(phrase, "\n".join(result["errors"]))

    def test_GT01_GT04_valid_amendment_and_rollback(self):
        self.start(max_calls=4)
        self.assertTrue(verify(self.h.root)["ok"])
        self.approve(self.propose(self.proposal(value=2)))
        result = self.propose({"reason": "Rollback", "round": 2, "source": {"kind": "manual", "id": "test"}, "rollback_to": 1})
        self.approve(result)
        self.assertTrue(verify(self.h.root)["ok"], verify(self.h.root))

    def test_modified_approved_bytes_and_status(self):
        self.start()
        path = self.h._path(self.c["id"], 1)
        c = json.loads(path.read_text())
        c["goal"] = "edited without amendment"
        path.write_bytes(canonical(c))
        self.assert_bad("content_hash mismatch")

    def test_missing_approval_and_missing_approved_version(self):
        self.start()
        path = self.h.root / "approvals" / f"{self.c['id']}-v1.json"
        path.unlink()
        self.assert_bad("approvals")
        self.h._path(self.c["id"], 1).unlink()
        self.assert_bad("approved contract file missing")

    def test_amendment_record_and_lineage_tamper(self):
        self.start()
        self.approve(self.propose())
        path = self.h._path(self.c["id"], 2).parent / "amendments" / "v1-to-v2.json"
        record = json.loads(path.read_text())
        record["widening"]["items"] = []
        path.write_bytes(canonical(record))
        self.assert_bad("amendment record differs")

    def test_evidence_payload_tamper(self):
        self.start()
        result = self.evidence_verify([self.hash_item()])
        (self.h.root / "evidence" / f"{result['evidence_ref']}.json").write_bytes(b"{}")
        self.assert_bad("evidence payload hash mismatch")

    def test_version_gaps_and_duplicate_approved(self):
        self.start()
        self.approve(self.propose())
        first = self.h._path(self.c["id"], 1)
        c = json.loads(first.read_text())
        c["status"] = "approved"
        first.write_bytes(canonical(c))
        self.assert_bad("multiple approved versions")
        first.unlink()
        self.assert_bad("version gap")

    def test_draft_amendment_has_no_authority_but_is_verifiable(self):
        self.start()
        self.propose()
        result = verify(self.h.root)
        self.assertTrue(result["ok"], result)

    def test_anchor_hash_checked(self):
        self.start()
        folder = self.h.root / "audit" / "anchors"
        folder.mkdir()
        (folder / "round-1.txt").write_text("0" * 64)
        self.assert_bad("anchor not in audit chain")
        (folder / "round-1.txt").write_text(self.h.audit_verify()["head"])
        self.assertTrue(verify(self.h.root)["ok"])

    def test_GT02_trailers_and_GT05_path_scope_GT11_branch(self):
        self.start()
        c = json.loads(self.h._path(self.c["id"], 1).read_text())
        message = f"Fix local bug\n\nRound: 1\nContract-Id: {c['id']}\nContract-Version: 1\nContract-Hash: {c['content_hash']}\nSubsystem: triage\n"
        contracts = {(c["id"], 1): c}
        branch = f"round/1/{c['id']}"
        check_commit(contracts, self.root, None, message, ["files/result.txt"], branch)
        for key in ("Round", "Contract-Id", "Contract-Version", "Contract-Hash", "Subsystem"):
            missing = "\n".join(line for line in message.splitlines() if not line.startswith(key + ":"))
            with self.assertRaises(ValueError):
                trailers(missing)
        for changed in (message.replace("Contract-Version: 1", "Contract-Version: 9"), message.replace(c["content_hash"], "0" * 64)):
            with self.assertRaises(ValueError):
                check_commit(contracts, self.root, None, changed, ["files/result.txt"], branch)
        with self.assertRaisesRegex(ValueError, "outside allowed"):
            check_commit(contracts, self.root, None, message, ["unapproved.py"], branch)
        with self.assertRaisesRegex(ValueError, "wrong branch"):
            check_commit(contracts, self.root, None, message, ["files/result.txt"], "main")

    def test_GT03_amendment_branch_scope(self):
        self.start()
        c = json.loads(self.h._path(self.c["id"], 1).read_text())
        message = f"Amend\n\nRound: 1\nContract-Id: {c['id']}\nContract-Version: 1\nContract-Hash: {c['content_hash']}\nSubsystem: contracts\n"
        with self.assertRaisesRegex(ValueError, "outside contracts"):
            check_commit({(c["id"], 1): c}, self.root, None, message, ["src/evil.py"], f"contract/{c['id']}/v1")

    def test_GT01_actual_git_base_comparison_detects_metadata_edit(self):
        self.start()
        git(self.root, "init", "--initial-branch=main")
        git(self.root, "-c", "core.autocrlf=false", "add", "--", "state")
        git(self.root, "-c", "user.name=Demo", "-c", "user.email=demo@example.invalid", "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={self.root / 'no-hooks'}", "commit", "-m", "Bootstrap fixture")
        path = self.h._path(self.c["id"], 1)
        c = json.loads(path.read_text())
        c["approved_at"] = "2026-01-01T00:00:00+00:00"  # excluded from content hash
        path.write_bytes(canonical(c))
        result = verify(self.h.root, repo=self.root, base="HEAD")
        self.assertFalse(result["ok"])
        self.assertIn("base approved bytes changed", "\n".join(result["errors"]))

    def test_GT09_cli_stable_name_and_missing_store(self):
        import contextlib
        import io
        from ember_harness.__main__ import main
        self.start()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["--store", str(self.h.root), "contract-lock"]), 0)
        self.assertEqual(json.loads(output.getvalue())["name"], "contract-lock")
        self.assertFalse(verify(self.root / "missing")["ok"])

    def test_GT08_pointer_only_asset_never_claims_verified_bytes(self):
        self.start()
        path = self.root / "asset.glb"
        expected = "b" * 64
        path.write_bytes(f"version https://git-lfs.github.com/spec/v1\noid sha256:{expected}\nsize 1234\n".encode())
        result = asset_check(path, expected)
        self.assertEqual(result["basis"], "lfs_pointer")
        self.assertEqual(result["label"], "self_reported")
        with self.assertRaisesRegex(ValueError, "oid mismatch"):
            asset_check(path, "a" * 64)

    def test_GT08_plain_file_size_guard(self):
        self.start()
        c = json.loads(self.h._path(self.c["id"], 1).read_text())
        message = f"Fix\n\nRound: 1\nContract-Id: {c['id']}\nContract-Version: 1\nContract-Hash: {c['content_hash']}\nSubsystem: triage\n"
        with self.assertRaisesRegex(ValueError, "size guard"):
            check_commit({(c["id"], 1): c}, self.root, None, message, ["files/result.txt"], f"round/1/{c['id']}", blobs={"files/result.txt": b"x" * (1024 * 1024 + 1)})

    def test_amendment_branch_cannot_hide_changes_under_similar_folder(self):
        self.start()
        c = json.loads(self.h._path(self.c["id"], 1).read_text())
        message = f"Amend\n\nRound: 1\nContract-Id: {c['id']}\nContract-Version: 1\nContract-Hash: {c['content_hash']}\nSubsystem: contracts\n"
        with self.assertRaisesRegex(ValueError, "outside contracts"):
            check_commit({(c["id"], 1): c}, self.root, None, message, [f"src/contracts/{c['id']}/v2.json"], f"contract/{c['id']}/v1", store_prefix="control")

    def test_staged_contract_cannot_hide_behind_restored_working_copy(self):
        self.start()
        git(self.root, "init", "--initial-branch=main")
        git(self.root, "-c", "core.autocrlf=false", "add", "--", "state")
        git(self.root, "-c", "user.name=Demo", "-c", "user.email=demo@example.invalid", "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={self.root / 'no-hooks'}", "commit", "-m", "Bootstrap fixture")
        c = json.loads(self.h._path(self.c["id"], 1).read_text())
        git(self.root, "switch", "-c", f"round/1/{c['id']}")
        path = self.h._path(self.c["id"], 1)
        original = path.read_bytes()
        altered = json.loads(original)
        altered["approved_at"] = "2026-01-01T00:00:00+00:00"
        path.write_bytes(canonical(altered))
        git(self.root, "-c", "core.autocrlf=false", "add", "--", path.relative_to(self.root).as_posix())
        path.write_bytes(original)
        message = f"Fix\n\nRound: 1\nContract-Id: {c['id']}\nContract-Version: 1\nContract-Hash: {c['content_hash']}\nSubsystem: triage\n"
        result = verify(self.h.root, repo=self.root, base="HEAD", staged_message=message)
        self.assertFalse(result["ok"])
        self.assertIn("staged store bytes differ", "\n".join(result["errors"]))
