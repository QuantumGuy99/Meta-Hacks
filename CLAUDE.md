# Crucible — Agent Operating Rules (whole team)

Read `@README.md` before writing code. `PLAN.md` is the team's build plan (1,700+ lines): read the
sections your task needs (§6 layout and ownership, §7 contracts, §22 agent rules) instead of all of it.
Your own build order, handoff dates and interfaces are in `plan/<your-name>.md`.

## Area rules
Each area can keep its own rules in a nested `CLAUDE.md`, which Claude Code loads when you work in that
folder. They add to this file and never loosen it. So far:
- Project Defense + Runner (Shreyas): `backend/crucible/defense/CLAUDE.md` (also loaded from `runner/`).
- Backend code style (everyone): `backend/CLAUDE.md`. File templates: the `crucible-code` skill.

## Source of truth
`PLAN.md` is the spec; `plan/*.md` are each person's slice of it (PLAN wins; fix the role plan in the same
PR, §22 rule 15). If PLAN and the code disagree, or a task is ambiguous, stop and ask the area's owner
(§6), then fix whichever is wrong in the same PR.

## Non-Negotiable Architecture Laws
1. **Stay in your lane:** edit only the paths your work package's owner owns (PLAN §6, your role plan)
   plus tests. If you need a change in someone else's area, note it in the PR or ask them.
2. **Contracts First:** every WebSocket/REST payload and timeline event is a Pydantic model in
   `backend/crucible/contracts/` (`Strict`, `StrEnum`, no defaults on LLM output models). Changes need
   SG + SS approval and `make contracts`. Never hand-edit `frontend/src/types/contracts.ts`.
3. **LLM Suggests, Code Decides:** models return structured judgements; Python decides scores, verdicts,
   phase changes and what the user sees, and every outgoing interviewer text passes the leak guard.
4. **Never hand over the answer:** hidden tests, rubrics, reference solutions and Defense finding
   explanations stay server-side until the product is allowed to reveal them.
5. **Meta models only at runtime,** through `backend/crucible/models/` (model ids only in `registry.py`
   / env). No api.openai.com, api.anthropic.com or third-party TTS in application code.
6. **Timeouts and fallbacks on every external call** (PLAN §21). MOCK replay only when `MOCK=1` is set
   explicitly; a real failure never silently returns recorded data.
7. **Untrusted code runs only in the Runner** (Modal sandbox; LocalRunner is dev-only).
8. **Secrets stay in `.env`** (read only by `config.py`); never in git, logs, chat or the browser.
9. **No license headers in source files.** The repo's `LICENSE` file and the README's License section
   stay as they are; just don't add license comments to code.
10. **No AI attribution lines** in commits or PR descriptions (no `Co-Authored-By:` an AI tool, no
   "Generated with ..." footer). `.claude/settings.json` turns them off for Claude Code.

## Model roles (Claude Code subagents: pass `model` to the Agent tool)
- **Architect (Opus 5.5, the main session):** owns blueprints, contracts, guardrails and error-recovery
  policy. Breaks work into tasks with explicit file lists and "done when" criteria, reviews every diff
  before commit, and is the only role that changes contracts, PLAN.md, area specs or these rules.
- **Builder (`model: "sonnet"`):** implements feature logic inside the files the task names, following
  `backend/CLAUDE.md` and the `crucible-code` skill. Doesn't invent architecture: if the task needs a new
  contract, file or dependency, stop and report back.
- **Operator (`model: "haiku"`):** runs tests, `ruff format`/`ruff check --fix`, boilerplate (fixtures,
  test scaffolds, empty modules from templates) and short scripts. Reports output verbatim and never
  changes logic to make a check pass.
- Every task brief names: files allowed, PLAN sections to read, the checks to run, done-when. If your
  area keeps a working-memory file, claims go there under the role's name (`[builder]`, `[operator]`).

## Fallback protocols
- **Test failure loop:** the same failure twice → the Operator stops and hands the output to the Builder.
  Builder fails two fix attempts → the Architect reviews the design before any third attempt. Never
  delete, skip or loosen a test or assertion to go green without the Architect's explicit OK.
- **Code drift:** before commit, the Architect checks the diff against the task's file list and the
  contracts. Edits outside scope, contract changes, new dependencies or new model ids → revert that part
  and re-plan.
- **Spec conflict or ambiguity:** any role stops and escalates to the Architect, who asks the area owner
  if PLAN.md doesn't settle it. Never guess on contracts, ownership or scoring rules.
- **Lint autofix changes behaviour** (or ruff can't fix it) → Builder, not Operator.
- **Context running out or a task stalls** (3+ rounds without progress): write a handoff (your area's
  memory file, or the PR description), end the subagent, and restart it fresh from that handoff.
- **A model is unavailable or too weak for the task:** escalate up (Haiku → Sonnet → Opus), never down
  for design decisions or reviews.
- **Main moved:** `git fetch` and compare with `origin/main` before starting and before pushing.

## Verification (before you say you're done)
- Backend: `uv run ruff check backend/` and `uv run pytest` (plus `MOCK=1 uv run pytest` once MOCK lands).
- Frontend: `pnpm --dir frontend exec tsc --noEmit` and `pnpm --dir frontend lint`.
- `make check` runs all of it once S-0 lands.
