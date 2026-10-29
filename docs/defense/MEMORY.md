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

## Status (end of 2026-10-27)
| WP | What | State | Notes |
|---|---|---|---|
| S-0, store | Scaffold, Makefile, CI, SQLite store | merged (#10) | main.py import guard can go once nothing needs it |
| RUN-1 | Harness + LocalRunner.run_tests | merged (#15) | Checked on a real problem; re-run on Sharvil's gold problems |
| RUN-3 | ModalRunner for projects | merged (#15), gaps open | Real Modal: race reproduces, egress blocked (V7). Open (#22 item 8): image built lazily, sample requirements.txt not installed, no asyncio timeouts on Modal calls |
| RUN-2 | Warm Modal sandbox for coding tests | Thu | ModalRunner.run_tests raises a clear RUN-2 error until then |
| DEF-1..6 | Defense pipeline + DefenseController | merged (#15), review fixes open | 7 WebSocket e2e tests; resume works. Blockers 1-4 of #22 fixed in #29; items 5, 7, 9, 10 open |
| OPS-2 | MOCK replay + recorder | merged (#15) | `defense-bank-transfer.jsonl` |
| OPS-1 | Deploy | prep merged (#14); deploy Sat | Railway signup was down; Render/Fly take the same Dockerfile; free credit only |
| DEF-11 | Muse fix assistant (full coding assistant, logged) | spec in #17 | Build after IC2 |
| — | Attacker prompt knows the new validator rules | #18 | Waiting on SG |
| lib/defense.ts | Selectors for Likhil's views | Thu | Shape in the role plan |

## Handoff (overwrite every session)
- **Last done:** 2026-10-27 [claude] Merged #13 (Glimmer dropped), #14 (deploy), #15 (Defense end to end) into
  main; main green (backend, contracts, docker, frontend). Opened #17 (assistant spec) and #18 (prompt rules).
  Replied to every review; issues #11 (Sharvil) and #12 (Likhil) updated.
- **Next step:** Wed morning: if `data/defense_apps/bank-transfer` isn't up, build it from
  `backend/tests/fixtures/apps/bank-transfer-min` (Sharvil owns data/; say so in #11). Then IC1 with Likhil.
- **Blocked on:** Sharvil (#11), Likhil's PR (#12), reviews of #16/#17/#18.

## Open questions for teammates
- SG: `models/registry.py` still lists a Glimmer provider (harmless); drop it when convenient (#13).
- ST: a fan-in attack (every transfer pays one account) drains $1,000 senders in ~1 s and the 409s count as errors. Use larger balances or amounts that can't run out (fixture uses $100,000 per account).
- ST: confirm `QuantumGuy99` is your account (#11). LG: open a PR for `feat/fe-visual-stack` (#12).

## Verified facts and gotchas
- 2026-10-28 [claude] Windows Python reads and writes text as cp1252 unless told otherwise: always pass encoding="utf-8" (a test checks).
- Windows: with LOCAL_RUNNER_ISOLATE, `proc.terminate()` ends only `uv run`; the app it started survives and keeps the port and the log file. Stop the tree (`taskkill /T`), and never let cleanup raise out of a stage.
<!-- e.g. "2026-10-28 [claude] Modal Sandbox.open() writes files into a running sandbox (V7)" -->
- 2026-10-28 [claude] On Windows the harness timer is a thread raising SIGINT: it lands up to ~25 ms late, and like SIGALRM it can't stop a blocked lock or other C code (the runner's process kill does).
- 2026-10-27 [claude] Modal `block_network=True` blocks egress and keeps loopback (V7 done).
- 2026-10-27 [claude] Modal stdout arrives in chunks, not lines; ModalRunner.stream_exec splits them (V7).
- 2026-10-27 [claude] Main moves under you: PR #2 landed while PR #4 was open. `git fetch` and check
  `git log HEAD..origin/main` before starting work and before pushing.
- 2026-10-27 [claude] MOCK fixture line format is `{"dt_ms": ..., "msg": <ServerMessage>}`; in MOCK mode
  the session id is the scenario name (PLAN §14.6).

## Session log (keep the last 10, newest first)
- 2026-10-28 [claude] for LG: every text read/write names encoding="utf-8" (Windows defaulted to cp1252: "→" in a problem was served as "â†’"), with `tests/test_text_encoding.py` as a guard. The full backend suite passes on Windows.
- 2026-10-28 [claude] for LG: the harness's per-test timer works on Windows (a timer thread raises SIGINT; the SIGALRM path is unchanged). `test_harness.py` and `test_problem_run.py` pass on Windows.
- 2026-10-28 [claude, for Likhil] `fix/windows-runner-cleanup`: LocalRunner stops the whole process tree on Windows and removes the app log best-effort; `run_attack` keeps a finished run when cleanup fails (a locked log crashed the stage and left sessions stuck in chaos). The 5 pipeline e2e tests now pass on Windows. Needs Shreyas's review.
- 2026-10-27 [claude] Merged #13–#15; opened #17, #18; docs refreshed (README status, role plan, spec).
- 2026-10-27 [claude] SG approved #13–#15. Attack containment in 3 layers (validator bans, loopback hook, Modal block_network); V7 done; samples load once.
- 2026-10-27 [claude] Day 0 + Day 1 checklist complete; RUN-1 "done when" checked on a real problem.
- 2026-10-27 [claude] DEF-6, RUN-1, OPS-2 built; Modal verified; deploy config PR #14; Glimmer dropped PR #13; folders consolidated.
- 2026-10-27 [claude] S-0 PR #10 (CI green); Defense built on SG's stack in `feat/defense`, 194 tests pass; reviews posted on #5–#7.
- 2026-10-27 [claude] Merged main into PR #4, resolved conflicts, controller.py rename, role plan + README synced.
- 2026-10-27 [claude] Cloned repo; wrote CLAUDE.md + DEFENSE_AGENT_SPEC.txt; reconciled 24 conflicts
  with PLAN.md; opened PR #4; added agent memory, coding rules and code-format skill.
