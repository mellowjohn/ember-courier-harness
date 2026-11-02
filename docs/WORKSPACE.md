# Existing workspace scan and setup

Open a saved session and choose **Plan → Existing workspace · scan & setup**. Enter an
absolute project-folder path, or choose it with **Choose workspace folder…**.
Choose **Prepare workspace scan**, inspect the source and permissions, then
**Approve read-only scan**. The review includes a four-hour workspace scope and
its first scan worker. Later workers need their own contract reviews within
that same scope; approving the scope alone cannot execute actions.

The inventory shows file/directory counts, languages inferred from file
extensions, Git-metadata presence and excluded paths. It never runs project code
or a Git command, contacts remotes, calls Muse or uses credits. It reads file
names and metadata, plus bounded `.gitignore` contents. Secret-like paths are
listed by name only. Links, junctions, special files, dependency/generated
directories and paused engine paths are excluded. Engine roots are refused.
The source must be outside the session-store ancestor so reports cannot write
into the scanned tree. Selecting a folder retains an inventory in this session;
it does not retarget the browser project's existing write permissions.

Choose **Prepare setup plan**, then **Approve setup planning**. Ember checks the
inventory again and compares existing setup files by hash. The resulting plan
shows every proposed file, its full content, byte count and one of:

- `create`: missing in the source; eligible for the sandbox rehearsal.
- `skip_exists`: already has identical bytes; omitted from writes.
- `conflict`: existing bytes differ; omitted from writes.
- `manual`: configuration requiring separate decisions, currently LFS routing.

The fixed setup proposes `AGENTS.md` and explanatory README files under
`contracts/`, `evidence/`, `intents/` and `triage/`. Existing owner instructions
are preserved; the contracts guide remains available when `AGENTS.md` conflicts.
The setup files grant no authority themselves.

Choose **Review sandbox setup**, review **Approve sandbox permissions**, then
review the complete diff again and **Approve exact sandbox setup**. The latter
is a separate one-time `scaffold_write` approval bound to the canonical plan
hash, destination and complete create list. The sandbox lives under this saved
session's `workspace-sandboxes/`; it contains only new setup files. Source game
files, secrets, conflicts and identical setup files are not copied. The host
checks the entire target set before writing, uses exclusive file creation and
verifies the exact resulting bytes and file-list evidence. It never overwrites
or deletes a source or sandbox file.

Requests, inventory, plans, evidence and owner receipts survive reopening a
session or restarting Ember. **Resume approved workspace step** reuses existing
authority after an interruption; it cannot renew its time window or invent an
approval. A stopped or stale run can be replaced with a new scan after any
pending review is discarded. Changes to pinned evidence, source inputs, targets,
contracts or scope authority stop execution. No cleanup removes earlier evidence.

## Current boundary

This is bounded onboarding and a setup rehearsal, not arbitrary-project editing,
source import, an executable copy or an engine adapter. It scans at most 2,000
directory entries and 20 levels. Each ignore/setup file read is at most 64 KiB,
with a 1 MiB total budget per inventory or plan pass and an approved per-worker
call limit. Unsupported ignore syntax fails the scan rather than silently
including excluded files. Supported rules include ordinary names, anchored and
nested paths, `*`, `?`, `**`, directory rules and negation; escaped patterns,
character classes and brace patterns require a smaller selected folder. Local
`.gitignore` rules apply; global Git excludes and `.git/info/exclude` are not read.

Git branch, dirty state, remotes, general engine detection, asset/run inventories,
arbitrary scaffold templates and copying a working source tree remain outside
this slice. Source-file metadata is an observation, not source-content or
behavior verification. The sandbox is deliberately separate from the session's
playable browser-project destination. The complete integrated sample, live Muse
quality rehearsal and human playtesting remain separate delivery work.

Run `py -3.12 -m unittest discover -s tests -p test_workspace.py -v` for the
focused regressions. The existing `tools/browser_check.py` rehearsal also uses
the real inventory, plan, contract and exact-action controls, reloads a pending
approval, checks mobile layout, verifies retained sandbox files and runs
contract-lock. Its owner responses are synthetic fixtures; Chromium observations
and file evidence are real.
