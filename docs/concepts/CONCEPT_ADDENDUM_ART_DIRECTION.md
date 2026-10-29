> Public pack copy for ember-courier-harness. Original team draft paths may still mention /workspace/...; treat those as historical source locations, not runtime paths in this repo.

# Concept step addendum: art_direction (2026-10-23)

Documentation only. `CONCEPT_STEP_SPEC.md` is held and untouched; this file supersedes parts of it by note. Test ids use the `CS-T` prefix.

## 1. How the concept step uses `art_direction`
- The concept step reads the `art_direction` block (style, palette, mood, references, do, dont) that the build contract inherits from the scope contract. It records that block's sha256 in its evidence.
- Every direction's `notes.md` gets a new final section, `## Art direction fit`. It has one line per criterion (style, palette, mood, do, dont) saying how the direction meets it, and it cites the `art_direction` hash.
- `## Palette` lists the direction's 5 hex values. Each value must come from `art_direction.palette` or be marked `(variant of #XXXXXX)`.
- Every reference image is a local file listed in `art_direction.references` with its sha256. No web references, and nothing copyrighted or trademarked.
- The concept step never approves anything. The verifier writes `art_score`, and Johnathan accepts or rejects each direction, including under approve-all.

## 2. What the verifier scores for concepts
Each criterion gets a score from 0 to 1, a confidence, and evidence: the file, region or crop, plus one sentence explaining the score.
1. **Silhouette:** the shape reads clearly at gameplay distance, checked on a crop downscaled to 128 px on its long side.
2. **Palette match:** sampled swatches from the hero image sit near `art_direction.palette`.
3. **Mood and style:** the image matches `art_direction.style` and `mood`.
4. **Do and dont:** each entry passes or fails, with evidence for that entry.
5. **Buildable:** the image uses only effects the target pipeline lists, given as `art_direction.do` and `dont` entries.
A low score becomes an amendment naming `failing_step: concept`. The cap stays at 3 attempts per step.

## 3. Superseding notes on CS-T checks
- **CS-T3 and CS-T4:** These become pass/fail technical gates under the ruling Hack Lead set on Oct 23. First, the file must open and must not be empty. Second, if the contract declares a target size for that asset, the dimensions must match it exactly. Numeric minimums and Q2 are void.
- **CS-T7:** The fixed last value `#0B0807` is dropped. The 5 values must be distinct, valid hex values that follow section 1.
- **CS-T8:** Unchanged.
- **CS-T14:** The heat-distortion string check stays in the Wrathful Conquest reference example only. For any other project it's driven by `art_direction.dont`.
- **New CS-T15:** Every `notes.md` has `## Art direction fit`, and the hash it cites equals the contract's `art_direction` hash.
- **New CS-T16:** An `art_score` evidence record exists for each direction, was written only by the verifier, and has a score, confidence and evidence for each criterion.

## 4. Wrathful Conquest reference example (not the hackathon demo)
This is a reference example only. The demo's sample game gets its `art_direction` from Johnathan's intent. Everything below is original Wrathful Conquest material with no third-party references.
```json
"art_direction": {
  "style": "low-poly dark fantasy; magic glows out of carved stone; warm emissive on dark stone",
  "palette": ["#FFE27A", "#FF9A1F", "#E8501A", "#8A1E0C", "#0B0807"],
  "mood": "heavy, molten, ominous; heat without haze",
  "references": [
    {"path": "/workspace/sc22/<VC-02 approved sheet>", "sha256": "<fill at run>"},
    {"path": "/workspace/concepts/fireball/molten-slag/molten-slag_hero.png", "sha256": "<fill at run>"}
  ],
  "do": ["silhouette reads at gameplay distance", "emissive graphs, noise-scrolled UVs, bloom, particles, point lights only", "dark crust over a bright core"],
  "dont": ["heat distortion or refraction", "lore or story text", "copyrighted or trademarked imagery", "cool or neon hues as the dominant color"]
}
```

## 5. Deferred `notes.md` migration
Not done, and no files moved. When v4 settles, the four `/workspace/concepts/fireball/*/notes.md` files get only the `## Art direction fit` section, citing the hash of the section 4 block. Images and code are not touched.
