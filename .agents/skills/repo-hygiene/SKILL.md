---
name: repo-hygiene
description: Keep Ember Harness changes small and generated output out of source control when adding workflows, demos, tests, or dependencies.
---

# Repository hygiene

Before adding a workflow, inspect its existing adapter, demo and tests. Prefer a
small extension or shared entry point over copying a complete pipeline. Avoid a
new abstraction or dependency unless the current task needs it.

Generated contracts, fixture images, nested sample Git repositories, execution
captures, reports, wheels and install checks belong under the ignored `.harness/`
directory. Keep reusable fixture generators in source rather than checking in
one generated asset per run. Temporary tests must clean up their own directories;
use an ignored scratch location when preserving output is necessary.

Keep one canonical implementation and one focused guide per workflow. Link to
existing setup and approval instructions instead of copying whole documents.
Add tests for meaningful behavior and cross-workflow failures; do not duplicate
the entire test suite or assert documentation wording.

Before finishing, inspect `git status --short`, `git diff --stat`, and
`git diff --check`, including newly created files. Confirm generated output is
ignored with `git check-ignore`. Do not add ignore patterns merely to hide source
changes. Report the source files added and any new dependency.

Never delete the user's artifacts, approvals, audit evidence or previous demo
runs solely to reduce disk usage. Inspect paths and retention needs first; keep
cleanup scoped to temporary files created for the current task. The contract
and permission rules in AGENTS.md continue to apply.
