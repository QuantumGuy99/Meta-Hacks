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
| S-0 | Scaffold, Makefile, CI, store | merged (#10) | Delete main.py's import guard once nothing on main needs it |
| RUN-1 | Runner protocol, harness (`run_tests.py`), LocalRunner | done (PR #15) | 21 harness tests + a real problem (contracts fixture: reference 3/3, starter fails). Re-run on Sharvil's 3 gold problems when they land |
| RUN-3 (projects) | ModalRunner start/put/stream/stop | verified on real Modal 2026-10-27 | Two bugs fixed: stray port arg; stdout chunks → lines |
| RUN-2 | Warm Modal sandbox for coding tests | not started (Thu) | ModalRunner.run_tests raises a clear "RUN-2" error until then |
| DEF-1..5 | projects, audit, attack, chaos, grill, verdict | done on `feat/defense` | |
| DEF-6 | DefenseController on the hub | done on `feat/defense`, WebSocket e2e tests | Resume rebuilds state from the timeline |
| OPS-2 | MOCK replay + recorder | done on `feat/defense` | `defense-bank-transfer.jsonl` recorded from a real run |
| OPS-1 | Deploy | config in PR #14 | Railway signup was down 2026-10-27; deploy ~Sat; free credit only |
| Glimmer | dropped | PR #13 | Attacker = Spark |

## Handoff (overwrite every session)
- **Last done:** 2026-10-27 [claude] Consolidated everything into the single `MetaDevHack` folder (no more
  worktrees; old copy in `git stash`). On `feat/defense`: DefenseController, RUN-1 harness, MOCK replay +
  recorder, Modal runner verified live. Meta key works (2 calls ≈ $0.0005). Modal token: shreyas-sahoo-15.
- **Next step:** open the Defense PR from `feat/defense`. Then Wed: IC1 (bank-transfer audit renders: needs
  Sharvil's app, #11), lib/defense.ts selectors for Likhil, RUN-2 Thu.
- **Blocked on:** Sharvil's `data/defense_apps/bank-transfer` (due Wed noon; write it Wed morning if missing).

## Open questions for teammates
- SG: `models/registry.py` still lists a Glimmer provider (harmless); drop it when convenient (#13).
- ST: a fan-in attack (every transfer pays one account) drains $1,000 senders in ~1 s and the 409s count as errors. Use larger balances or amounts that can't run out (fixture uses $100,000 per account).
- ST: confirm `QuantumGuy99` is your account (#11). LG: open a PR for `feat/fe-visual-stack` (#12).

## Verified facts and gotchas
<!-- e.g. "2026-10-28 [claude] Modal Sandbox.open() writes files into a running sandbox (V7)" -->
- 2026-10-27 [claude] Modal `block_network=True` blocks egress and keeps loopback (V7 done).
- 2026-10-27 [claude] Modal stdout arrives in chunks, not lines; ModalRunner.stream_exec splits them (V7).
- 2026-10-27 [claude] Main moves under you: PR #2 landed while PR #4 was open. `git fetch` and check
  `git log HEAD..origin/main` before starting work and before pushing.
- 2026-10-27 [claude] MOCK fixture line format is `{"dt_ms": ..., "msg": <ServerMessage>}`; in MOCK mode
  the session id is the scenario name (PLAN §14.6).

## Session log (keep the last 10, newest first)
- 2026-10-27 [claude] SG approved #13–#15. Attack containment in 3 layers (validator bans, loopback hook, Modal block_network); V7 done; samples load once.
- 2026-10-27 [claude] Day 0 + Day 1 checklist complete; RUN-1 "done when" checked on a real problem.
- 2026-10-27 [claude] DEF-6, RUN-1, OPS-2 built; Modal verified; deploy config PR #14; Glimmer dropped PR #13; folders consolidated.
- 2026-10-27 [claude] S-0 PR #10 (CI green); Defense built on SG's stack in `feat/defense`, 194 tests pass; reviews posted on #5–#7.
- 2026-10-27 [claude] Merged main into PR #4, resolved conflicts, controller.py rename, role plan + README synced.
- 2026-10-27 [claude] Cloned repo; wrote CLAUDE.md + DEFENSE_AGENT_SPEC.txt; reconciled 24 conflicts
  with PLAN.md; opened PR #4; added agent memory, coding rules and code-format skill.
