# Ember theme, typography and iconography

Open **Project tools → Typography & icons** for the live reference. It uses the
same library as the conversation, controls and work status. Known assets has its
own **Project tools → Known assets** section.

The canonical files are `ember_harness/ui_library.css` and
`ember_harness/ui_library.js`. Both ship with the local app. No external fonts,
icon service or new dependencies are needed.

## Ember studio theme

The local workspace uses charcoal surfaces, warm orange controls and copper
borders. The shared palette lives in `ui_library.css`: `--canvas`, `--sidebar`,
`--surface`, `--surface-raised`, `--surface-inset`, `--surface-selected`, `--line`,
`--line-strong`, `--ink`, `--ink-muted`, `--accent` and `--accent-soft`.
Use these tokens for new workspace surfaces. Success, warning and failure retain
separate semantic colors, visible labels and icons.

The game preview's empty-state ember uses the original SVG flame and CSS particles.
Both particles and the glow pause under `prefers-reduced-motion`. The decorative
scene is hidden from assistive technology and makes no network requests. Game
contents retain their own art direction inside the isolated preview.

Game-idea shortcuts fill and focus an editable chat draft. They never submit a
message or call Muse. The first-launch welcome opens the existing session dialog.

## Typography

Use the local Segoe UI Variable / Segoe UI / system font stack for interface text,
and Cascadia Code / Consolas / monospace for paths and evidence. Display headings
use the local Bahnschrift / Arial Narrow / Segoe UI stack. Shared type sizes use `rem`
so browser text-size preferences work. Keep the body’s relaxed 1.6 line height.

| Role | Class | Token | Use |
| --- | --- | --- | --- |
| Display | `type-display` | `--text-display` | Main page titles, fluid size |
| Heading | `type-heading` | `--text-heading` | Major sections |
| Title | `type-title` | `--text-title` | Cards and panels |
| Body | `type-body` | `--text-body` | Conversation and reading |
| Label | `type-label` | `--text-label` | Fields and controls |
| Caption | `type-caption` | `--text-caption` | Timestamps and supporting text |
| Overline | `type-overline` | `--text-caption` | Short section labels |
| Code | `type-code` | `--text-caption` | Paths and evidence |

The library also applies these roles to existing semantic elements and core UI
selectors. Use the classes for new surfaces and the tokens for new components;
avoid adding another hardcoded size for the same role.

## Iconography

The original SVG set uses a 24 × 24 view box, rounded 1.7-unit strokes and
`currentColor`. `EmberUI.iconNames` lists every available name. Sizes are `small`
(1rem), `medium` (1.25rem) and `large` (1.75rem).

```js
button.append(EmberUI.icon('assets', 'small'));
EmberUI.label(button, 'Known assets', 'assets');
```

`label` replaces the contents with an icon and safe text. Known control labels
have defaults in `EmberUI.actions`; the shared `el` helper applies those defaults
to buttons, links, summaries and section headings. Use `label` again when a
control's text changes. Keep visible labels with icons; icon-only controls need
an accessible name on the control. SVGs are decorative and hidden from assistive
technology. Never inject provider or user content as SVG or HTML.

## Working status

```js
EmberUI.status(panel, {
  phase: 'muse_working', state: 'active',
  context: 'Current task · Build the delivery route'
});
```

Friendly messages correspond to observed phases. Unknown phases keep the real
provided title. The current task is shown when available; otherwise the actual
phase title is the context. Elapsed time, observed response counts, quiet-period
notices and expandable request history remain available. Do not cycle through
invented tasks or show made-up completion percentages. Interrupted and failed
requests have distinct, explicit explanations and no animated dots. The ellipsis
uses three decorative dots and respects `prefers-reduced-motion`.

## Message keyboard behavior

Enter submits the main composer through its existing form. Shift+Enter adds a
line. Composition/IME events, modified Enter and held-key repeats never send.
Empty drafts and active requests cannot submit, and the existing explicit retry
flow is unchanged. The shortcut hint is linked to the textarea for screen readers.
