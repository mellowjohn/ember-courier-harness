# Existing workspace scan and setup

Open a saved session and choose **Plan → Existing workspace · scan & setup**. Enter an
absolute project-folder path, or choose it with **Choose workspace folder…**.
Choose **Prepare workspace scan**, inspect the source and permissions, then
**Approve read-only scan**. The review includes a four-hour workspace scope and
its first scan worker. Later workers need their own contract reviews within
that same scope; approving the scope alone cannot execute actions.

The inventory shows file/directory counts, languages inferred from file
extensions, passive Git branch/commit metadata, asset filename hints and excluded paths. It never runs project code
or a Git command, contacts remotes, calls Muse or uses credits. It reads file
names and metadata, plus bounded `.gitignore`, Git `HEAD` and branch-reference contents. Git config,
hooks, index contents and remotes are not read; worktree dirty state remains
explicitly uninspected. External worktree pointer files and linked Git directories
are identified without following them. Secret-like paths are
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

## Import a supported browser project

After a fresh reviewed scan, prepare a **browser import plan**. This separate
review permits reads of the root's lowercase HTML, CSS and JavaScript files.
The scan worker itself still cannot read game source. After approval, Ember
validates the existing browser profile and displays every selected file's full
content, byte count and SHA-256, the source inventory binding, omitted paths and
destination conflicts. Nothing is copied at planning time.

Review **browser import permissions**, then approve the exact create-only
copy action. It binds the complete manifest, destination and plan hash using
the same workspace contracts and one-time `scaffold_write` approval as setup.
The copy is placed in the session's separate `workspace-imports/` sandbox.
The source is unchanged, no scripts/hooks/package installers are run, and a
pre-existing destination is refused. Source bytes, source inventory, host inputs
and the complete destination set are checked before writes; interrupted approved
copies can resume only with matching bytes and the same action receipt.

The completed import is a snapshot independent of later external source edits.
Changed, missing, linked or added files in its retained sandbox prevent reuse.
Use **Review imported game changes** to prepare the normal scoped exact-build
review in the current session. The copy step alone never replaces the current
game, grants a project scope, accepts an asset or completes a task. The existing
project-plan, exact-build, individual-asset and human-outcome reviews still apply.

## Current boundary

This is bounded onboarding, setup and flat browser-source import, not arbitrary-project
editing or an engine adapter. It scans at most 2,000
directory entries and 20 levels. Each ignore/setup file read is at most 64 KiB,
with a 1 MiB total budget per inventory or plan pass and an approved per-worker
call limit. Unsupported ignore syntax fails the scan rather than silently
including excluded files. Supported rules include ordinary names, anchored and
nested paths, `*`, `?`, `**`, directory rules and negation; escaped patterns,
character classes and brace patterns require a smaller selected folder. Local
`.gitignore` rules apply; global Git excludes and `.git/info/exclude` are not read.
Import supports a root `index.html` and at most eight flat lowercase `.html`,
`.css` and `.js` files, each at most 64 KiB and at most 256 KiB source
in total, validated by the existing browser-project validator. Files are exact
UTF-8 bytes, including their line endings. Unsupported static resource references,
binary/NUL content, links, hard links, secrets and paused engine paths are
refused. Standalone assets and dependency folders are inventoried/omitted rather
than copied. Dynamic dependencies are not executed or independently verified.
Supported structure does not prove startup, game rules or quality;
play and run the normal checks after the separate exact-build review.

Git dirty state, remotes, full engine/asset dependency inventories,
arbitrary scaffold templates and copying arbitrary working source trees remain outside
this slice. Source-file metadata is an observation, not source-content or
behavior verification. The sandbox is deliberately separate from the session's
playable browser-project destination. The complete live Muse quality rehearsal
and Johnathan's integrated human demonstration/playtest remain separate delivery
work; successful automated fixture rehearsals do not satisfy those gates.

Old scan scopes predate source-read/import permissions. Prepare a fresh scan to
use the new import path; no permission is silently added to an approved scope.

Run `py -3.12 tools/offline_tests.py --pattern test_workspace.py` for the
focused regressions. The existing `tools/browser_check.py` rehearsal also uses
the real inventory, plan, contract and exact-action controls, reloads a pending
approval, checks mobile layout, verifies retained sandbox files and runs
contract-lock. Its owner responses are synthetic fixtures; Chromium observations
and file evidence are real.

`py -3.12 tools/offline_tests.py --pattern test_workspace_import.py` covers the
separate read/copy/action reviews, exact adoption source, source-byte changes
with restored metadata, destination conflicts, interrupted replay, independent
snapshots, passive Git metadata, paused scopes and unsupported inputs. All owner
responses in these tests are synthetic; no source code or provider is executed.
