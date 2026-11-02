# Findings and verified browser fixes

The default fix flow needs only **Playtest notes** below the game. Type or dictate
what went wrong, then choose **Find & fix bug**. **Tester agent** jumps to those
notes. This works with an approved game, with or without a project plan or saved
gameplay checks. An approved scope still constrains every proposed change.

Ember makes a separate source investigation before generating a targeted repair.
The progress card shows reading, investigation, code preparation, review and file
application. It retains the suspected cause, repair plan, examined files and
elapsed time. These are source-review hypotheses, not claims of browser
reproduction. The proposed source passes the normal format, file and scope gates;
try it or run saved gameplay checks before accepting it. **Approve & play** is
still the exact decision that writes project files. Applied filenames and the
saved version provide the completion receipt; elapsed time is never used as a
measure of correctness.

New notes-only fixes use high reasoning effort for both source investigation and
repair, with up to fifteen minutes per call (thirty minutes for at least 48 KiB of
editable source). The active allowance appears in progress. This gives complex
work more room; notes-only fixes still require gameplay verification and do not
automatically iterate or claim resolution. Reviewed task runs provide the
separate bounded verification/repair loop.

The two calls share a $10 maximum reservation within the existing promotional
credit ledger. A stable report ID prevents duplicate inference. Failed generation
can reuse its retained investigation on retry, including after restart. Pending
proposals, changed project bytes and stale reports stop another fix. Notes-only
fixes do not manufacture formal bug closures or task acceptance.

**Dictate** beside chat and playtest notes uses the browser's SpeechRecognition
or webkitSpeechRecognition API. Click it to start, allow the microphone, then
choose **Stop dictation** and review the editable text before sending. One field
records at a time; sending, switching sessions, leaving the page or replacing
the preview stops recognition. Unsupported browsers and microphone/service
errors leave typing available. Audio processing is handled by the browser and
may use its online service. Ember does not upload or retain an audio recording.
Real microphone/service quality is separate from simulated browser regression
checks. No transcription service, credentials or paid fallback is added.

## Optional formal finding and closure workflow

Use an approved **Project plan & tasks** scope with an applied browser build.
Existing scopes need **Amend or renew project plan** to review the added intake,
QA and closure permissions. This uses the existing amendment acknowledgement and
approval rules. It does not authorize paused engine work.

1. Expand **Checks & advanced refinement → Findings & fixes → Advanced finding tools**. Describe the bug, how to repeat
   it, what should happen and what happened instead, then choose **Review finding**.
   This records your description against the current approved build without a
   separate playtest step or Muse call. **More details (optional)** includes area,
   frequency, impact and an existing problem report. You can also play the preview,
   use a previously recorded problem. Browser diagnostics stay
   untrusted clues; they cannot create or close bugs by themselves.
2. In **Findings & fixes**, inspect the plain-language report, copied evidence and narrow
   intake/QA contracts, then **Approve finding intake**. No Muse call occurs.
3. Review the queue. Missing details remain **needs repro**. **Update reproduction**
   prepares a reviewed update using a current problem report and the current bug
   hash. **New finding** clears the update selection. Fingerprints suggest
   duplicates; **Confirm duplicate** records an explicit QA decision. Critical
   severity proposals require a severity review. Review notes are your recorded
   QA judgments, labeled separately from automated checks.
4. Save a gameplay scenario whose assertion reproduces the problem. Choose that
   scenario beside the canonical triaged finding, then **Review tester agent**.
   Review the coding and independent verifier contracts and **Start tester agent**.
   Blocked launch controls explain the next step; **Set up gameplay check** opens
   the existing checks editor when no scenarios are saved. **View tester agent
   progress** returns to the current run in chat.
   The frozen scenario must fail an observable assertion on the original build
   before Muse is called. A startup error alone does not satisfy this requirement.
5. A separate verifier runs the same frozen gameplay plan on the candidate and
   assesses its source and desktop/touch captures. All scenarios must pass, with
   no startup/overflow findings and no AI issues. The verifier cannot edit the
   candidate or change the plan. **Review proposed fix** prepares the usual
   proposal; preview it and **Approve & play** to apply exactly those bytes.
6. Choose **Review verified closure**, inspect the evidence, then **Approve bug
   closure**. Closure always has its own exact action approval in this workflow,
   including S0/S1 under an `approve_all` project scope. Applying the build and
   passing checks leave the finding open until this decision. Task acceptance
   and individual asset acceptance remain separate.

One reviewed fix run allocates one attempt in the existing per-bug ledger and
allows one coder/verifier pair, bounded to $10 of the shared promotional credits.
A failed independent report consumes the attempt. Three approved attempts block
further fixes until **Authorize one extra attempt** records the current owner
decision. Creating a new run, renewing scope or reopening a bug does not reset
the count. Stopping consumes the allocation by ending its worker attempt. An interrupted
provider can resume the same allocation and verified artifacts, with the existing
credit reservations and saved-response replay.

Use **Review classification or recurrence → Reopen recurring finding** for a
closed bug. This preserves its closure receipt and attempt history. Record a new
problem on the current build and review an updated reproduction before another
fix. Duplicate merges after attempts have started require the existing owner
reconciliation workflow; the browser duplicate button fails closed in that case.
Engine and non-code routes cannot start a browser fix.
Browser fixes preserve prepared `engine.js` and `asset.js` bytes exactly. Native
asset/source corrections use the separate asset-production/refinement workflow.

The browser closure receipt maps C0 to the frozen failing baseline, C1 to the
separate candidate report, C2 to the exact applied build and C3 to explicit owner
closure. These are browser witnesses. General Git workers, local commit trailers,
clean base/head Git rounds and failure-driven scope amendments remain the
separate library workflows. Scope changes use the existing reviewed amendment
controls; a finding does not silently widen the project scope.

Changed bug details, scope, project files, gameplay plans, provider/runtime
inputs or retained captures block the relevant continuation, promotion or
closure. Contract-lock rechecks historical browser closure evidence even after
the current project advances. Sessions, evidence and audit records remain under
ignored `.harness/` paths; game ZIPs do not include private finding history.

`tests/test_findings.py` covers intake, routing, duplicates, critical review,
frozen regression proof, exact application, explicit closure, interruption,
three-attempt escalation, reopening, tampering and HTTP authorization. The
expanded `tools/browser_check.py` operates the actual desktop/mobile controls and
real Chromium regressions. Provider replies and owner decisions in these checks
are synthetic. Live Muse fix quality and human playtesting remain delivery gates.
