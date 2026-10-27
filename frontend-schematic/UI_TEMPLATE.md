# Crucible UI template

Every Crucible screen follows two rule sets:

- **Look:** taste-skill (art direction).
- **Behaviour:** Vercel's Web Interface Guidelines (accessibility, forms, motion, copy).

Check each new page or component against both before opening a PR. Run the guidelines review with the `web-design-guidelines` skill. It fetches the current rules from
`https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md`.

## Look

| Thing | Rule |
|---|---|
| Direction | "The product performs": real, working fragments of Crucible instead of illustrations (taste-skill seed 93808965) |
| Theme | Dark. `--bg #0c0c0d`, `--surface #17171a`, `--surface-2 #222226`, `--ink #f2f2f0`, `--muted-ink #a2a2a8` |
| Accent | `#1c80ba` (`--signal`): the hero stage, colour fields, interviewer state, focus rings, progress. Button fills use the darker `#1a74a9` (`--signal-fill`) so white label text passes 4.5:1 |
| Red | `--danger #e5484d`, failures only: a broken chaos run, missing steps, severity chips. Never on actions |
| Green | `--ok #4cc77a`: tests passed, merge gate passed, fix verified |
| Type | Hanken Grotesk 400/500, plus Geist Mono only inside code. Steps: small 13–14, body 17–19, lead 20–26, head 32–64, display 44–80 |
| Shape | Buttons are square with a 4px radius. Fragments have a 6px radius and 1px `--ui-line` borders, inside `data-ui` only |
| Fragments | Interface fragments use `data-ui` and the `--ui-bg` / `--ui-panel` / `--ui-line` tokens |
| Banned | Gradients, glows, resting shadows, eyebrow labels, 01/02/03 numbering, monospace outside code, rows of identical icon cards |
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

Demo routes on mock data: `/coding/demo`, `/defense/demo`, `/report/demo`.

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
