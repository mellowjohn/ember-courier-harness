# Persistent project scope and ordered tasks

Plan through the session's chat, or choose **Plan → Plan together in chat**.
Ember asks the next useful question, remembers explicit answers in the project
brief and gathers the game concept, core loop, features, exclusions, artwork estimates,
completion criteria and art direction as they become relevant. You can change
these decisions through conversation. No project-plan form is required.
When enough decisions are known, ask Ember to prepare the plan for review.
The model returns a structured design proposal; the host validates it and uses
the existing scope compiler. Features become ordered task cards. Artwork counts are planning estimates,
not enforced limits; exceeding an estimate does not require an amendment. The existing local planning API remains available.

Read the inline review's complete design, art direction and
scope permissions, then choose **Approve project plan** or discard it. The plan
is an actual root scope in the existing contract store, not an approval flag in
the brief. Approval saves authority for up to 24 hours; it does not create or
modify project files, start a worker, accept an asset or complete a task.

## Work on one task

Choose **Work on this task**, then ask Ember to implement it. The approved plan
and selected task are included in the request even when older conversation text
has left the context. A retry keeps its original task selection. A changed active
scope stops a stale retry before another Muse call. Pending, revoked or expired
scopes permit conversation but cannot authorize builds.

The resulting proposal names its existing project scope and task. Its exact
coding contract must be a subset of that scope and inherit its art direction.
The host checks this before preparing the review and the existing gate checks
it again on approval/execution. The root scope is reused across task builds;
each exact build still needs **Approve & play**, and a changed asset still needs
individual **Accept asset & play**. The model receives no approval tools.

Use the existing proposal preview and saved desktop/touch gameplay comparisons.
After application, the task says **Build applied · outcome needs review**. Inspect
and play the latest build before choosing **Accept task outcome**. This records
a separate human observation bound to the plan version, task, build and manifest.
Applying files, a model claiming success or a passing gameplay report does not
automatically accept a task. Task acceptance is not independent verification,
critical-bug closure or proof of overall project completion.

After **Accept task outcome**, Ember automatically selects the first unfinished
task in plan order and prepares its **Approve task run** review. Approval of that
new run starts its agents; accepting the previous outcome does not approve new
contracts. The next task remains selected when missing checks, credits, tooling
or unfinished work prevent preparation, with the reason shown beside the plan.
Repeated acceptance does not create duplicate runs. When every planned outcome
has been accepted, Ember reports that and stops preparing work.

For a bounded coding run followed by separate Chromium checks and a Muse verifier,
choose **Run task with Muse** and review its permissions. See [task execution](TASK_RUNS.md)
for the three-attempt limit, recovery and final exact approval.

**Create chest/gate directions** runs the [bounded asset-production workflow](ASSET_PRODUCTION.md)
for a selected task. It needs a separate producer/
verifier review, explicit direction pick and individual final asset acceptance.

The current task remains selected until you choose another; no background task
scheduler or worker is started by selecting a card. Accepted outcomes
remain tied to their saved versions. Subsequent versions need their own checks.

## Amend, renew and recover

Tell Ember what to change, or choose **Discuss plan changes in chat**, to prepare
a reviewed successor. Expired plans can also be discussed and renewed through
chat. Revoked authority cannot be renewed. Finish
or discard any pending build, or recover an approved interrupted build first.
The existing amendment compiler records the changes and requires a separate
**Acknowledge scope changes** gesture for computed widening or unproven changes,
followed by **Approve project plan**. A new time window also needs review.
Approval supersedes the prior scope and rechecks its children using the existing
core implementation. New-plan task outcomes start unaccepted; earlier receipts
remain in the audit against their original version and criteria.
The current approved game can still be inspected and checked against its original
receipts when its write contract retires. This read-only verification never
reactivates the old contract; new work needs the current approved scope.

Plans, pending reviews, task selection, outcomes and acknowledgement receipts
survive reload/restart. The 24-hour authorization does not extend on restart.
Revoked scopes cannot be silently revived. Unexpected changes to reviewed
contracts, project destinations or saved project files stop the relevant action.
An interrupted owner receipt can be recovered with the same reviewed response
through the existing review implementation; no approval is inferred from a
model response or a task status.

Existing sessions keep their per-build review behavior until a project plan is
first prepared. Once configured, an unapproved, declined, expired or revoked
plan cannot fall back to a new independent build scope. This compatibility
boundary is explicit. Conversational brief updates remain guidance and cannot
amend approved scope without the separate project-plan review.

**Save approved project as…** copies the game, brief and gameplay plan to a new
session. Project authority and task acceptance belong to their original session
and destination; prepare and review a new plan for the copy. ZIPs contain the
verified game, not private plan/approval history.

## Current boundary and evidence

This is the persistent planning and scope-binding milestone in
[the original MVP checklist](MVP_STATUS.md). Artwork estimates, design exclusions and
completion criteria are explicit design constraints supplied to Muse and the
human reviewer. The gate enforces tool permissions, paths, content, windows and
limits; it does not infer semantic feature compliance or count produced assets.
Art direction is inherited exactly; artistic quality still needs judgment.

Bounded browser task workers and separate per-task verification are available
through [task runs](TASK_RUNS.md). Continuation follows plan order; dependency-graph scheduling, arbitrary project
workers and general concept/model production remain separate implementation work.
[Findings and verified fixes](FINDINGS.md) now connect current-build human reports
to scoped browser fixes and separate closure under the approved project scope.
Overnight polish freezes the project/task context
and rejects stale authority before further model calls or final promotion; its
separately reviewed isolated candidate scope is still its own worker workflow.

`tests/test_project_plan.py` covers review, persistence, root reuse, exact child
contracts, task outcomes, amendments, expiry/revocation, tampering, selected-task
retry snapshots, HTTP authorization and asset/restore compatibility. The existing
`tools/browser_check.py` rehearsal also exercises conversational answer saving,
read-only summaries, reload persistence, chat-prepared plans and amendments,
scope approval, selected task, proposal gameplay comparison, separate task
acceptance, reload and amendment acknowledgement on desktop/mobile. Model replies,
folder-picker selection and owner decisions are synthetic in isolated fixtures;
browser execution and file evidence are real. These checks make no claim about
the quality of arbitrary live Muse output.
