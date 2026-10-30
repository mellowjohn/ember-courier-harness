"""Audit-derived round checkpoints. Only the trusted host writes round state."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re

from .core import canonical, digest, matches, normal, timestamp, constraints_ok
from .contract_lock import git, verify as contract_lock
from .staged_fix import execution


class Rounds:
    def __init__(self, harness):
        self.h = harness

    def status(self, number):
        if type(number) is not int or number < 1:
            raise ValueError("positive round number required")
        events = [e for e in self.h._entries() if e.get("detail", {}).get("scope") == "round" and e["detail"].get("round") == number]
        if not events or events[0]["detail"]["checkpoint"] != "C0":
            raise ValueError("round not found")
        first, last = events[0], events[-1]
        tasks = deepcopy(first["tasks"])
        for task in tasks:
            task["checkpoints"] = {e["detail"]["checkpoint"]: e["seq"] for e in events if e.get("bug_id") == task["bug_id"]}
        return {"round": number, "status": last["status"], "status_basis": last["seq"], "tasks": tasks,
                "plan_hash": first["task_list_sha256"], "checkpoints": {"C0": first["seq"], **{e["detail"]["checkpoint"]: e["seq"] for e in events if e["detail"]["checkpoint"] in ("C3", "abandoned")}},
                "events": events}

    def _open(self, number):
        state = self.status(number)
        if state["status"] in ("complete", "abandoned"):
            raise ValueError("round is terminal")
        return state

    def _contracts(self, task):
        active = self.h._active(self.h._entries())
        result = []
        for key in ("fix", "verifier"):
            cid = task[key + "_contract_id"]
            if cid not in active or active[cid]["contract_version"] != task[key + "_version"]:
                raise ValueError("planned contract is no longer the active approved version")
            c = self.h._authority(active[cid], active)
            window = c["limits"]["time_window"]
            if not timestamp(window["not_before"]) <= self.h.clock() <= timestamp(window["not_after"]):
                raise ValueError("planned contract expired")
            result.append(c)
        fix, verifier = result
        from .attempts import action_block
        reason = action_block(self.h._entries(), active[fix["id"]])
        if reason and reason != "attempt_succeeded":
            raise ValueError(reason)
        if (fix["agent"] == verifier["agent"] or verifier["allowed_paths"]["write"] or
                fix.get("extensions", {}).get("orchestration", {}).get("role") not in ("coding", "worker") or
                verifier.get("extensions", {}).get("orchestration", {}).get("role") != "verifier"):
            raise ValueError("distinct read-only verifier required")
        if any(a["args_constraints"].get("branch") != {"equals": task["branch"]} for a in fix["allowed_actions"] if a["tool"] in ("git.add", "git.commit")):
            raise ValueError("planned branch differs from approved worker branch")
        return fix, verifier

    def _record(self, number, checkpoint, status, **fields):
        entry = self.h._append("state_transition", detail={"scope": "round", "round": number, "checkpoint": checkpoint}, status=status, **fields)
        warning = None
        try:
            path = self.h.root / "triage" / "rounds" / f"round-{number:04d}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(canonical(self.status(number)))
            if checkpoint == "C3":
                anchor = self.h.root / "audit" / "anchors" / f"round-{number}.txt"
                anchor.parent.mkdir(parents=True, exist_ok=True)
                anchor.write_text(entry["entry_hash"] + "\n", encoding="utf-8")
        except OSError as error:
            warning = str(error)
        return {"round": number, "status": status, "status_basis": entry["seq"], "audit_head": entry["entry_hash"], "cache_warning": warning}

    def start(self, tasks):
        if not isinstance(tasks, list) or not 1 <= len(tasks) <= 2:
            raise ValueError("one or two tasks required")
        required = {"bug_id", "severity", "fix_contract_id", "fix_version", "verifier_contract_id", "verifier_version", "source_path", "repo", "base", "branch", "repro_repo", "verification_repo"}
        with self.h._lock():
            prior = [e for e in self.h._entries() if e.get("detail", {}).get("scope") == "round"]
            number = max((e["detail"]["round"] for e in prior), default=0) + 1
            if prior and self.status(number - 1)["status"] not in ("complete", "abandoned"):
                raise ValueError("previous round is still open")
            bugs, branches, workers = set(), set(), set()
            planned = deepcopy(tasks)
            for task in planned:
                if set(task) != required or re.fullmatch(r"BUG-[0-9]+", task["bug_id"]) is None or task["severity"] not in ("S0", "S1", "S2", "S3"):
                    raise ValueError("invalid round task")
                if task["bug_id"] in bugs or task["branch"] in branches or task["fix_contract_id"] in workers:
                    raise ValueError("duplicate bug, worker or branch")
                bugs.add(task["bug_id"]); branches.add(task["branch"]); workers.add(task["fix_contract_id"])
                if task["branch"] != f"round/{number}/{task['fix_contract_id']}":
                    raise ValueError("worker branch must belong to this round")
                fix, verifier = self._contracts(task)
                from .attempts import action_block
                if action_block(self.h._entries(), self.h._active(self.h._entries())[fix["id"]]):
                    raise ValueError("a finished fix attempt cannot start another round")
                if not any(matches(normal(task["source_path"]), p) for p in fix["allowed_paths"]["write"]):
                    raise ValueError("source is outside fix scope")
                snapshot = next((i for i in fix["inputs"] if i["name"] == "bug_snapshot"), None)
                if not snapshot or sha256(Path(snapshot["path"]).read_bytes()).hexdigest() != snapshot.get("sha256"):
                    raise ValueError("approved frozen bug snapshot required")
                bug = json.loads(Path(snapshot["path"]).read_text(encoding="utf-8"))
                if bug.get("id") != task["bug_id"] or bug.get("severity") != task["severity"]:
                    raise ValueError("plan differs from approved bug snapshot")
                for key in ("repo", "source_path", "repro_repo", "verification_repo"):
                    task[key] = normal(task[key])
                if len({task[k] for k in ("repo", "repro_repo", "verification_repo")}) != 3:
                    raise ValueError("verification requires separate clean checkout paths")
                task["base"] = git(task["repo"], "rev-parse", "--verify", task["base"] + "^{commit}").decode().strip()
            return self._record(number, "C0", "planned", tasks=planned, task_list_sha256=digest(planned))

    def _task(self, state, bug_id):
        task = next((t for t in state["tasks"] if t["bug_id"] == bug_id), None)
        if not task:
            raise ValueError("bug is not in round plan")
        self._contracts(task)
        return task

    def _clean_run(self, task, seq, checkout, build, action_id, exit_code):
        event, payload = execution(self.h, seq)
        _, verifier = self._contracts(task)
        if event["contract_id"] != verifier["id"] or event["contract_version"] != verifier["version"] or payload["returncode"] != exit_code:
            raise ValueError("wrong verifier, version or execution result")
        decision = next(e for e in self.h._entries() if e["seq"] == event["decision_seq"])
        permitted = next((a for a in verifier["allowed_actions"] if a["action_id"] == action_id), None)
        if not permitted or decision["action"]["tool"] != "test.run" or not constraints_ok(decision["action"]["args"], permitted["args_constraints"]):
            raise ValueError("execution is not the planned verification action")
        if git(checkout, "rev-parse", "HEAD").decode().strip() != build or git(checkout, "status", "--porcelain"):
            raise ValueError("verification checkout is dirty or on the wrong build")
        root = Path(checkout).resolve()
        for path, expected in payload["inputs"].items():
            relative = Path(path).resolve().relative_to(root).as_posix()
            if sha256(git(root, "show", f"{build}:{relative}")).hexdigest() != expected:
                raise ValueError("captured input differs from named clean build")
        relative_source = Path(task["source_path"]).relative_to(Path(task["repo"])).as_posix()
        if (root / relative_source).as_posix() not in payload["inputs"]:
            raise ValueError("execution did not capture planned source")
        return event, payload

    def reviewed(self, number, bug_id, *, build, review_seq):
        # Evidence refresh appends its own audit entry before the checkpoint.
        state = self._open(number)
        task = self._task(state, bug_id)
        if "C1" in task["checkpoints"]:
            raise ValueError("C1 already recorded")
        if self.h.step_status(task["verifier_contract_id"], "review")["status"] != "complete":
            raise ValueError("review evidence is incomplete")
        with self.h._lock():
            state = self._open(number); task = self._task(state, bug_id)
            if "C1" in task["checkpoints"]:
                raise ValueError("C1 already recorded")
            if review_seq <= state["checkpoints"]["C0"]:
                raise ValueError("review predates round plan")
            _, payload = self._clean_run(task, review_seq, task["verification_repo"], build, "review", 0)
            if "REVIEW PASS" not in payload["stdout"]:
                raise ValueError("review did not pass")
            if not contract_lock(self.h.root, repo=task["repo"], base=task["base"])["ok"]:
                raise ValueError("contract-lock failed")
            return self._record(number, "C1", "in_progress", bug_id=bug_id, build=build, branch=task["branch"], review_execution_seq=review_seq)

    def verified(self, number, bug_id, *, repro_seq, verify_seq):
        state = self._open(number); task = self._task(state, bug_id)
        if "C1" not in task["checkpoints"] or "C2" in task["checkpoints"]:
            raise ValueError("C2 requires C1 and cannot be repeated")
        for action in ("reproduce", "verify"):
            if self.h.step_status(task["verifier_contract_id"], action)["status"] != "complete":
                raise ValueError("verification evidence is incomplete")
        with self.h._lock():
            state = self._open(number); task = self._task(state, bug_id)
            if "C1" not in task["checkpoints"] or "C2" in task["checkpoints"]:
                raise ValueError("C2 requires C1 and cannot be repeated")
            c1 = next(e for e in state["events"] if e["seq"] == task["checkpoints"]["C1"])
            if repro_seq <= state["checkpoints"]["C0"] or verify_seq <= c1["seq"]:
                raise ValueError("verification witnesses are out of order")
            before_event, before = self._clean_run(task, repro_seq, task["repro_repo"], task["base"], "reproduce", 1)
            after_event, after = self._clean_run(task, verify_seq, task["verification_repo"], c1["build"], "verify", 0)
            if before["script_sha256"] != after["script_sha256"] or "AssertionError" not in before["stderr"] or "OK" not in after["stderr"]:
                raise ValueError("same regression must fail before and pass after")
            refs = [e["evidence_refs"][0] for e in self.h._entries() if e["kind"] == "evidence" and e.get("decision_seq") in (before_event["decision_seq"], after_event["decision_seq"])]
            return self._record(number, "C2", "awaiting_approval", bug_id=bug_id, build=c1["build"], repro_execution_seq=repro_seq, verify_execution_seq=verify_seq, evidence_refs=refs)

    def close(self, number, *, next_round=None):
        next_round = [] if next_round is None else next_round
        if not isinstance(next_round, list) or any(not isinstance(b, str) or re.fullmatch(r"BUG-[0-9]+", b) is None for b in next_round) or len(set(next_round)) != len(next_round):
            raise ValueError("next-round list must contain unique bug IDs")
        with self.h._lock():
            state = self._open(number)
            entries = self.h._entries()
            closures = []
            for task in state["tasks"]:
                self._task(state, task["bug_id"])
                if "C2" not in task["checkpoints"]:
                    raise ValueError("all tasks require C1 and C2 before C3")
                c2 = next(e for e in state["events"] if e["seq"] == task["checkpoints"]["C2"])
                self._clean_run(task, c2["repro_execution_seq"], task["repro_repo"], task["base"], "reproduce", 1)
                self._clean_run(task, c2["verify_execution_seq"], task["verification_repo"], c2["build"], "verify", 0)
                relative = Path(task["source_path"]).relative_to(Path(task["repo"])).as_posix()
                if (git(task["repo"], "rev-parse", "HEAD").decode().strip() != c2["build"] or
                        sha256(Path(task["source_path"]).read_bytes()).hexdigest() != sha256(git(task["repo"], "show", f"{c2['build']}:{relative}")).hexdigest()):
                    raise ValueError("current source/build changed after verification")
                closure = next((e for e in reversed(entries) if e["kind"] == "state_transition" and e.get("bug_id") == task["bug_id"] and e.get("status") == "closed" and e["seq"] > c2["seq"]), None)
                if not closure or closure.get("build") != c2["build"] or closure.get("fix_contract_id") != task["fix_contract_id"] or closure.get("fix_version") != task["fix_version"] or closure.get("verifier_contract_id") != task["verifier_contract_id"] or closure.get("execution_seqs", [])[-1:] != [c2["verify_execution_seq"]]:
                    raise ValueError("verified bug closure required before C3")
                decision = next((e for e in entries if e["seq"] == closure.get("decision_seq")), {})
                if decision.get("decision") != "allow" or decision.get("action", {}).get("args", {}).get("severity") != task["severity"]:
                    raise ValueError("closure approval is missing or mismatched")
                if task["severity"] in ("S0", "S1"):
                    approval = next((e for e in entries if e["seq"] == decision.get("approval_ref")), {})
                    if approval.get("scope") != "action" or approval.get("actor") != "johnathan" or approval.get("actor_type") != "human":
                        raise ValueError("critical closure requires Johnathan's own action approval")
                closures.append(closure["seq"])
            head = entries[-1]["entry_hash"]
            return self._record(number, "C3", "complete", closure_seqs=closures, push_decision="not_requested", next_round=next_round, audit_head_before_close=head)

    def abandon(self, number, reason):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("abandonment reason required")
        with self.h._lock():
            self._open(number)
            return self._record(number, "abandoned", "abandoned", reason=reason)
