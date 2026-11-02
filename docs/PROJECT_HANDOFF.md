# Project handoff and the integrated sample

The workspace follows four views. **Plan** holds the approved design, ordered
tasks, creative brief and project-folder setup. **Build** holds the current task,
conversation, candidate review, asset library and running task evidence.
**Playtest** keeps the live game beside saved gameplay checks, findings and
overnight polish. **Handoff** holds the current project download and saved versions.
Activity, audit records and detailed permissions remain available separately.
Switching between Build and Playtest preserves the live game's frame and state.

In **Handoff**, choose **Download project handoff**. The download contains:

- `game.zip`: the existing verified export of the current approved game.
- `PROJECT_HANDOFF.md`: a readable status and playtest guide.
- `project-report.json`: the source manifest, originating build scope, current
  approved plan and amendment history, version-bound task acceptance, accepted
  GLB specification, task attempts, separate AI judgments, findings/closures,
  current gameplay reports and recorded playtest observations.

The game ZIP's hash is recorded in the report. The download checks current files,
reviewed bytes, owner receipts, the audit chain and contract-lock. Retained task
reports, production outputs and current gameplay captures are rechecked. Changed
evidence, a different selected session, a stale current-build reference or an audit
change during assembly stops the download. A pending proposal stays unapplied and
is counted in the report. Downloading makes no model call or approval decision.

The report distinguishes the scope used for the build from the latest approved
plan. A scope amendment does not make earlier files compliant. Historical task
acceptance and bug closure remain associated with their exact saved builds.
Absent current gameplay checks are reported as **not checked**. Passing checks,
AI judgments and human observations remain separate; the report never declares
the entire project complete.

Host paths, owner quotes, conversations, native Blender files and raw captures
are omitted. The latter remain in the local session workspace; this package is
the approved browser game plus its report. User-authored design, finding titles
and playtest notes are included, so review the report before sharing it.
Local host records do not provide independent identity authentication or prove
that an owner response was made by a real person rather than a test fixture.

## Rehearse one integrated sample

With the existing optional Blender, offline Three.js engine bundle and Chromium
tooling configured, run:

```powershell
py -3.12 tools/asset_production_check.py --integrated
```

This extends the existing asset-production rehearsal in one isolated session:
approved scope, three real Blender studies, explicit fixture direction pick,
failing collision check, source refinement, separate independent checks, exact
asset acceptance and separate task acceptance. It then reviews a scope amendment
requiring two parcels per dispatch, freezes failing keyboard/touch expectations,
records a finding, runs a scoped fix preserving the accepted GLB and runtime,
applies the independently checked fix, explicitly closes the finding, accepts
the task separately, runs the current gameplay checks and downloads the handoff.
Re-download equality and a changed-production-evidence rejection are checked too.

The test's model replies and owner responses are explicitly synthetic. Blender
renders/exports, browser input, assertions, files and evidence checks actually run.
It uses no live Muse calls or credits and does not establish live model quality
or Johnathan's artistic/gameplay acceptance. Logs, screenshots and the handoff
remain under ignored `.harness/integrated-sample-checks/`.

For the UI navigation, draft/preview retention and older-server missing-plan
regressions alone, use `tools/browser_check.py --ui-only` with the existing
Playwright/Chromium arguments. The normal browser rehearsal includes those checks.
An old server response missing gameplay-plan state now disables plan editing and
shows a restart instruction instead of reading an undefined revision. Existing
drafts are retained until a valid saved plan arrives.
