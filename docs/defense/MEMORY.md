# Defense working memory (shared by Claude Code and Muse Code)

The one place where context survives between sessions and between agents. Read it at the start of every
session. Update it before you finish any session that changed code, decisions or status.

**Rules**
- Facts, not narratives. One line per item. Absolute dates (2026-10-27), never "today" or "yesterday".
- Sign entries with the agent: `[claude]`, `[muse]` or `[shreyas]`.
- Keep this file under ~150 lines. When a section grows, delete what is done or no longer true. Git
  history keeps the old versions.
- Don't copy what lives elsewhere: architecture is in PLAN.md, your build order, handoff dates and
  interfaces are in `plan/shreyas-defense-and-runner.md`, decisions already made are in
  docs/defense/DEFENSE_AGENT_SPEC.txt §9, and code explains itself. Link to those instead.
- A verified API fact also goes into PLAN.md §23 (set the row to `done` + what you found).
- Before editing files, claim them under **Active work**. Remove your claim when you finish. Never edit
  files another agent has claimed.

## Active work (claims)
| Agent | Files / area | Since |
|---|---|---|
| — | — | — |

## Status
| WP | What | State | Notes |
|---|---|---|---|
| S-0 | Scaffold: backend/, Makefile, CI, .env.example | not started | Due 2026-10-27 morning; blocks everyone. Frontend is already on main |
| store | `store/repo.py` for SG | not started | Due 2026-10-27; interface in the role plan |
| S-1 | Contracts v1 + export.py (with SG) | not started | Due 2026-10-27; use PLAN §7 as updated by PR #4 |
| RUN-1 | Runner protocol, harness, LocalRunner | not started | Due 2026-10-27 (SG, ST need it) |
| OPS-2 | Mock replay engine + fixtures | not started | Skeleton 2026-10-27, working 2026-10-29 |
| DEF-1..10, RUN-2/3, OPS-1 | see PLAN §16 + role plan | not started | |
| PR #4 | Spec reconciled with PLAN.md + role plan + agent docs | open; SG built #5 on it; awaiting LG review | https://github.com/QuantumGuy99/Meta-Hacks/pull/4 |

## Handoff (overwrite every session)
- **Last done:** 2026-10-27 [claude] Standalone Defense backend built on local branch
  `feat/defense-standalone` (uncommitted; Shreyas's machine): runner (local + Modal), chaos template,
  validator, audit/attack/grill/verdict with fallbacks, pipeline, REST + dev API, CLI, 44 tests. Unit tests
  pass; e2e break → fix → hold passed before a template change. Moved Shreyas-only agent rules out of
  root CLAUDE.md into backend/crucible/defense/CLAUDE.md (PR #4).
- **Next step:** (1) chaos template: shard the attack across several httpx clients (≈ 10 connections
  each) and stagger worker start. Benchmark: one pool collapses (199 rps at 50 concurrent, ReadErrors at
  200), sharded pools give ~2,400 rps at 200 with 0 errors. Rerun e2e. (2) Drop local contracts in favour of
  PR #5; adapt defense to PR #6's `llm.complete_json` / `AllModelsFailed`. (3) S-0 PR (Makefile, CI with the
  Node test command SG asked for, .env.example), then the defense PR.
- **Blocked on:** SG + LG approval of the contract changes in PR #4 before S-1 is final.

## Open questions for teammates
- SG: PR #5 defense contracts match ours field for field; OK to keep `FindingPublic.of` / `AuditPublic.of` helpers in defense code, not contracts.
- SG: OK for SS to write `models/sam.py` and `models/image.py` (DEF-9, DEF-10)?
- LG / SG: GitHub usernames, so PRs can request reviews.

## Verified facts and gotchas
<!-- e.g. "2026-10-28 [claude] Modal Sandbox.open() writes files into a running sandbox (V7)" -->
- 2026-10-27 [claude] Main moves under you: PR #2 landed while PR #4 was open. `git fetch` and check
  `git log HEAD..origin/main` before starting work and before pushing.
- 2026-10-27 [claude] MOCK fixture line format is `{"dt_ms": ..., "msg": <ServerMessage>}`; in MOCK mode
  the session id is the scenario name (PLAN §14.6).

## Session log (keep the last 10, newest first)
- 2026-10-27 [claude] Merged main into PR #4, resolved conflicts, controller.py rename, role plan + README synced.
- 2026-10-27 [claude] Cloned repo; wrote CLAUDE.md + DEFENSE_AGENT_SPEC.txt; reconciled 24 conflicts
  with PLAN.md; opened PR #4; added agent memory, coding rules and code-format skill.
