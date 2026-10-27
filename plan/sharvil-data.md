# Sharvil: data for both modes

Your slice of [PLAN.md](../PLAN.md). PLAN has the spec details; this file has the order, the formats, the
handoffs and the checklists. Team overview and the handoff calendar: [plan/README.md](README.md).

## Your job

The interviewer is only as good as what it grades against. You write:
- **the problem bank:** original problems, each with tests, a reference solution and a rubric that says what a
  strong candidate does, step by step;
- **the sample defense apps:** small FastAPI apps that look fine but break under load, each with a documented
  flaw and a reference fix;
- **the evals:** scripted sessions that prove the interviewer behaves (nudges when it should, stays quiet when it
  should, never leaks the answer);
- **the demo data**, and the rehearsals that check the demo works.

You support Srinithin (problems, coding evals) and Shreyas (sample apps, defense evals, the validator test
corpus). When either of them asks for data that isn't on this list, it's probably yours too.

## What you own

| Path | What |
|---|---|
| `data/problems/` | The problem bank (`_drafts/` for unreviewed drafts) |
| `data/defense_apps/` | Sample apps (Shreyas reviews them) |
| `data/evals/` | Coding and defense evals |
| `backend/crucible/datatools/` | `draft_problem.py`, `validate_problems.py`, `validate_apps.py` |
| `backend/tests/defense/validator_corpus/` | Bad and good attack scripts for Shreyas's validator tests |
| The originality review | Every problem passes it before it leaves `_drafts/` |

**Don't touch:** `engine/`, `coding/`, `defense/`, `runner/` or the frontend. The datatools call the runner and
the model wrapper; they don't change them.

## Setup (Day 0, Mon Oct 26)

- [ ] Claim your Meta credits (individually), add a card, set a spend-limit notification (PLAN §15.3).
- [ ] Get `MODEL_API_KEY`. Ask for Baseten access if you want Spark Open for bulk drafting, and check V6 (its
      base URL).
- [ ] Python 3.12 + uv.
- [ ] Read PLAN §7.3, §13 and §22 rule 13.

---

## Handoffs

### You provide

| What | To | By | Why it's urgent |
|---|---|---|---|
| **DATA-1:** problem template + 3 gold problems (1 easy, 1 medium, 1 hard) | Srinithin | **Tue Oct 27, night** | His analyzer and ProblemBank can't be tested without them |
| `bank-transfer` app + `flaws.json` | Shreyas | **Wed Oct 28, noon** | The IC1 audit runs on it, and it's the demo app |
| `skips-empty-input` and `off-by-one` evals | Srinithin | Thu Oct 29 | His analyzer's "done when" uses them |
| 12 problems; `ticket-drop` and `report-service`; reference attacks + `fix.patch` for all 3 apps | Srinithin, Shreyas | Thu Oct 29 | P0 counts |
| Validator corpus | Shreyas | Thu Oct 29 | DEF-3's "done when" |
| 20 problems | Srinithin | Fri Oct 30 | |
| P0 evals: 6 coding + 3 defense | Srinithin, Shreyas | Sat Oct 31 | Eval tuning before IC3 |
| 30 problems; apps 4–5 (`search-api`, `rate-limiter`) | — | Sun Nov 1 | P1 |
| DATA-7: demo data, expected-behavior script, 2 rehearsals | Everyone | Mon Nov 2 | Video takes start Tue |

### You need

| What | From | By | Until then |
|---|---|---|---|
| S-1 contracts | Srinithin + Shreyas | Tue Oct 27 | Write against PLAN §7.3 directly; it's the same shape |
| RUN-1 LocalRunner | Shreyas | Tue Oct 27 | Check reference solutions with a throwaway script |
| ENG-3 `models/llm.py` | Srinithin | Tue Oct 27 | Write the gold problems by hand (they must be hand-written anyway) |
| LocalRunner `start_project` | Shreyas | Wed Oct 28 | Run the app with `uvicorn` and the attack by hand |

---

## Problem format

One folder per problem, `data/problems/<slug>/`:

| File | What |
|---|---|
| `problem.json` | A `ProblemSpec` (PLAN §7.3) without the three sibling-file fields |
| `statement.md` | The statement the candidate reads. Original story, names and examples |
| `reference.py` | A correct solution: one function with the exact name and signature from `problem.json` |
| `brute.py` | Optional: a slow, obviously correct solution, compared against the reference |
| `gen.py` | Optional (proposed): `def generate(rng: random.Random) -> list` returns one random set of positional args, for the brute-vs-reference check |
| `illustration.png` | P1: Muse Image, human-reviewed |

An abbreviated example. It's a real, original easy problem, but trimmed: a full one has 3–6 steps, 2–4 visible
tests and 8–25 hidden tests.

```json
{
  "slug": "quiet-streak",
  "title": "Quiet Streak",
  "difficulty": "easy",
  "topics": ["arrays"],
  "function": {
    "name": "longest_quiet_streak",
    "params": [{"name": "readings", "type": "list[int]"}, {"name": "threshold", "type": "int"}],
    "returns": "int"
  },
  "starter_code": "def longest_quiet_streak(readings: list[int], threshold: int) -> int:\n    pass\n",
  "examples": [
    {"input": "readings = [30, 52, 41, 38, 60, 35], threshold = 50", "output": "2",
     "explanation": "41 and 38 are the longest run of readings below 50."}
  ],
  "constraints": ["0 <= len(readings) <= 10^5", "0 <= readings[i], threshold <= 200"],
  "tests_visible": [
    {"id": "v1", "args": [[30, 52, 41, 38, 60, 35], 50], "expected": 2, "comparator": "exact", "edge_case_id": null}
  ],
  "tests_hidden": [
    {"id": "h1", "args": [[], 50], "expected": 0, "comparator": "exact", "edge_case_id": "e1"},
    {"id": "h2", "args": [[10, 20, 30], 50], "expected": 3, "comparator": "exact", "edge_case_id": "e2"}
  ],
  "rubric": {
    "approaches": [
      {"name": "single pass with a running count", "time": "O(n)", "space": "O(1)", "acceptable": true},
      {"name": "check every start index", "time": "O(n^2)", "space": "O(1)", "acceptable": false}
    ],
    "steps": [
      {"id": "s1", "title": "Clarify the input", "required": true, "order": 1,
       "description": "States what an empty list returns and whether a reading equal to the threshold counts as quiet.",
       "look_for": ["mentions the empty list", "asks whether equal to the threshold is quiet"],
       "hints": ["Before you code, is there anything about the input you'd want to pin down?",
                 "What should happen if there are no readings at all?",
                 "Settle the empty list and the equal-to-threshold case before you start."]},
      {"id": "s2", "title": "Count a streak that reaches the end", "required": true, "order": 2,
       "description": "Records the best length for a streak that is still running when the loop ends.",
       "look_for": ["updates the best length after the loop", "updates the best length on every quiet reading"],
       "hints": ["Look at what happens on your last reading.",
                 "If the longest quiet stretch is at the very end, when does your code record it?",
                 "A streak can end because the list ends, not only because of a loud reading."]}
    ],
    "edge_cases": [{"id": "e1", "description": "empty list"}, {"id": "e2", "description": "every reading is quiet"}],
    "common_mistakes": [
      {"id": "m1", "description": "only updates the best length when a loud reading appears",
       "symptom": "fails when the longest streak runs to the end of the list"}
    ],
    "wrap_up_questions": ["What are the time and space complexity?",
                          "How would you change this if readings arrived one at a time as a stream?"]
  },
  "time_limit_min": 20,
  "illustration": null,
  "origin_note": "Original. Pattern: single pass with a running counter."
}
```

### Quality bar (PLAN §13.1)
- [ ] 3–6 rubric steps with `order`, at least one about edge cases.
- [ ] Each step has exactly 3 hints that escalate (point at the area → Socratic question → name the technique)
      and contain **no code**.
- [ ] `look_for` lists concrete signals you could see in code or hear in speech.
- [ ] Every edge case maps to at least one hidden test through `edge_case_id`.
- [ ] 2 wrap-up questions: complexity, plus a trade-off or edge case.
- [ ] `time_limit_min`: easy 20, medium 30, hard 40, unless there's a reason.
- [ ] The starter code compiles and fails at least one test.

### Originality (a rights risk means disqualification)
- [ ] A fresh story, names and examples. Classic **patterns** are fine; copied **wording** is not.
- [ ] No titles, text or examples from LeetCode, HackerRank or anywhere else, and never paste a site's problem
      text into the drafter prompt.
- [ ] You'd be comfortable if the original site's authors read it.

### Coverage (PLAN §13.1)
P0's 12 = 4 easy, 6 medium, 2 hard, spread across the patterns in the §13.1 table. Mark 1 easy and 1 medium as
**demo problems**.

---

## Work packages, in build order

### DATA-1 — Problem template + 3 gold problems
**P0 · Mon–Tue (done by Tue Oct 27, night)** · Read: PLAN §7.3, §13.1
1. Write the template from the example above (`data/problems/_template/`).
2. Write 3 problems **by hand**: 1 easy, 1 medium, 1 hard, from different patterns, to the full quality bar.
3. Make the medium one a **demo candidate**: it needs an edge-case step that's easy to skip and easy to see on
   camera (like `s2` above). The video shows the candidate skipping the empty-input case and getting nudged.
4. Check each reference solution against every test, even with a throwaway script, until LocalRunner exists.

**Done when:** Srinithin's ProblemBank loads all 3 and the reference solutions pass every test.

### DATA-2 — Draft and validate tools
**P0 · Wed · needs RUN-1, ENG-3** · Read: PLAN §13.1 (pipeline), §13.2
**Files:** `datatools/draft_problem.py`, `datatools/validate_problems.py`, `datatools/validate_apps.py`
1. `draft_problem --pattern "sliding window" --difficulty medium`: drafts `problem.json`, the statement,
   reference and brute (and `gen.py`) into `data/problems/_drafts/` with the `drafter` role (Spark 1.3, or
   Spark Open for bulk runs).
2. `validate_problems [slug|--all]`: the schema; the reference passes every test through LocalRunner; brute
   agrees with the reference on 200 random inputs when `gen.py` exists; the starter compiles and fails a test;
   every edge case has a test; hints contain no code (the leak-guard heuristic); the time limit is set.
3. `validate_apps [slug|--all]`: the app boots in the runner; the reference attack **breaks** the original;
   with `fix.patch` applied, the same attack **holds**.

### DATA-3 — Problem bank
**P0: 12 by Thu Oct 29 · then 20 Fri, 25 Sat, 30 by Sun Nov 1 (P1) · 40+ (P2)**
Draft → `validate_problems` → your human review (quality bar + originality) → move from `_drafts/` to
`data/problems/`. Never commit a problem to `data/problems/` that hasn't passed both (PLAN §22 rule 13).

### DATA-4 — Defense sample apps
**P0: `bank-transfer` by Wed Oct 28 noon, 3 apps by Thu Oct 29 · P1: +2 by Sun Nov 1** · Read: PLAN §11.1, §13.2

One folder per app, `data/defense_apps/<slug>/`:

| File | What |
|---|---|
| `app/` | FastAPI, 150–400 lines, in a realistic "AI-generated" style: plausible, readable, subtly wrong |
| `requirements.txt` | Pinned |
| `crucible.json` | `{"entrypoint": "uvicorn app.main:app --host 127.0.0.1 --port 8080", "port": 8080}` (8080 keeps clear of the backend's :8000 when LocalRunner runs the app) |
| `flaws.json` | Ground truth: `[{id, category, file, line_start, line_end, explanation, expected_fix, grill_expected_points, chaos_invariant}]` |
| `fix.patch` | The reference fix, as a unified diff that `git apply` accepts |
| `reference_attack.json` | Proposed (agree with Shreyas): `{"concurrency": 200, "duration_s": 10, "functions": <AttackFunctions>}`, the three template bodies that prove the flaw (PLAN §11.4) |

`reference_attack.json` goes through the same template and validator as the AI-written attacks, so it also
proves the validator accepts a good script.

| Slug | Seeded flaw | Invariant | P |
|---|---|---|---|
| `bank-transfer` | `/transfer` reads the sender's balance, awaits a "fraud check" (`await asyncio.sleep(0.03)`), then writes `balance - amount`; no transaction or lock. Target headline: "Under 200 concurrent transfers, $1,240 disappeared" | Total balance stays constant | P0, demo |
| `ticket-drop` | Check-then-insert on seat availability. Target: "Under 150 concurrent checkouts, 38 seats double-booked". **Second finding:** an O(n²) unindexed seat-recommendation loop (its own `flaws.json` entry) | Each seat sold at most once; sold ≤ capacity | P0 |
| `report-service` | Blocking `time.sleep` or CPU work inside an `async def` route | `/health` p95 < 200 ms while `/report` is loaded | P0 |
| `search-api` | O(n²) dedupe per request | p95 grows with dataset size | P1 |
| `rate-limiter` | Unsynchronized counter + unbounded dict | Allowed ≤ limit per window | P1 |

**Reference attacks** use the PLAN §11.4 template: `check_invariant` returns **`(ok, violations, detail)`**.
`violations` is a count people understand (dollars missing, seats double-booked) and is charted live;
`detail` is the headline with the real numbers. Optional extras in a `flaws.json` entry that the audit
fallback uses: `title` (neutral, names the area not the cause), `severity`, `grill_question`, `grill_follow_up`,
`fix_steps`, and `chaos: {endpoint, method, body_example, concurrency, duration_s, p95_threshold_ms}`
(`p95_threshold_ms` for latency flaws like `report-service`). A working example lives in
`backend/tests/fixtures/apps/bank-transfer-min/` once Shreyas's Defense PR lands.

**`bank-transfer` tips (it's the demo):** make the `await` look natural (an `await fraud_check(...)` or an
audit-log call between reading and writing the balance), so the race reproduces on **every** run at 200
concurrent transfers. Use round numbers, like 10 accounts × $1,000, so the chaos summary reads as money:
"$1,240 missing".

**Done when:** `validate_apps --all` shows break at baseline and hold with `fix.patch` for every P0 app.

### Validator corpus (for Shreyas's DEF-3)
**P0 · Thu Oct 29** · Read: PLAN §11.4 (ScriptValidator)
`backend/tests/defense/validator_corpus/`: 15–20 **bad** attack-function sets, each breaking exactly one rule
(a forbidden import, `open`, `getattr`, `os.system`, a URL to another host, `CONCURRENCY = 500`, …), and 5
**good** ones. Name each file after the rule it breaks: `bad_import_subprocess.json`, `good_bank_transfer.json`.

### DATA-5 — Evals
**P0: 2 by Thu Oct 29, then 6 coding + 3 defense by Sat Oct 31 · P1: the full list in PLAN §13.3**
- **First (Thu):** `skips-empty-input` and `off-by-one`.
- **P0 coding six:** those two, plus `clean-solve`, `paste-solution`, `asks-for-answer`, `passive-mode`.
- **P0 defense three:** one per P0 app.

### DATA-6 — Muse Image illustrations
**P1** · Read: PLAN §13.1; check V10 first
Grid, tree and graph problems only. Generate them offline, review each one by eye (labels match the statement),
commit the PNGs and set `illustration`.

### DATA-7 — Demo data + rehearsal
**P0 · Mon Nov 2** · Read: PLAN §20
1. Lock the demo problem (medium, 10-minute preset) and the demo app (`bank-transfer`).
2. Write the **expected-behavior script**: for each beat of the §20.1 video, what the candidate says and does,
   and what the interviewer should do.
3. Run 2 dry runs on the deployed build. Log what went wrong, who owns it, and whether it's fixed.

---

## Eval format (proposed)

Agree on this with Srinithin by **Wed Oct 28**, then copy it into PLAN §13.3. Srinithin writes the runner that
plays these files through the real engine with a simulated clock (`backend/tests/evals/`).

An eval is a recording of **what the candidate did**. The engine produces everything else, so you never
hand-write a `RunResult` or an `Analysis`. One JSON object per line:

```jsonl
{"meta": {"problem_slug": "quiet-streak", "feedback": "active", "voice": true, "about": "forgets the streak that reaches the end"}}
{"t": 0,      "do": "say",      "text": "I'll walk the list once and keep a running count of quiet readings."}
{"t": 20000,  "do": "snapshot", "code": "def longest_quiet_streak(readings, threshold):\n    best = cur = 0\n"}
{"t": 65000,  "do": "snapshot", "code": "...the code at 65 s..."}
{"t": 70000,  "do": "run"}
{"t": 90000,  "do": "chat",     "text": "Is this right?"}
{"t": 95000,  "do": "paste",    "code": "...the whole file after the paste...", "pasted": "...the pasted block..."}
{"t": 120000, "do": "hint"}
{"t": 150000, "do": "submit"}
{"expect": {"fires": [{"trigger": "missed_step", "step_id": "s2", "by_t": 140000}],
            "never": ["bug_suspected"], "max_shown": 3, "no_leak": true, "flags": ["paste"]}}
```

- `do` values: `say` (a final voice turn), `chat`, `snapshot`, `paste`, `run`, `submit`, `hint`, `advance` (with
  `"to": "coding"` or `"wrap_up"`), `end`. A gap in `t` is idle time, which is how you script `stuck-idle`.
- Use `snapshot` lines every few seconds instead of keystroke edits. The engine reconciles from snapshots, so
  this is much faster to write and behaves the same.
- `expect` can check: `fires` (trigger, optional `step_id`, `by_t`), `never` (triggers that must not appear),
  `max_shown` (unsolicited messages shown), `no_leak` (the leak guard held), `flags` (integrity flag kinds).
- An eval passes if its expectations hold in ≥ 2 of 3 runs (PLAN §18).

**Defense evals** (`data/evals/defense/<slug>.json`):
`{"app": "<slug>", "expected_findings": [{"flaw_id", "file", "line_start", "line_end", "category"}],
"baseline": "broke", "verify_with_fix_patch": "held"}`.

---

## Day by day

| Day | Date | Build | End-of-day check |
|---|---|---|---|
| 0 | Mon Oct 26 | Setup, template, start the gold problems | Template committed |
| 1 | Tue Oct 27 | **DATA-1 done**, start `bank-transfer` | 3 gold problems pass their tests |
| 2 | Wed Oct 28 | `bank-transfer` by noon, DATA-2 tools, `ticket-drop`; agree on the eval format | **IC1** |
| 3 | Thu Oct 29 | **12 problems**, `report-service`, reference attacks, validator corpus, 2 early evals | **3 apps validated** |
| 4 | Fri Oct 30 | Evals v1, 20 problems | **IC2** |
| 5 | Sat Oct 31 | P0 evals done, 25 problems | |
| 6 | Sun Nov 1 | **30 problems**, apps 4–5 | **IC3** + cut-line review |
| 7 | Mon Nov 2 | DATA-7: demo data + 2 rehearsals | Demo script passes twice |
| 8 | Tue Nov 3 | **Feature freeze 12 PM.** Final data checks; help record takes | Takes recorded |
| 9 | Wed Nov 4 | Originality check on every problem; **submit by 6 PM** | Submitted |

## Risks to watch

- **A sample app that doesn't break every time:** the demo can't depend on luck. Re-run `validate_apps` 5
  times on `bank-transfer` and make the race wider if it ever holds.
- **Drafted problems with subtle test bugs:** `brute.py` + `gen.py` catches most of them. Use them on every
  medium and hard problem.
- **Hints that give away the answer:** if a hint names the exact line to write, it's a leak, even without
  code. Rewrite it as a question.

## PR checklist

- [ ] Branch `feat/data-…`; one batch of problems or one app per PR
- [ ] `make validate` passes
- [ ] Originality checklist ticked in the PR description, for every new problem
- [ ] Nothing in `data/problems/` that hasn't had a human review
- [ ] PLAN.md and this file updated if a format changed
