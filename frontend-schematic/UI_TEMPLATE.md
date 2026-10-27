# Crucible UI template

Every Crucible screen follows two rule sets:

- **Look:** the "vivid" theme below (`components/theme/vivid.css`), with liquid glass from the `liquid-glass` skill on small subpanels only.
- **Behaviour:** Vercel's Web Interface Guidelines (accessibility, forms, motion, copy).

Check each new page or component against both before opening a PR. Run the guidelines review with the `web-design-guidelines` skill. It fetches the current rules from
`https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md`.

## Design rules (from Likhil)

- **Aesthetic:** clean, modern, high-contrast, premium typography, restrained palette (at most 3 core colours plus neutrals: here black, blue `#2f6bff`, white), subtle background grain, intentional whitespace.
- **Banned:** glowing gradient text, glassmorphism everywhere (glass only on a few small subpanels over blue), identical boring feature cards, buzzwords such as "supercharge", "seamless" or "delve".
- **Motion:** smooth, subtle scroll animations and micro-interactions that feel organic, not distracting: short travel, no tilt, no bounce easing.
- **Two equal modes:** Live Coding Interview and Project Defense carry the same weight everywhere: matching hero buttons, the same section header layout, and one start dialog with a mode switch.

The "professional hacker" layer (`components/theme/hacker.css`) applies these on top of the base theme: Space Grotesk headings and controls, a blinking `_` cursor on the hero and both wordmarks, `>` shell prompts on section titles (not on buttons), solid square buttons (cobalt primary, hairline-bordered secondary), a few bold white key phrases per paragraph, bracketed status tags, hairline-bordered panels, and black instruments (score box, tracks, chips) wherever a fragment sits on blue.

## Look

| Thing | Rule |
|---|---|
| Direction | Real, working fragments of Crucible instead of illustrations, set in bold solid colour blocks on black |
| Page | Solid black `#000`. Surfaces `#101012` / `#1c1c20`; ink `#fff`, muted `#b4b4bc` |
| Colours | Solid, bright, high contrast: cobalt `#2f6bff` (stages, fields, interviewer), lime `#c6ff1a` (primary action, passes, phase), pink `#ff2e88` (failures, nudges), cyan `#00d4ff`, orange `#ff8a00`. Black text on bright fills, white on dark |
| Gradients | None, anywhere. The only exception is the liquid-glass tint |
| Liquid glass | `<LiquidGlass>` (`components/theme/LiquidGlass.tsx`, port of the skill's refraction) on small subpanels that sit over a solid colour block: the hero interviewer panel, the tour panel, the metric tiles. Children of a glass panel paint no surface of their own |
| Type | Space Grotesk 500 for headings, the wordmark, nav, buttons and labels; Inter for reading text; Geist Mono only for code and terminal cues (file names, timers, tags, the principles panel) |
| Shape | 8px buttons with a 0.97 press; 12–16px radius on cards and colour blocks |
| Banned | Gradients outside liquid glass, eyebrow labels, 01/02/03 numbering, monospace outside code, coloured side stripes on cards |
| Layout | 12-column grid with one pair of margins (`--margin`, safe-area aware). Section gaps 96–140px. No half-empty rows: answer any one-sided block with content on the other side |
| Motion | Masked headline on load, reveal-once on scroll, feedback on every control. Transform and opacity only, each with a `prefers-reduced-motion` fallback |

## Library stack (from the visual-plugins research)

| Need | Use | Notes |
|---|---|---|
| Motion | `motion` as `m` + `LazyMotion` (`components/motion/MotionProvider.tsx`) | `reducedMotion="user"`; messages and stage swaps only |
| Route changes | React 19.3 `<ViewTransition>` in `app/layout.tsx` | 220 ms crossfade; none under reduced motion |
| Live numbers | `@number-flow/react` | Scores, counters, timers |
| Toasts | `sonner` via `components/ui/sonner.tsx` | Dark, top right below the bars |
| Streaming text | `streamdown` | Interviewer replies and problem markdown |
| Code editor | `@monaco-editor/react` + `lib/code-theme.ts` | No autocomplete; flagged lines get a red gutter marker |
| Static code | `shiki` on the server (`lib/highlight.ts`) | Same palette as Monaco; cached at build |
| Topology | `@xyflow/react` + `@dagrejs/dagre` + React Flow UI `base-node` | Still edges; flagged nodes and paths in red |
| Live charts | `uplot` (`components/defense/LiveLoadChart.tsx`) | Canvas, no tweening, streams only while visible |
| Report charts | `recharts` via shadcn `chart` | Flat fills, `accessibilityLayer` |
| Panels and scrubber | shadcn `resizable`, `slider` | Scrubber markers are real buttons |
| Icons | `lucide-react`, plus animated `refresh-cw` and `activity` from lucide-animated | Keep animated icons to a handful |

Demo routes on mock data: `/coding/demo`, `/defense/demo`, `/report/demo`. The landing fragments and these routes read the backend's sample data from `src/lib/fixtures/` (copies of `backend/tests/fixtures/*.json`, typed against the generated `src/types/contracts.ts`): the Quiet Streak coding session and the bank-transfer defense. The room records edits with `lib/capture/editor.ts` and the report replays them with `lib/replay.ts` (both verbatim from `feat/engine-codestate`; never edited here). The defense demo follows PLAN §11.2: Audit → Chaos → Grill → Fix → Verify → Verdict, with the explanation hidden until the grill is graded, code-computed grill scores, "Circle It" on the diagram, per-file editor models in Fix, and a before/after verify chart.

## Behaviour (Web Interface Guidelines, as applied here)

- **Accessibility:** a skip link to `#main`; one `h1` with a heading hierarchy below it; `aria-live="polite"` on interviewer messages and run results; `<button>` for actions and `<Link>` for navigation; real tab semantics with arrow keys for stage switchers.
- **Focus:** every control shows `:focus-visible` (2px `#1c80ba`). Never set `outline: none` without a replacement.
- **Forms:** inputs get a `name`, `autocomplete`, and a label that wraps or points at them. Placeholders end with "…". Submit buttons stay enabled until the request starts. Errors appear inline and get focus.
- **Motion:** honour reduced motion. Anything that auto-advances for more than 5 seconds needs a pause control. Never use `transition: all`.
- **Typography:** use "…", curly quotes and apostrophes, `tabular-nums` for numbers that are compared, and `text-wrap: balance` on headings.
- **Content:** flex children that can overflow get `min-width: 0`. Plan for empty, short and very long content.
- **Locale:** format dates, times, money and counts with `Intl.*`. Put `translate="no"` on brand names, model names and code.
- **Theme:** set `color-scheme: dark` on `<html>` and a `theme-color` that matches `--bg`.
- **Touch:** `touch-action: manipulation` on controls, and `overscroll-behavior: none` only for fine pointers.
- **Copy:** Title Case for headings and buttons; specific button labels ("Start Interview", not "Continue"); second person, active voice.

## Known exceptions

- Landing tab state isn't synced to the URL. It's a marketing tour; the app's room and report screens will put state in the URL.
- Fragment text is 13–15px because that's the interface's real size. The landing's 5-step type scale doesn't apply inside `data-ui`.
