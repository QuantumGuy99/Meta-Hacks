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
| S-0 | Scaffold, Makefile, CI, store | PR #10 open, CI green | Handles #8's and #9's hub shapes; delete the import guard in main.py once #5/#6/#8 merge |
| S-1 | Contracts v1 | SG's PR #5, approved | Defense uses them as is |
| RUN-1 (projects) | Runner protocol, LocalRunner, Modal runner | built on `feat/defense` | ModalRunner untested (no Modal token yet, V7). run_tests (coding) not built yet |
| DEF-1..5 core | projects, audit, attack writer + validator, chaos, grill, verdict | built on `feat/defense`, 44 tests | Pipeline only; DefenseController (hub) not built yet |
| DEF-6 | DefenseController on the hub | next | Needs #9's ModeFactory: `defense.controller.make_mode()` (main.py already looks for it) |
| OPS-2 | MOCK replay | not started | |
| PR #4 | Spec, role plans, agent docs | SG requested changes, all addressed, awaiting re-review | |

## Handoff (overwrite every session)
- **Last done:** 2026-10-27 [claude] Pushed `feat/defense` (5689a3d): Defense ported onto #5 contracts, #6
  wrapper (WrapperModelClient), #8 public_audit; branch = S-0 + #5–#9 merged + Defense. Chaos template now
  spreads the attack over pools of 10 with a 0.4 s ramp (110 → ~1,500 req/s, 0 errors) and ends with a final
  metric line. CLI demo: broken "$8,827 disappeared", fixed holds, MERGE GATE PASS in ~12 s, no keys.
- **Next step:** DEF-6 `defense/controller.py` (`make_mode()` returning a ModeFactory; plan_session picks the
  sample; on_start runs audit + baselines; chat answers during grill → answer_grill; defense.verify →
  verify; report_extra). Then OPS-2 MOCK fixtures for Likhil. Open the Defense PR once #5–#10 are on main
  (rebase `feat/defense` onto main first).
- **Blocked on:** SG + LG approval of the contract changes in PR #4 before S-1 is final.

## Open questions for teammates
- ST: a fan-in attack (every transfer pays one account) drains $1,000 senders in ~1 s and the 409s count as errors. Use larger balances or amounts that can't run out (fixture uses $100,000 per account).
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
- 2026-10-27 [claude] S-0 PR #10 (CI green); Defense built on SG's stack in `feat/defense`, 194 tests pass; reviews posted on #5–#7.
- 2026-10-27 [claude] Merged main into PR #4, resolved conflicts, controller.py rename, role plan + README synced.
- 2026-10-27 [claude] Cloned repo; wrote CLAUDE.md + DEFENSE_AGENT_SPEC.txt; reconciled 24 conflicts
  with PLAN.md; opened PR #4; added agent memory, coding rules and code-format skill.
