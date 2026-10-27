# Project Defense + Runner — area rules (owner: Shreyas)

Loaded when you work in `backend/crucible/defense/` or `backend/crucible/runner/`. Adds to the root
`CLAUDE.md`; never loosens it.

Read before writing code here: `@../../../docs/defense/DEFENSE_AGENT_SPEC.txt` (Defense briefing and the §9
decision log; don't reopen settled decisions) and `plan/shreyas-defense-and-runner.md` (build order,
handoff dates, interfaces). PLAN sections: §7.4 defense contracts, §11 Defense, §12 Runner, §19 deploy.

## Working memory
`@../../../docs/defense/MEMORY.md` is the shared working memory for Claude Code and Muse Code on this area:
claim files under "Active work" before editing, never edit files someone else has claimed, and update
status, handoff and the session log before you finish.

## Scope for agents working on Defense + Runner
Create or edit only Shreyas's paths: `backend/crucible/defense/`, `backend/crucible/runner/`,
`backend/crucible/models/glimmer.py`, `backend/crucible/mock/`, `frontend/src/lib/defense.ts`, the scaffold
(Makefile, CI, `.env.example`, `backend/pyproject.toml`, Dockerfile, `main.py`, `config.py`, `store/`),
`docs/defense/` and tests. `contracts/` needs SG + SS approval. `engine/`, the rest of `models/`,
`data/defense_apps/` and other `frontend/` files belong to teammates: note needed changes instead.

## Defense-specific laws
- `Finding.explanation`, grill specs and fix rubrics stay server-side until that finding's grill is graded:
  `defense.audit` carries `AuditPublic`; the full `Finding` arrives with `defense.grill.eval`.
- The model writes only the three attack bodies; the template and the AST validator own everything else.
- Grill scores, chaos verdicts and the merge gate are pure Python functions with unit tests.
- Spec conflicts: ask Shreyas, then fix PLAN.md and the spec in the same PR.

## Checks
`uv run pytest backend/tests/defense backend/tests/runner` and `uv run ruff check backend/`.
