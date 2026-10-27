# Crucible — Agent Operating Rules (Shreyas: Project Defense & Runner)

Read `@DEFENSE_AGENT_SPEC.txt` and `@README.md` before writing code. `PLAN.md` is the team's build plan
(1,700+ lines): read the section you need (§6 layout, §7.4 defense contracts, §11 Defense, §12 Runner,
§19 deploy, §22 agent rules) instead of loading all of it.

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

## Verification Commands (run after every backend edit, once `backend/` exists)
- `uv run pytest backend/tests/defense/`
- `uv run ruff check backend/`
- `MOCK=1 uv run pytest`
