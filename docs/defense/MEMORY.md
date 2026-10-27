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
  DEFENSE_AGENT_SPEC.txt §9, and code explains itself. Link to those instead.
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
| PR #4 | Spec reconciled with PLAN.md | open, **merge conflicts** with main (PR #2) | https://github.com/QuantumGuy99/Meta-Hacks/pull/4 |

## Handoff (overwrite every session)
- **Last done:** 2026-10-27 [claude] Reconciled DEFENSE_AGENT_SPEC.txt with PLAN.md (PR #4); added
  agent docs (this file, backend/CLAUDE.md, .claude/skills/crucible-code/SKILL.md).
- **Next step:** fix PR #4 (merge main; rename `defense/session.py` → `defense/controller.py` to match
  the role plan's `DefenseController`; update `plan/shreyas-defense-and-runner.md` per PLAN §22 rule 15:
  grill scoring, AuditPublic, SAM DEF-9, card DEF-10, port 8080). Then S-0 → store → S-1 → RUN-1.
- **Blocked on:** SG + LG approval of the contract changes in PR #4 before S-1 is final.

## Open questions for teammates
- SG: OK for SS to write `models/sam.py` and `models/image.py` (DEF-9, DEF-10)?
- LG / SG: GitHub usernames, so PRs can request reviews.
- README model table still calls SAM 3.1 "Stretch"; should say P1.

## Verified facts and gotchas
<!-- e.g. "2026-10-28 [claude] Modal Sandbox.open() writes files into a running sandbox (V7)" -->
- 2026-10-27 [claude] Main moves under you: PR #2 landed while PR #4 was open. `git fetch` and check
  `git log HEAD..origin/main` before starting work and before pushing.
- 2026-10-27 [claude] MOCK fixture line format is `{"dt_ms": ..., "msg": <ServerMessage>}`; in MOCK mode
  the session id is the scenario name (PLAN §14.6).

## Session log (keep the last 10, newest first)
- 2026-10-27 [claude] Cloned repo; wrote CLAUDE.md + DEFENSE_AGENT_SPEC.txt; reconciled 24 conflicts
  with PLAN.md; opened PR #4; added agent memory, coding rules and code-format skill.
