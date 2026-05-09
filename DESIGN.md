# NDX vNext Design Context

## Design Register

Product interface. Design serves repeated research, audit, configuration, and review. It should not behave like a landing page.

## Scene

A focused analyst is using the console on a desktop display during a market review session, with a second browser tab open for the latest brief and workbench. The room is bright enough for long reading, the user is comparing evidence across layers, and the interface must stay calm under dense information.

This scene favors a light, paper-adjacent interface with restrained contrast, crisp rules, compact controls, and selective color for state and risk. Dark mode can be added later, but it is not the default.

## Visual Direction

Use a restrained product palette:

- Tinted neutral background, not pure white.
- Ink should be near black but slightly warm or cool, never `#000`.
- Surface should be subtly separated by borders and spacing, not heavy shadows.
- One primary accent for action and focus.
- Separate semantic colors for risk, caution, good state, and muted metadata.
- Charts may use a fuller palette, but each color must map to a data role.

Recommended OKLCH roles:

- `--bg`: `oklch(0.975 0.006 86)`
- `--surface`: `oklch(0.995 0.004 86)`
- `--surface-muted`: `oklch(0.955 0.008 86)`
- `--ink`: `oklch(0.185 0.012 80)`
- `--muted`: `oklch(0.48 0.018 80)`
- `--rule`: `oklch(0.84 0.012 82)`
- `--accent`: `oklch(0.48 0.11 235)`
- `--risk`: `oklch(0.55 0.16 28)`
- `--watch`: `oklch(0.66 0.12 78)`
- `--good`: `oklch(0.52 0.11 150)`

## Typography

The interface should read like a professional research tool:

- Body text line length should stay near 65 to 75 characters in narrative areas.
- Dense controls should use smaller text, but not below comfortable reading size.
- Section titles should be clear and compact.
- Avoid oversized hero type inside dashboards and consoles.
- Letter spacing should remain normal.

Preferred stack:

```css
font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
```

For numeric tables and command previews:

```css
font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
```

## Layout

The console should prioritize scanning and repeated operation:

- Use full-width bands or grid regions, not decorative nested cards.
- Cards are acceptable for repeated artifacts, individual panels, and compact controls.
- Avoid nesting cards inside cards.
- Keep primary run controls visually close to command preview, status, and latest artifact links.
- Manual data should remain structured and forgiving; empty fields must clearly mean no override.
- Long technical strings should wrap or live in command preview blocks.
- Mobile should collapse to one column without horizontal overflow.

## Interaction

Expected interactions:

- Run button calls the local control service and shows clear connection, success, or failure status.
- Controls update command preview immediately.
- News/event toggle only adds a sidecar artifact flag.
- Workbench module checkboxes update the workbench command preview.
- Evidence and event references should feel clickable and auditable.

Motion should be subtle:

- Use short ease-out transitions for focus, hover, disclosure, and highlight.
- Do not animate layout dimensions in a way that shifts reading position.

## Copy Rules

- Prefer concrete labels over explanatory paragraphs.
- State safety boundaries plainly.
- Do not make the system sound more certain than the evidence.
- Avoid decorative slogans.
- Avoid em dashes.
- Chinese is the default for user-facing explanatory text.

## Absolute Bans

- No gradient text.
- No decorative glassmorphism.
- No colored side-stripe borders on cards or callouts.
- No identical card grids as the main structure.
- No hero metric template.
- No marketing hero on the first screen of a tool.

## Component Direction

- Buttons: clear command labels, compact height, visible disabled and loading states.
- Toggles and checkboxes: use for optional capabilities, especially news sidecar, legacy charts, and workbench modules.
- Segmented controls: use for run mode and model strategy.
- Status text: colocate with the action that caused it.
- Tables: prefer dense but readable rows with sticky or repeated context only where useful.
- Badges: use sparingly for source tier, layer, permission type, confidence, and severity.

## Design Debt To Address Next

- The research console needs a stronger visual hierarchy between setup, run, artifacts, and safety.
- The brief report needs more refined typography and better pacing for continuous reading.
- Workbench controls should feel more like a research instrument than a generated chart page.
- Event refs and evidence refs should be visually distinct.
- PRODUCT.md and DESIGN.md should be revisited after the next serious UI polish pass.
