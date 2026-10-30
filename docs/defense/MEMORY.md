# Defense working memory (shared by the coding agents)

The one place where context survives between sessions and between agents. Read it at the start of every
session. Update it before you finish any session that changed code, decisions or status.

**Rules**
- Facts, not narratives. One line per item. Absolute dates (2026-10-27), never "today" or "yesterday".
- Sign entries with the agent: `[agent]`, `[muse]` or `[shreyas]`.
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

## Status (2026-10-29)
| WP | What | State | Notes |
|---|---|---|---|
| S-0, store | Scaffold, Makefile, CI, SQLite store | merged (#10) | main.py import guard can go once nothing needs it |
| RUN-1 | Harness + LocalRunner.run_tests | merged (#15) | Checked on a real problem; re-run on Sharvil's gold problems |
| RUN-3 | ModalRunner for projects | merged (#15), gaps open | Real Modal: race reproduces, egress blocked (V7). Every Modal call now has a deadline (#73). Still open (#22 item 8): image built lazily, sample requirements.txt not installed |
| RUN-2 | Warm Modal sandbox for coding tests | Thu | ModalRunner.run_tests raises a clear RUN-2 error until then |
| DEF-1..6 | Defense pipeline + DefenseController | merged (#15), review fixes open | 7 WebSocket e2e tests; resume works. Blockers 1-4 of #22 fixed in #29; items 5, 7, 9, 10 open |
| OPS-2 | MOCK replay + recorder | merged (#15); re-recorded | `defense-bank-transfer.jsonl` now from the real `bank-transfer`; `rest/report-defense.json` serves the report page |
| OPS-1 | Deploy | prep merged (#14); deploy Sat | Railway signup was down; Render/Fly take the same Dockerfile; free credit only |
| DEF-11 | Muse fix assistant (full coding assistant, logged) | spec in #17 | Build after IC2 |
| — | Attacker prompt knows the new validator rules | #18 | Waiting on SG |
| lib/defense.ts | Selectors for Likhil's views | built, with Node tests | Shape as in the role plan |
| DEF-2 recall | `python -m crucible.defense.recall` over `data/evals/defense/` | built, not run live | Needs MODEL_API_KEY; the flaws.json fallback never counts |

## Handoff (overwrite every session)
- **Last done:** 2026-10-29 [agent] In #73: one reference attack per flaw
  (ticket-drop f2 no longer needs the model), Sharvil's DATA-2 tools (`make validate`), validator corpus,
  recall eval, MOCK re-recorded from the real app + `report-defense`, `lib/defense.ts`, Modal deadlines,
  the Verify busy-check race, two loopback-hook bypasses closed (`type(client)()`, `event_hooks`), and the
  grill/audit/attacker prompts now treat candidate and project text as data.
- **Next step:** run `python -m crucible.defense.recall` with a key (DEF-2 done-when); RUN-2.
- **Blocked on:** a MODEL_API_KEY for the recall eval; Likhil's Defense views (FE-6) to show any of it.

## Open questions for teammates
- SG: `models/registry.py` still lists a Glimmer provider (harmless); drop it when convenient (#13).
- ST: a fan-in attack (every transfer pays one account) drains $1,000 senders in ~1 s and the 409s count as errors. Use larger balances or amounts that can't run out (fixture uses $100,000 per account).
- ST: confirm `QuantumGuy99` is your account (#11). LG: open a PR for `feat/fe-visual-stack` (#12).

## Verified facts and gotchas
<!-- e.g. "2026-10-28 [agent] Modal Sandbox.open() writes files into a running sandbox (V7)" -->
- 2026-10-27 [agent] Modal `block_network=True` blocks egress and keeps loopback (V7 done).
- 2026-10-27 [agent] Modal stdout arrives in chunks, not lines; ModalRunner.stream_exec splits them (V7).
- 2026-10-27 [agent] Main moves under you: PR #2 landed while PR #4 was open. `git fetch` and check
  `git log HEAD..origin/main` before starting work and before pushing.
- 2026-10-27 [agent] MOCK fixture line format is `{"dt_ms": ..., "msg": <ServerMessage>}`; in MOCK mode
  the session id is the scenario name (PLAN §14.6).

## Session log (keep the last 10, newest first)
- 2026-10-29 [agent] Data/Defense weak spots fixed and Thursday leftovers built (see Handoff); 600+ tests pass.
- 2026-10-27 [agent] Merged #13–#15; opened #17, #18; docs refreshed (README status, role plan, spec).
- 2026-10-28 [agent] #35 + #43 Defense fixes (reference attack matched by file/lines, keyword root-cause floor, p95 0 = no check, race load floor 50, empty-audit retry, harness configures models, stages cancelled on end). Live run on bank-transfer-min: attacker timed out twice (pre-#43 registry) → reference attack matched → broke $11,249 → grill 10/10 → held → PASS.
- 2026-10-27 [agent] SG approved #13–#15. Attack containment in 3 layers (validator bans, loopback hook, Modal block_network); V7 done; samples load once.
- 2026-10-27 [agent] Day 0 + Day 1 checklist complete; RUN-1 "done when" checked on a real problem.
- 2026-10-27 [agent] DEF-6, RUN-1, OPS-2 built; Modal verified; deploy config PR #14; Glimmer dropped PR #13; folders consolidated.
- 2026-10-27 [agent] S-0 PR #10 (CI green); Defense built on SG's stack in `feat/defense`, 194 tests pass; reviews posted on #5–#7.
- 2026-10-27 [agent] Merged main into PR #4, resolved conflicts, controller.py rename, role plan + README synced.
- 2026-10-27 [agent] Cloned repo; wrote the agent rules + DEFENSE_AGENT_SPEC.txt; reconciled 24 conflicts
  with PLAN.md; opened PR #4; added agent memory, coding rules and code-format skill.
