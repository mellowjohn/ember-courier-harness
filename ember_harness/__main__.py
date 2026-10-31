"""Local trusted-host CLI. Does not execute gated actions."""
import argparse
import json
from pathlib import Path
import sys

from .core import Harness, content_hash, draft, validate


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default=".harness", help="private local harness state directory")
    commands = parser.add_subparsers(dest="command", required=True)
    owner_decide = commands.add_parser('owner-decide', help='trusted human-facing host: record an actual owner response')
    owner_decide.add_argument('request_ref')
    owner_decide.add_argument('--choice', required=True)
    owner_decide.add_argument('--quote', required=True, help="owner's actual response; never fabricate approval wording")
    create = commands.add_parser("draft", help="create an empty, unapproved role template")
    create.add_argument("id")
    create.add_argument("agent")
    create.add_argument("intent")
    create.add_argument("--role", default="coding")
    proposal = commands.add_parser("scope-propose", help="propose an unapproved scope from intent")
    proposal.add_argument("id")
    proposal.add_argument("agent")
    proposal.add_argument("intent")
    proposal.add_argument("--workspace", required=True)
    proposal.add_argument("--brief", help="optional JSON design overrides; cannot grant permissions")
    proposal.add_argument("--asset-workflow", action="store_true", help="include manual concept selection and asset ingest capabilities")
    scope_review = commands.add_parser("scope-review", help="review proposed game and exact authority")
    scope_review.add_argument("file")
    asset_draft = commands.add_parser("asset-draft", help="propose an asset child of an approved scope")
    for flag in ("scope", "manifest", "id", "agent"):
        asset_draft.add_argument("--" + flag, required=True)
    concept_review = commands.add_parser("concept-review", help="check supplied PNG concepts and create a review snapshot")
    concept_review.add_argument("--contract", required=True)
    for name in ("concept-select", "asset-ingest", "asset-accept", "asset-status"):
        command = commands.add_parser(name)
        command.add_argument("review_ref")
        command.add_argument("--contract", required=True)
        if name == "concept-select":
            command.add_argument("--choice", required=True)
        else:
            command.add_argument("--dest", required=True)
    for name in ("validate", "review", "save", "check", "approve-action"):
        cmd = commands.add_parser(name)
        cmd.add_argument("file")
        if name == "approve-action":
            cmd.add_argument("--quote", required=True)
    approve = commands.add_parser("approve", help="record Johnathan's reviewed contract approval")
    approve.add_argument("id")
    approve.add_argument("version", type=int)
    approve.add_argument("--reviewed-hash", required=True)
    approve.add_argument("--quote", required=True)
    approve.add_argument("--parent")
    revoke = commands.add_parser("revoke")
    revoke.add_argument("id")
    revoke.add_argument("--reason", required=True)
    inputs = commands.add_parser("verify-inputs")
    inputs.add_argument("id")
    commands.add_parser("audit-verify")
    evidence = commands.add_parser("verify-evidence")
    evidence.add_argument("id")
    evidence.add_argument("action_id")
    evidence.add_argument("file", help="JSON array of evidence items")
    evidence.add_argument("--decision-seq", required=True, type=int)
    status = commands.add_parser("step-status")
    status.add_argument("id")
    status.add_argument("action_id")
    amendment = commands.add_parser("amend")
    amendment.add_argument("id")
    amendment.add_argument("file", help="untrusted JSON proposal")
    amendment.add_argument("--proposed-by", required=True)
    amendment.add_argument("--replace-pending", action="store_true")
    acknowledgement = commands.add_parser("acknowledge-widening")
    acknowledgement.add_argument("id")
    acknowledgement.add_argument("version", type=int)
    acknowledgement.add_argument("--widening-hash", required=True)
    acknowledgement.add_argument("--quote", required=True)
    for name in ("history", "carry-forward"):
        cmd = commands.add_parser(name)
        cmd.add_argument("id")
    lock = commands.add_parser("contract-lock", help="read-only history, approval and local Git verification")
    lock.add_argument("--repo")
    lock.add_argument("--base")
    lock.add_argument("--message-file", help="check staged files and this prospective commit message")
    attempt_status = commands.add_parser("attempt-status")
    attempt_status.add_argument("bug_id")
    attempt_report = commands.add_parser("attempt-report")
    attempt_report.add_argument("bug_id")
    attempt_report.add_argument("--output")
    failure = commands.add_parser("attempt-fail")
    failure.add_argument("contract_id")
    failure.add_argument("--execution-seq", type=int, required=True)
    failure.add_argument("--reason", required=True)
    escalation = commands.add_parser("attempt-decide")
    escalation.add_argument("bug_id")
    escalation.add_argument("--choice", choices=("retry", "stop"), required=True)
    escalation.add_argument("--state-hash", required=True)
    escalation.add_argument("--quote", required=True)
    for name in ("bug-ingest", "bug-list", "bug-show", "bug-confirm-duplicate", "bug-review-severity", "bug-snapshot", "bug-report", "bug-reopen"):
        command = commands.add_parser(name)
        command.add_argument("--root", required=True, help="approved external intake data workspace")
        if name in ("bug-show", "bug-confirm-duplicate", "bug-review-severity", "bug-snapshot", "bug-reopen"):
            command.add_argument("bug_id")
        if name == "bug-ingest":
            command.add_argument("file")
            command.add_argument("--contract", required=True)
            command.add_argument("--update")
            command.add_argument("--expected-hash")
        elif name == "bug-confirm-duplicate":
            command.add_argument("target_id")
            command.add_argument("--contract", required=True)
            command.add_argument("--bug-hash", required=True)
            command.add_argument("--target-hash", required=True)
            command.add_argument("--note", required=True)
        elif name == "bug-review-severity":
            command.add_argument("--contract", required=True)
            command.add_argument("--expected-hash", required=True)
            command.add_argument("--severity", choices=("S0", "S1", "S2", "S3"), required=True)
            command.add_argument("--demo-impact", choices=("true", "false"), required=True)
            command.add_argument("--note", required=True)
        elif name == "bug-reopen":
            command.add_argument("--contract", required=True)
            command.add_argument("--expected-hash", required=True)
            command.add_argument("--state-hash", required=True)
            command.add_argument("--reason", required=True)
        elif name == "bug-snapshot":
            command.add_argument("fix_contract_id")
    for name in ("bug-reconcile-propose", "bug-reconcile-approve"):
        command = commands.add_parser(name)
        command.add_argument("--root", required=True)
        if name.endswith("propose"):
            command.add_argument("bug_id")
            command.add_argument("target_id")
            for flag in ("contract", "bug-hash", "target-hash", "note"):
                command.add_argument("--" + flag, required=True)
        else:
            command.add_argument("plan_hash")
            command.add_argument("--quote", required=True)
    review = commands.add_parser("muse-review")
    review.add_argument("request")
    review.add_argument("--contract", required=True)
    review.add_argument("--provider", choices=("echo", "manual", "meta"), default="echo")
    review.add_argument("--binary")
    review.add_argument("--binary-sha256")
    review_findings = commands.add_parser("muse-review-findings")
    review_findings.add_argument("capture_ref")
    plan = commands.add_parser("round-start")
    plan.add_argument("file", help="JSON array of planned tasks")
    for name in ("round-status", "round-close", "round-abandon", "round-report", "round-reviewed", "round-verified"):
        command = commands.add_parser(name)
        command.add_argument("number", type=int)
        if name == "round-close":
            command.add_argument("--next-round", nargs="*", default=[])
        elif name == "round-abandon":
            command.add_argument("--reason", required=True)
        elif name == "round-report":
            command.add_argument("--output")
        elif name in ("round-reviewed", "round-verified"):
            command.add_argument("bug_id")
            if name == "round-reviewed":
                command.add_argument("--build", required=True)
                command.add_argument("--review-seq", required=True, type=int)
            else:
                command.add_argument("--repro-seq", required=True, type=int)
                command.add_argument("--verify-seq", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        if args.command == "draft":
            result = draft(args.id, args.agent, args.intent, role=args.role)
        elif args.command == "scope-propose":
            from .scope import propose
            result = propose(args.id, args.agent, args.intent, args.workspace,
                             brief=read(args.brief) if args.brief else None, asset_workflow=args.asset_workflow)
        elif args.command == "scope-review":
            from .scope import review as review_scope
            result = review_scope(read(args.file))
        elif args.command in ("validate", "review"):
            c = read(args.file)
            validate(c)
            result = {"valid": True, "reviewed_hash": content_hash(c)}
            if args.command == "review":
                result["summary"] = {"goal": c["goal"], "agent": c["agent"], "version": c["version"],
                                     "approval_mode": c.get("approval_mode", "each"), "limits": c["limits"],
                                     "actions": c["allowed_actions"], "paths": c["allowed_paths"],
                                     "forbidden": c["forbidden_actions"], "required_evidence": c["required_evidence"],
                                     "requires_approval": c["requires_approval"], "extensions": c.get("extensions", {}),
                                     "inputs": c["inputs"], "art_direction": c.get("art_direction")}
        elif args.command == "contract-lock":
            from .contract_lock import verify
            result = verify(args.store, repo=args.repo, base=args.base,
                            staged_message=Path(args.message_file).read_text(encoding="utf-8") if args.message_file else None)
        else:
            h = Harness(args.store)
            if args.command == 'owner-decide':
                from .owner_review import decide
                result = decide(h, args.request_ref, args.choice, args.quote)
            elif args.command in ("asset-draft", "concept-review", "concept-select", "asset-ingest", "asset-accept", "asset-status"):
                from .assets import Assets
                assets = Assets(h)
                if args.command == "asset-draft":
                    result = assets.proposal(args.scope, args.manifest, args.id, args.agent)
                elif args.command == "concept-review":
                    result = assets.review(args.contract)
                elif args.command == "concept-select":
                    result = assets.select(args.contract, args.review_ref, args.choice)
                elif args.command == "asset-ingest":
                    result = assets.ingest(args.contract, args.review_ref, args.dest)
                elif args.command == "asset-accept":
                    result = assets.accept(args.contract, args.review_ref, args.dest)
                else:
                    result = assets.status(args.contract, args.review_ref, args.dest)
            elif args.command == "save":
                h.save_draft(read(args.file))
                result = {"saved": True, "status": "draft"}
            elif args.command == "approve":
                result = h.approve(args.id, args.version, approver="johnathan", quote=args.quote,
                                   expected_hash=args.reviewed_hash, parent_id=args.parent)
            elif args.command == "approve-action":
                result = h.approve_action(read(args.file), approver="johnathan", quote=args.quote)
            elif args.command == "check":
                result = h.check(read(args.file))
            elif args.command == "revoke":
                h.revoke(args.id, approver="johnathan", reason=args.reason)
                result = {"revoked": args.id}
            elif args.command == "verify-inputs":
                result = {"passed": h.verify_inputs(args.id)}
            elif args.command == "verify-evidence":
                result = h.verify_evidence(args.id, args.action_id, read(args.file), decision_seq=args.decision_seq)
            elif args.command == "step-status":
                result = h.step_status(args.id, args.action_id)
            elif args.command == "amend":
                result = h.amend(args.id, read(args.file), proposed_by=args.proposed_by, replace_pending=args.replace_pending)
            elif args.command == "acknowledge-widening":
                result = h.acknowledge_widening(args.id, args.version, args.widening_hash, approver="johnathan", quote=args.quote)
            elif args.command == "history":
                result = {"versions": h.history(args.id)}
            elif args.command == "carry-forward":
                result = h.carry_forward(args.id)
            elif args.command.startswith("attempt-"):
                from .attempts import Attempts
                attempts = Attempts(h)
                if args.command == "attempt-status":
                    result = attempts.status(args.bug_id)
                elif args.command == "attempt-report":
                    from .reporting import write_attempt_report
                    result = write_attempt_report(h, args.bug_id, args.output)
                elif args.command == "attempt-fail":
                    result = attempts.fail(args.contract_id, execution_seq=args.execution_seq, reason=args.reason)
                else:
                    result = attempts.decide(args.bug_id, choice=args.choice, expected_state_hash=args.state_hash, approver="johnathan", quote=args.quote)
            elif args.command.startswith("muse-review"):
                from .muse_reviews import MuseReviews
                reviews = MuseReviews(h, binary=getattr(args, "binary", None), binary_sha256=getattr(args, "binary_sha256", None))
                if args.command == "muse-review":
                    result = reviews.run(args.request, contract_id=args.contract, provider=args.provider)
                else:
                    result = {"findings": reviews.findings(args.capture_ref)}
            elif args.command.startswith("bug-"):
                from .intake import Intake
                intake = Intake(h, args.root)
                if args.command.startswith("bug-reconcile-"):
                    from .reconciliation import Reconciliation
                    reconciliation = Reconciliation(intake)
                    if args.command.endswith("propose"):
                        result = reconciliation.propose(args.bug_id, args.target_id, contract_id=args.contract, bug_hash=args.bug_hash, target_hash=args.target_hash, note=args.note)
                    else:
                        result = reconciliation.approve(args.plan_hash, approver="johnathan", quote=args.quote)
                elif args.command == "bug-ingest":
                    result = intake.ingest(args.file, contract_id=args.contract, bug_id=args.update, expected_hash=args.expected_hash)
                elif args.command == "bug-list":
                    result = {"bugs": intake.list()}
                elif args.command == "bug-show":
                    result = intake.get(args.bug_id)
                elif args.command == "bug-confirm-duplicate":
                    result = intake.confirm_duplicate(args.bug_id, args.target_id, contract_id=args.contract, bug_hash=args.bug_hash, target_hash=args.target_hash, note=args.note)
                elif args.command == "bug-review-severity":
                    result = intake.review_severity(args.bug_id, contract_id=args.contract, expected_hash=args.expected_hash, severity=args.severity, demo_impact=args.demo_impact == "true", note=args.note)
                elif args.command == "bug-reopen":
                    result = intake.reopen(args.bug_id, contract_id=args.contract, expected_hash=args.expected_hash, expected_state_hash=args.state_hash, reason=args.reason)
                elif args.command == "bug-snapshot":
                    result = intake.snapshot(args.bug_id, args.fix_contract_id)
                else:
                    from .reporting import write_intake_report
                    result = write_intake_report(h, args.root)
            elif args.command.startswith("round-"):
                from .rounds import Rounds
                rounds = Rounds(h)
                if args.command == "round-start":
                    result = rounds.start(read(args.file))
                elif args.command == "round-status":
                    result = rounds.status(args.number)
                elif args.command == "round-close":
                    result = rounds.close(args.number, next_round=args.next_round)
                elif args.command == "round-abandon":
                    result = rounds.abandon(args.number, args.reason)
                elif args.command == "round-reviewed":
                    result = rounds.reviewed(args.number, args.bug_id, build=args.build, review_seq=args.review_seq)
                elif args.command == "round-verified":
                    result = rounds.verified(args.number, args.bug_id, repro_seq=args.repro_seq, verify_seq=args.verify_seq)
                else:
                    from .reporting import write_round_report
                    result = write_round_report(h, args.number, args.output)
            else:
                result = h.audit_verify()
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 1 if result.get("integrity_ok") is False or result.get("ok") is False or result.get("decision") == "deny" or result.get("passed") is False or result.get("status") in ("incomplete", "failed") else 0
    except Exception as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
