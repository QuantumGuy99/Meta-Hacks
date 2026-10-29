# Product evals

Scripted, end-to-end checks of the whole product through the real backend (REST and the session WebSocket) and the frontend's pages, with no model key. Each check records **pass**, **fail** or **blocked** (it couldn't run here, which is not a product failure), how long the backend took, and a one-line detail.

Model-graded behaviour (does the analyzer catch the bug, does a nudge fire) needs `MODEL_API_KEY` and is covered by the coding eval runner in `backend/tests/evals/`.

## Latest run: Oct 29, 2026

Build: `main` at `d68ee37` plus every open PR (#49, #51, #52, #57, #58, #61, #67, #68, #69) and `fix/harness-windows-timer` (the Windows fixes), on Windows 11 with no model key. Left out: #55 and #56 (spoken replies; voice stays speech to text) and the docs-only #70–#72.

**87 of the 87 checks that could run passed, 0 failed, and 9 are blocked.** Every blocked check needs a Meta model key.

| Passed | Failed | Blocked | Checks |
|---:|---:|---:|---:|
| 87 | 0 | 9 | 96 |

### Results by area

| Area | Session or page set | Passed | Failed | Blocked |
|---|---|---:|---:|---:|
| Setup | backend | 1 | 0 | 0 |
| Coding | thermostat-swings | 22 | 0 | 3 |
| Coding | ingredient-groups | 22 | 0 | 3 |
| Coding | genre-sampler | 22 | 0 | 3 |
| Defense | live on this machine | 5 | 0 | 0 |
| Defense | recorded run (MOCK) | 7 | 0 | 0 |
| Frontend | pages | 8 | 0 | 0 |

### What's blocked

| Cause | Checks | What it covers | Fix |
|---|---:|---|---|
| Needs a Meta model key | 9 | Interviewer answers, hints and the written review, in each coding interview | `MODEL_API_KEY` in `.env` |

### Test suites

| Suite | Passed | Failed | Notes |
|---|---:|---:|---|
| Backend: main + every open PR + the Windows fixes (`pytest tests`, every test) | 768 | 3 | 2 are the new encoding guard catching a bare `read_text()` in open PRs (#51 `guide/prompts/__init__.py:11`, #67 `tests/runner/test_modal_runner.py:52`); 1 is the voice timing test, which passes on reruns of its file. 3 Modal tests skipped. |
| Frontend capture, replay and Defense selectors (`node --test`) | 34 | 0 | On `feat/fe-visual-stack`, #52 and #69 included. |
| Frontend types, lint and build | 3 | 0 | `tsc --noEmit`, `eslint`, `next build` on `feat/fe-visual-stack` (Frontend v16). |
| Test-harness timer at the deadline (stress) | 8 | 0 | 8 harness runs of 168 cases timed to end around a 50 ms limit on Windows: no crash or stray interrupt. |

### Every check

| Area | Session | Check | Result | What happened | Backend ms |
|---|---|---|---|---|---:|
| Setup | backend | Backend health | pass | {"ok": true, "version": "0.1.0", "mock": false} |  |
| Coding | thermostat-swings | Create session | pass | 201, session 7d1871e0bba8 | 11 |
| Coding | thermostat-swings | Problem API hides the answer | pass | no hidden tests, rubric or reference in GET /api/problems/{slug} |  |
| Coding | thermostat-swings | Socket hello → session.state | pass | phase intro | 155 |
| Coding | thermostat-swings | Warm-up greeting before the problem | pass | Hi, I'm Ares, and I'll be your interviewer today. Before we get to the… | 0 |
| Coding | thermostat-swings | Clock holds during the warm-up | pass | 1200 s left, still 1200 s 3 s later, phase intro |  |
| Coding | thermostat-swings | Skip Intro → clarify | pass | clarify with 1200 s left | 56 |
| Coding | thermostat-swings | Clock runs once the problem is presented | pass | 1200 s, then 1197 s 3 s later |  |
| Coding | thermostat-swings | Chat → transcript turn | pass | candidate turn recorded | 65 |
| Coding | thermostat-swings | Interviewer answers a question | blocked | no answer: needs MODEL_API_KEY |  |
| Coding | thermostat-swings | Start coding (clarify → coding) | pass | phase coding | 55 |
| Coding | thermostat-swings | Refuses going back (coding → clarify) | pass | error bad_phase | 58 |
| Coding | thermostat-swings | Hint button | blocked | server: hints aren't available right now (the live engine needs MODEL_API_KEY) | 65 |
| Coding | thermostat-swings | Typing raises no integrity note | pass | 0 notes while typing line by line |  |
| Coding | thermostat-swings | A paste becomes a neutral note | pass | pasted 14 lines at 00:17 | 65 |
| Coding | thermostat-swings | An infinite loop times out | pass | timed_out=True, timed out after 2 s | 6336 |
| Coding | thermostat-swings | Run the reference solution | pass | 3 of 3 tests passed | 291 |
| Coding | thermostat-swings | Submit the reference solution | pass | 14 of 14 tests passed | 261 |
| Coding | thermostat-swings | Live timeline hides analyses and notes | pass | 31 events, kinds ['editor', 'integrity', 'intervention', 'phase', 'run', 'snapshot', 'transcript'] |  |
| Coding | thermostat-swings | Edits reach the timeline | pass | 9 edit events, last snapshot matches the typed code |  |
| Coding | thermostat-swings | No report while live | pass | HTTP 409 |  |
| Coding | thermostat-swings | Reconnect keeps the session | pass | back in wrap_up (was wrap_up) | 52 |
| Coding | thermostat-swings | Wrap-up asks its questions | pass | after the passing submit: What are the time and space complexity? | 0 |
| Coding | thermostat-swings | Report after End | pass | 2 dimensions, 5 moments, model template | 1019 |
| Coding | thermostat-swings | Written review in the report | blocked | metrics only: needs MODEL_API_KEY |  |
| Coding | thermostat-swings | No false 'replaced the edits' note | pass | none |  |
| Coding | ingredient-groups | Create session | pass | 201, session ed5a4d240861 | 3 |
| Coding | ingredient-groups | Problem API hides the answer | pass | no hidden tests, rubric or reference in GET /api/problems/{slug} |  |
| Coding | ingredient-groups | Socket hello → session.state | pass | phase intro | 70 |
| Coding | ingredient-groups | Warm-up greeting before the problem | pass | Hi, I'm Ares, and I'll be your interviewer today. Before we get to the… | 0 |
| Coding | ingredient-groups | Clock holds during the warm-up | pass | 1800 s left, still 1800 s 3 s later, phase intro |  |
| Coding | ingredient-groups | Skip Intro → clarify | pass | clarify with 1800 s left | 58 |
| Coding | ingredient-groups | Clock runs once the problem is presented | pass | 1800 s, then 1797 s 3 s later |  |
| Coding | ingredient-groups | Chat → transcript turn | pass | candidate turn recorded | 57 |
| Coding | ingredient-groups | Interviewer answers a question | blocked | no answer: needs MODEL_API_KEY |  |
| Coding | ingredient-groups | Start coding (clarify → coding) | pass | phase coding | 56 |
| Coding | ingredient-groups | Refuses going back (coding → clarify) | pass | error bad_phase | 58 |
| Coding | ingredient-groups | Hint button | blocked | server: hints aren't available right now (the live engine needs MODEL_API_KEY) | 65 |
| Coding | ingredient-groups | Typing raises no integrity note | pass | 0 notes while typing line by line |  |
| Coding | ingredient-groups | A paste becomes a neutral note | pass | pasted 14 lines at 00:16 | 56 |
| Coding | ingredient-groups | An infinite loop times out | pass | timed_out=True, timed out after 2 s | 6414 |
| Coding | ingredient-groups | Run the reference solution | pass | 3 of 3 tests passed | 294 |
| Coding | ingredient-groups | Submit the reference solution | pass | 15 of 15 tests passed | 345 |
| Coding | ingredient-groups | Live timeline hides analyses and notes | pass | 30 events, kinds ['editor', 'integrity', 'intervention', 'phase', 'run', 'snapshot', 'transcript'] |  |
| Coding | ingredient-groups | Edits reach the timeline | pass | 8 edit events, last snapshot matches the typed code |  |
| Coding | ingredient-groups | No report while live | pass | HTTP 409 |  |
| Coding | ingredient-groups | Reconnect keeps the session | pass | back in wrap_up (was wrap_up) | 54 |
| Coding | ingredient-groups | Wrap-up asks its questions | pass | after the passing submit: What are the time and space complexity? | 0 |
| Coding | ingredient-groups | Report after End | pass | 2 dimensions, 5 moments, model template | 1006 |
| Coding | ingredient-groups | Written review in the report | blocked | metrics only: needs MODEL_API_KEY |  |
| Coding | ingredient-groups | No false 'replaced the edits' note | pass | none |  |
| Coding | genre-sampler | Create session | pass | 201, session 49fdf0d7d8af | 3 |
| Coding | genre-sampler | Problem API hides the answer | pass | no hidden tests, rubric or reference in GET /api/problems/{slug} |  |
| Coding | genre-sampler | Socket hello → session.state | pass | phase intro | 50 |
| Coding | genre-sampler | Warm-up greeting before the problem | pass | Hi, I'm Ares, and I'll be your interviewer today. Before we get to the… | 0 |
| Coding | genre-sampler | Clock holds during the warm-up | pass | 2400 s left, still 2400 s 3 s later, phase intro |  |
| Coding | genre-sampler | Skip Intro → clarify | pass | clarify with 2400 s left | 65 |
| Coding | genre-sampler | Clock runs once the problem is presented | pass | 2400 s, then 2397 s 3 s later |  |
| Coding | genre-sampler | Chat → transcript turn | pass | candidate turn recorded | 65 |
| Coding | genre-sampler | Interviewer answers a question | blocked | no answer: needs MODEL_API_KEY |  |
| Coding | genre-sampler | Start coding (clarify → coding) | pass | phase coding | 57 |
| Coding | genre-sampler | Refuses going back (coding → clarify) | pass | error bad_phase | 58 |
| Coding | genre-sampler | Hint button | blocked | server: hints aren't available right now (the live engine needs MODEL_API_KEY) | 58 |
| Coding | genre-sampler | Typing raises no integrity note | pass | 0 notes while typing line by line |  |
| Coding | genre-sampler | A paste becomes a neutral note | pass | pasted 14 lines at 00:22 | 64 |
| Coding | genre-sampler | An infinite loop times out | pass | timed_out=True, timed out after 2 s | 6359 |
| Coding | genre-sampler | Run the reference solution | pass | 3 of 3 tests passed | 281 |
| Coding | genre-sampler | Submit the reference solution | pass | 17 of 17 tests passed | 605 |
| Coding | genre-sampler | Live timeline hides analyses and notes | pass | 53 events, kinds ['editor', 'integrity', 'intervention', 'phase', 'run', 'snapshot', 'transcript'] |  |
| Coding | genre-sampler | Edits reach the timeline | pass | 31 edit events, last snapshot matches the typed code |  |
| Coding | genre-sampler | No report while live | pass | HTTP 409 |  |
| Coding | genre-sampler | Reconnect keeps the session | pass | back in wrap_up (was wrap_up) | 68 |
| Coding | genre-sampler | Wrap-up asks its questions | pass | after the passing submit: What are the time and space complexity? | 0 |
| Coding | genre-sampler | Report after End | pass | 2 dimensions, 5 moments, model template | 1027 |
| Coding | genre-sampler | Written review in the report | blocked | metrics only: needs MODEL_API_KEY |  |
| Coding | genre-sampler | No false 'replaced the edits' note | pass | none |  |
| Defense | live on this machine | Create session | pass | 201, session a01d48a31177 | 8 |
| Defense | live on this machine | Audit arrives | pass | 1 finding(s), 1 node(s); without a key it uses the sample's flaws.json | 55 |
| Defense | live on this machine | Attack starts and streams metrics | pass | first metric received | 6904 |
| Defense | live on this machine | Attack finishes with a verdict | pass | broke: $20,699 disappeared across 10 accounts (6,064 requests at 20 | 10412 |
| Defense | live on this machine | Session moves on after the attack | pass | reached grill | 65 |
| Defense | recorded run (MOCK) | Create session | pass | 201, scenario defense-bank-transfer |  |
| Defense | recorded run (MOCK) | Stages in order | pass | audit → chaos → grill → fix → verify → verdict → ended | 4288 |
| Defense | recorded run (MOCK) | Audit hides explanations | pass | 1 findings, no explanation field |  |
| Defense | recorded run (MOCK) | Live attack metrics stream | pass | 24 metric messages |  |
| Defense | recorded run (MOCK) | Baseline breaks, verify holds | pass | baseline: broke; verify: held |  |
| Defense | recorded run (MOCK) | Grill graded with the finding revealed | pass | score 10/10 |  |
| Defense | recorded run (MOCK) | Merge gate verdict | pass | PASS |  |
| Frontend | pages | GET / | pass | HTTP 200, 72 KB | 171 |
| Frontend | pages | GET /coding | pass | HTTP 200, 16 KB | 72 |
| Frontend | pages | GET /defense | pass | HTTP 200, 15 KB | 64 |
| Frontend | pages | GET /coding/demo | pass | HTTP 200, 30 KB | 106 |
| Frontend | pages | GET /defense/demo | pass | HTTP 200, 26 KB | 70 |
| Frontend | pages | GET /report/demo | pass | HTTP 200, 39 KB | 802 |
| Frontend | pages | GET /coding/7d1871e0bba8 | pass | HTTP 200, 30 KB | 74 |
| Frontend | pages | GET /report/7d1871e0bba8 | pass | HTTP 200, 22 KB | 606 |

## Running it

Start the backend on `:8000`, a MOCK backend on `:8001` (`MOCK=1`) and the frontend on `:3000`, then from the repo root (the script's paths are relative to `backend/`):

```bash
uv --directory backend run python ../docs/evals/product_evals.py .. ../docs/evals/results.json
```

Each run starts about ten sessions, so raise `MAX_SESSIONS_PER_IP_PER_DAY` for the backend you test against. On Windows, Run and Submit need the harness timer from `fix/harness-windows-timer` (until it merges).
