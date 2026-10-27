# Crucible — Agent Operating Rules (Shreyas: Project Defense & Runner)

Read `@DEFENSE_AGENT_SPEC.txt` and `@README.md` before writing code. `PLAN.md` is the team's build plan
(1,700+ lines): read the section you need (§6 layout, §7.4 defense contracts, §11 Defense, §12 Runner,
§19 deploy, §22 agent rules) instead of loading all of it.

## Context between sessions
`@docs/defense/MEMORY.md` is the shared working memory for Claude Code and Muse Code: claim files there
before editing, and update status, handoff and session log before you finish. Build order, handoff
dates and interfaces: `plan/shreyas-defense-and-runner.md`. How code is written: `backend/CLAUDE.md`.
File templates: the `crucible-code` skill.

## Source of truth
`PLAN.md` is shared with Srinithin (engine), Likhil (frontend) and Sharvil (data); the spec is the
Defense briefing and agrees with it. Earlier conflicts are resolved in the spec's §9 decision log, so
don't reopen them. If you find a new disagreement, stop and ask Shreyas, then fix both files in the same PR.

## Non-Negotiable Architecture Laws
1. **Scope:** Create/edit only SS-owned paths: `backend/crucible/defense/`, `backend/crucible/runner/`,
   `backend/crucible/models/glimmer.py`, `backend/crucible/mock/`, `frontend/src/lib/defense.ts`, the
   scaffold (Makefile, CI, `.env.example`, `backend/pyproject.toml`, Dockerfile, `main.py`, `config.py`,
   `store/`) and tests. `contracts/` needs SG + SS approval; `engine/`, the rest of `models/`,
   `data/defense_apps/` and other `frontend/` files belong to teammates. Note needed changes instead.
2. **Contracts First:** Every WebSocket/REST payload and timeline event is a Pydantic model in
   `backend/crucible/contracts/` (`Strict`, `StrEnum`, no defaults on LLM output models). Run
   `make contracts` after any schema change. Never hand-edit `frontend/src/types/contracts.ts`.
3. **LLM Suggests, Code Decides:** Models return structured judgements (`GrillEval` points hit,
   `AttackFunctions` bodies); Python computes scores, verdicts and phase changes, validates attack
   code, and runs every outgoing text through the leak guard. A model never opens the Merge Gate.
4. **Never reveal the answer early:** `Finding.explanation` stays server-side until that finding's grill
   is graded (`defense.audit` sends `AuditPublic`).
5. **Meta models only at runtime,** through the shared wrapper (`models/llm.py`, `asr.py`, `sam.py`,
   `image.py`, `glimmer.py`); model ids only in `models/registry.py` / env. No api.openai.com,
   api.anthropic.com or third-party TTS.
6. **Timeouts and fallbacks on every external call** (PLAN §21). MOCK replay only when `MOCK=1` is set
   explicitly; a real failure never silently returns recorded data.
7. **Untrusted code runs only in the Runner** (Modal sandbox; LocalRunner is dev-only).
8. **No License Headers:** Do not add MIT license references anywhere.

## Model roles (Claude Code subagents: pass `model` to the Agent tool)
- **Architect (Opus 5.5, the main session):** owns blueprints, contracts, guardrails and error-recovery
  policy. Breaks work into tasks with explicit file lists and "done when" criteria, reviews every diff
  before commit, and is the only role that changes contracts, PLAN.md, the spec or these rules.
- **Builder (`model: "sonnet"`):** implements feature logic inside the files the task names, following
  `backend/CLAUDE.md` and the `crucible-code` skill. Doesn't invent architecture: if the task needs a new
  contract, file or dependency, stop and report back.
- **Operator (`model: "haiku"`):** runs tests, `ruff format`/`ruff check --fix`, boilerplate (fixtures,
  test scaffolds, empty modules from templates) and short scripts. Reports output verbatim and never
  changes logic to make a check pass.
- Every task brief names: files allowed, PLAN/spec sections to read, the checks to run, done-when.
  Claims go in `docs/defense/MEMORY.md` under the role's name (`[builder]`, `[operator]`).

## Fallback protocols
- **Test failure loop:** the same failure twice → the Operator stops and hands the output to the Builder.
  Builder fails two fix attempts → the Architect reviews the design before any third attempt. Never
  delete, skip or loosen a test or assertion to go green without the Architect's explicit OK.
- **Code drift:** before commit, the Architect checks the diff against the task's file list and the
  contracts. Edits outside scope, contract changes, new dependencies or new model ids → revert that part
  and re-plan.
- **Spec conflict or ambiguity:** any role stops and escalates to the Architect, who asks Shreyas if
  PLAN.md and the spec don't settle it. Never guess on contracts, ownership or the merge-gate rules.
- **Lint autofix changes behaviour** (or ruff can't fix it) → Builder, not Operator.
- **Context running out or a task stalls** (3+ rounds without progress): write the handoff to
  `docs/defense/MEMORY.md`, end the subagent, and restart it fresh from that handoff.
- **A model is unavailable or too weak for the task:** escalate up (Haiku → Sonnet → Opus), never down
  for design decisions or reviews.
- **Main moved:** `git fetch` and compare with `origin/main` before starting and before pushing.

## Verification Commands (run after every backend edit, once `backend/` exists)
- `uv run pytest backend/tests/defense/`
- `uv run ruff check backend/`
- `MOCK=1 uv run pytest`
