# Manual concept selection and gated asset ingest

This implemented slice starts with three or four supplied original PNG concepts,
one image per direction. It checks technical validity, records an immutable
review bound to approved input hashes and inherited art direction, waits for
Johnathan's selection, and copies the selected file into an approved destination.
Johnathan then accepts the ingested asset separately. Both decisions require
an explicit one-use action approval even under `approve_all`.

The concept generation, hero/impact pairs, palette images, comparison-sheet
layout, artistic scoring, refinement, conversion and engine stages in the held
design specifications remain future work. This implementation does not claim
full CS-T coverage, automated visual QA, original authorship verification or
engine readiness. Technical checks never establish artistic acceptance.

## Contract and files

Create a scope proposal using `scope-propose ... --asset-workflow`. This optional
flag adds `concept.select`, `fs.copy` and `asset.accept` capabilities to the
proposal's existing `WORKSPACE/scope-output/**` boundary. Review the resulting
permissions and obtain Johnathan's explicit approval using the existing flow.
An already approved scope without these tools must be amended and reviewed;
the flag never changes existing authority.

Put the supplied PNGs and a UTF-8 manifest beneath `scope-output/`. Create the
desired destination parent folder before ingest. The manifest is:

```json
{
  "topic": "Ember Courier player",
  "candidates": [
    {"slug": "ember-drop", "path": "D:/project/scope-output/candidates/drop.png", "sha256": "64_LOWERCASE_HEX_CHARACTERS", "pitch": "Rounded ember silhouette", "target": [128, 128], "require_alpha": true},
    {"slug": "ember-star", "path": "D:/project/scope-output/candidates/star.png", "sha256": "64_LOWERCASE_HEX_CHARACTERS", "pitch": "Pointed ember silhouette"},
    {"slug": "ember-crystal", "path": "D:/project/scope-output/candidates/crystal.png", "sha256": "64_LOWERCASE_HEX_CHARACTERS", "pitch": "Faceted ember silhouette"}
  ]
}
```

Substitute real resolved absolute paths and SHA-256 values. Slugs and resolved
source paths must be unique. Only nonempty, fully decoded, single-frame PNGs
are supported, at most 8 MiB and 16,777,216 pixels each. Declared target dimensions
must match exactly; without a target there is no arbitrary minimum size.
`require_alpha` checks for an alpha channel or PNG transparency information,
not artistic transparency quality. Manifest size is limited to 64 KiB.

## Propose the child, approve and review

```powershell
py -m ember_harness --store STORE asset-draft --scope SCOPE_ID --manifest MANIFEST_PATH --id ct-assets-0001 --agent asset-worker
```

Save that JSON as UTF-8, run `review` and `save`, and have Johnathan approve its
reviewed hash using `approve ... --parent SCOPE_ID`. The draft pins the manifest
and all supplied source hashes, inherits art direction, uses the resolved parent
window and remains within its capability ceiling. Draft creation only reads
the manifest to propose inputs; it neither decodes candidates nor grants authority.

```powershell
py -m ember_harness --store STORE verify-inputs ct-assets-0001
py -m ember_harness --store STORE concept-review --contract ct-assets-0001
```

Review gates each source inspection, checks the approved hashes and technical
requirements, and returns `awaiting_pick`, a `review_ref` and the candidate paths,
pitches, dimensions, alpha results and inherited art direction/hash. The snapshot
is saved at `STORE/concepts/REVIEW_REF/review.json`; its hash is linked to the audit.
Open and visually inspect the candidate files before making a real owner choice.
No recommendation or quality score is fabricated.

## Owner selection, ingest and acceptance

```powershell
py -m ember_harness --store STORE concept-select REVIEW_REF --contract ct-assets-0001 --choice ember-drop
```

The response is `needs_approval` and includes an exact `approval_action` object.
Save only that object as UTF-8 JSON. After Johnathan explicitly approves the
choice, the trusted host records it with `approve-action ACTION.json --quote
"EXACT_OWNER_WORDS"`. Rerun the same `concept-select` command to consume the
one-use approval and record the selection. Approval methods belong only to
Johnathan or a trusted host relaying his real decision; they do not authenticate
identity and must remain outside agent toolsets. A different choice needs a
different approval. A recorded selection is immutable for that review; a new
pick requires a reviewed contract amendment.

```powershell
py -m ember_harness --store STORE asset-ingest REVIEW_REF --contract ct-assets-0001 --dest DESTINATION.png
py -m ember_harness --store STORE asset-status REVIEW_REF --contract ct-assets-0001 --dest DESTINATION.png
py -m ember_harness --store STORE asset-accept REVIEW_REF --contract ct-assets-0001 --dest DESTINATION.png
```

Ingest requires the earlier selection, active authority, unchanged approved
inputs and an allowed `fs.copy` decision. It captures the pinned source bytes,
creates the destination exclusively, flushes them, checks the resulting hash
and records source/destination evidence. It rejects **every existing destination**,
including identical content. No destination parent folders are created by the
adapter. No conversion, generation, network access or engine action occurs.

The initial status is `awaiting_acceptance`. `asset-accept` returns another exact
approval action; obtain Johnathan's separate approval with `approve-action`, then
rerun `asset-accept`. Acceptance requires fresh complete copy evidence and an
unchanged destination. A technical pass or concept selection cannot accept it.

`asset-status` recomputes source, manifest and destination hashes and refreshes
copy evidence. Changed bytes become `incomplete`; restored original bytes may
again match the historical acceptance. Historical audit approvals are preserved.
Revocation or expiry prevents further operations. New contract versions require
new review snapshots and selections; old approval tokens cannot cross versions.

## Verification and recovery

`contract-lock` verifies review snapshot hashes, pinned manifest/source bindings,
art direction hashes, inspection decisions, exact owner approvals, selections,
copy decisions and acceptance evidence links. Historical verification uses the
retained snapshot and audit; it does not require original working files to stay
unchanged. Use `asset-status` to check current bytes. The audit is a trusted local
record, not independently authenticated external proof.

An audit or evidence failure never creates an accepted asset. A failure after
exclusive file creation can leave an unclaimed file, which is never silently
overwritten on retry. Inspect it and select a new approved destination or resolve
it manually; this adapter performs no deletion. Harness operations serialize
through the local writer lock and recheck authority before mutations. This is
not OS isolation: another process changing filesystem links concurrently remains
a host-level race, as in the base contract implementation.

```powershell
py examples/asset_demo.py
py -m unittest discover -s tests -p test_assets.py -v
py tools/release_check.py
```

The CLI demo uses three original procedural test silhouettes and explicit
simulated approvals in an isolated store. It proves selection, ingest,
separate acceptance under `approve_all`, overwrite and outside-path refusal,
changed source/destination detection, restoration, contract-lock and scope
revocation. Reports with the three images are retained at
`.harness/demos/assets-*/ASSET_DEMO.md`. These are fixture approvals, not real
production selections or asset acceptances. The release gate includes the
workflow as its eleventh standalone offline demo.
