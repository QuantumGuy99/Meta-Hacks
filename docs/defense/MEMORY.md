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

## Status (2026-11-04)
| WP | What | State | Notes |
|---|---|---|---|
| S-0, store | Scaffold, Makefile, CI, SQLite store | merged (#10) | main.py import guard can go once nothing needs it |
| RUN-1 | Harness + LocalRunner.run_tests | merged (#15) | Checked on a real problem; re-run on Sharvil's gold problems |
| RUN-3 | ModalRunner for projects | merged (#15, #67) | Real Modal: race reproduces, egress blocked (V7). Deadlines on every Modal call (#73); images with each sample's requirements built at startup (#67) |
| RUN-2 | Warm Modal sandbox for coding tests | merged (#67, #76) | Warmed at session start |
| DEF-1..6 | Defense pipeline + DefenseController | merged (#15), review fixes open | 7 WebSocket e2e tests; resume works. Blockers 1-4 of #22 fixed in #29; items 5, 7, 9, 10 open |
| OPS-2 | MOCK replay + recorder | merged (#15); re-recorded | `defense-bank-transfer.jsonl` now from the real `bank-transfer`; `rest/report-defense.json` serves the report page |
| OPS-1 | Deploy | prep merged (#14) | No deployed URL is recorded in the repo: add it to README and docs/DEPLOY.md |
| DEF-11 | Muse fix assistant (full coding assistant, logged) | built | `defense/assistant.py`, `FixAssistant.tsx`; the report's AI-share line (§11.9) isn't built yet: the timeline has every turn |
| DEF-1 upload | Zip upload + notes for the audit | built | `defense/uploads.py`; the audit and attacks need a model key (no flaws.json for uploads) |
| — | Attacker prompt knows the new validator rules | #18 | Waiting on SG |
| lib/defense.ts | Selectors for Likhil's views | built, with Node tests | Shape as in the role plan |
| DEF-2 recall | `python -m crucible.defense.recall` over `data/evals/defense/` | built, not run live | Needs MODEL_API_KEY; the flaws.json fallback never counts |

## Handoff (overwrite every session)
- **Last done:** 2026-11-04 [agent] Upload your own project (zip, private, with optional notes for the audit),
  the DEF-11 fix assistant (ask, reply, apply, all on the timeline), no answer box in the grill, profanity
  warnings that end the session on the third strike.
- **Next step:** run `python -m crucible.defense.recall` with a key (DEF-2 done-when).
- **Blocked on:** a MODEL_API_KEY for the recall eval.

## Open questions for teammates
- ST: a fan-in attack (every transfer pays one account) drains $1,000 senders in ~1 s and the 409s count as errors. Use larger balances or amounts that can't run out (fixture uses $100,000 per account).
- ST: confirm `QuantumGuy99` is your account (#11). LG: open a PR for `feat/fe-visual-stack` (#12).

## Verified facts and gotchas
- 2026-10-28 [agent] Windows Python reads and writes text as cp1252 unless told otherwise: always pass encoding="utf-8" (a test checks).
- Windows: with LOCAL_RUNNER_ISOLATE, `proc.terminate()` ends only `uv run`; the app it started survives and keeps the port and the log file. Stop the tree (`taskkill /T`), and never let cleanup raise out of a stage.
<!-- e.g. "2026-10-28 [agent] Modal Sandbox.open() writes files into a running sandbox (V7)" -->
- 2026-10-28 [agent] On Windows the harness timer is a thread raising SIGINT: it lands up to ~25 ms late, and like SIGALRM it can't stop a blocked lock or other C code (the runner's process kill does).
- 2026-10-27 [agent] Modal `block_network=True` blocks egress and keeps loopback (V7 done).
- 2026-10-27 [agent] Modal stdout arrives in chunks, not lines; ModalRunner.stream_exec splits them (V7).
- 2026-10-27 [agent] Main moves under you: PR #2 landed while PR #4 was open. `git fetch` and check
  `git log HEAD..origin/main` before starting work and before pushing.
- 2026-10-27 [agent] MOCK fixture line format is `{"dt_ms": ..., "msg": <ServerMessage>}`; in MOCK mode
  the session id is the scenario name (PLAN §14.6).

## Session log (keep the last 10, newest first)
- 2026-11-04 [agent, for SG] Abusive language ends both modes (engine/conduct.py via the hub). The grill answers questions back (`grill.clarify`), follow-ups react to what was said, and no line repeats an earlier one. Fix-stage check-ins back off (2, 4 min) and stop at 3. LocalRunner: spawns can't be cancelled halfway (`_spawn`), and apps or harnesses cancelled mid-start are stopped. This was the occasional test-suite hang and the pile of orphaned `app.main` servers. Needs Shreyas's review.
- 2026-11-04 [agent, for SG] From SG's practice run (#88 bugs 1, 5, item 6): one answer per grill question (a message while grading, or speech begun before the question, is ignored; spoken parts are joined after a 2.5 s pause), the grader's reaction goes out with the next line instead of on its own, questions are reworded in plain words by `grill.plain_question` (`interviewer` role, audit wording as the fallback), and the Defense clock holds through audit and chaos (`HELD_CLOCK` in engine/hub.py). Needs Shreyas's review.
- 2026-10-31 [agent] #78: the audit asks again when a finding names a file that doesn't exist (a live run got the race back as file "hello world" and attacked nothing). #71 moved the agent rules to AGENTS.md.
- 2026-10-29 [agent] Data/Defense weak spots fixed and Thursday leftovers built (see Handoff); 600+ tests pass.
- 2026-10-28 [agent] for LG: every text read/write names encoding="utf-8" (Windows defaulted to cp1252: "→" in a problem was served as "â†’"), with `tests/test_text_encoding.py` as a guard. The full backend suite passes on Windows.
- 2026-10-28 [agent] for LG: the harness's per-test timer works on Windows (a timer thread raises SIGINT; the SIGALRM path is unchanged). `test_harness.py` and `test_problem_run.py` pass on Windows.
- 2026-10-28 [agent, for Likhil] `fix/windows-runner-cleanup`: LocalRunner stops the whole process tree on Windows and removes the app log best-effort; `run_attack` keeps a finished run when cleanup fails (a locked log crashed the stage and left sessions stuck in chaos). The 5 pipeline e2e tests now pass on Windows. Needs Shreyas's review.
- 2026-10-27 [agent] Merged #13–#15; opened #17, #18; docs refreshed (README status, role plan, spec).
- 2026-10-29 [agent] RUN-2 + RUN-3 gaps: warm Modal sandbox per coding session, requirements.txt baked into per-project images (network is blocked at run time), images prebuilt at startup, asyncio timeouts on every Modal call. All 3 sample apps break and hold on real Modal.
- 2026-10-28 [agent] #35 + #43 Defense fixes (reference attack matched by file/lines, keyword root-cause floor, p95 0 = no check, race load floor 50, empty-audit retry, harness configures models, stages cancelled on end). Live run on bank-transfer-min: attacker timed out twice (pre-#43 registry) → reference attack matched → broke $11,249 → grill 10/10 → held → PASS.
