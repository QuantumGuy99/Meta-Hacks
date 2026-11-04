# Team plans

[PLAN.md](../PLAN.md) is the spec for all of Crucible. The files in this folder split it by person: what
each of us owns, what we owe each other and by when, and the order to build things in. Each file is written so
you (or a coding agent such as Muse Code) can start from it without reading the whole spec first. It links to the PLAN
sections you need for the details.

**If a role plan and PLAN.md disagree, PLAN.md wins.** Fix the role plan in the same PR (PLAN §22 rule 15).

| Person | Plan | Area | Work packages |
|---|---|---|---|
| Srinithin Ganesh (SG) | [srinithin-engine-and-coding.md](srinithin-engine-and-coding.md) | Shared interviewer engine, Live Coding Interview backend, capture and replay libs | S-1, ENG-1…8, COD-1…6, VIS-1 |
| Shreyas Sahoo (SS) | [shreyas-defense-and-runner.md](shreyas-defense-and-runner.md) | Project Defense backend, code runner, scaffold, mock mode, deployment | S-0, S-1, RUN-1…3, DEF-1…10, OPS-1…2 |
| Likhil Gudipati (LG) | [likhil-frontend.md](likhil-frontend.md) | Every page and component in both modes | FE-1…8 |
| Sharvil Talware (ST) | [sharvil-data.md](sharvil-data.md) | Problem bank, sample defense apps, evals, demo data | DATA-1…7 |

---

## Where we are (Mon Oct 26, evening)

| Item | State |
|---|---|
| README + PLAN.md | Merged to `main` |
| Frontend scaffold + landing page (the frontend part of S-0, most of FE-1) | On Likhil's `frontend` branch, with his plan and UI rules in `frontend-schematic/`. No PR yet |
| Backend scaffold, Makefile, CI (rest of S-0) | Not started |
| Contracts (S-1) | Not started |
| Gold problems (DATA-1) | Not started |
| Repo visibility | **Private.** It must be public before we submit |

Update this table at each integration checkpoint.

---

## The handoffs that matter

At each of these points, one person's work blocks someone else's. If you're going to miss one, say so in the
team chat as soon as you know, and give the person who's waiting a stub they can build against.

| By (ET) | From → to | What | Unblocks |
|---|---|---|---|
| Tue Oct 27, morning | SS → all | S-0: backend skeleton, `make dev`, CI | All backend work |
| Tue Oct 27 | SG + SS → all | S-1: contracts + generated `contracts.ts` | FE-2, ENG-1, RUN-1, the DATA-1 format |
| Tue Oct 27 | SG → SS, ST | ENG-3: `models/llm.py` (`complete_json`, model roles) | DEF-2 audit, DATA-2 drafter |
| Tue Oct 27 | SS → SG, ST | RUN-1: `Runner`, `RunRequest`, harness, LocalRunner | COD-3 tests, DATA-2 validator |
| Tue Oct 27, night | ST → SG | DATA-1: 3 gold problems | ENG-4 analyzer, COD-1 |
| Wed Oct 28, morning | SG → LG | `lib/capture/editor.ts` (`attachEditorCapture`) | FE-3 room |
| Wed Oct 28, noon | ST → SS | `bank-transfer` sample app + `flaws.json` | DEF-2 audit for IC1 |
| Wed Oct 28 | SS → ST | LocalRunner `start_project` (runs a sample app locally) | `validate_apps` |
| Wed Oct 28 | SG → LG | REST sessions + WS `hello` / `session.state`, live on LocalRunner | IC1 |
| Wed Oct 28 | SG + SS | Agree on the engine hooks for defense and the eval format (see Open decisions) | DEF-5, DEF-6, DATA-5 |
| Thu Oct 29 | SS → LG | OPS-2 MOCK replay + defense fixtures + `lib/defense.ts` | FE-6 defense views |
| Thu Oct 29 | ST → SG | `skips-empty-input` and `off-by-one` evals | ENG-4 "done when" |
| Thu Oct 29 | ST → SS | `ticket-drop`, `report-service`, reference attacks, `fix.patch`, validator corpus | DEF-3, DEF-4 |
| Thu Oct 29 | SG → SS | Engine hooks built: `ModeController`, `RubricContext`, `Interviewer.say()` | DEF-5, DEF-6 |
| Fri Oct 30 | SG → LG | `lib/capture/audio` + `lib/replay.ts` (`codeAt`) | FE-4 voice, FE-7 replay |
| Fri Oct 30 | SS → SG | RUN-2: warm Modal sandbox for coding runs | IC2 |
| Sat Oct 31 | SG → SS, LG | ENG-8: ReportBuilder for both modes | DEF-7, FE-7 |
| Sat Oct 31 | SS → all | OPS-1: deployed frontend + backend | IC3 |
| Sat Oct 31 | ST → SG, SS | P0 evals (6 coding, 3 defense) | Eval tuning |
| Mon Nov 2 | ST → all | DATA-7: demo data, expected-behavior script, 2 rehearsals | Video takes |

---

## Rhythm

- **Integration checkpoints at 9 PM ET:** IC1 Wed Oct 28, IC2 Fri Oct 30, IC3 Sun Nov 1. Merge to `main`
  before 9 PM, then run the checkpoint script (PLAN §17) on a clean checkout.
- **Before each checkpoint**, post three lines in the team chat: done / next / blocked.
- **Feature freeze:** Tue Nov 3, 12 PM ET. **Submit by:** Wed Nov 4, 6 PM ET (3 hours of buffer before the
  9 PM deadline).
- **Branches:** `feat/<area>-<thing>` or `fix/<area>-<thing>`, small PRs, 1 review from the area owner
  (PLAN §22 rule 11).

---

## Using a coding agent (Muse Code)

Use one agent session per work package. Start each session with this prompt and fill in the brackets:

```text
You are building one work package of Crucible, a hackathon project. Read these first, in order:
1. PLAN.md §0 and §22 (rules for coding agents)
2. plan/<your-file>.md, the section for <WP-ID>
3. The PLAN.md sections that section lists under "Read"
Build <WP-ID> only. Touch only the paths listed for it, plus tests.
Contracts in backend/crucible/contracts/ are frozen unless the work package says otherwise.
Every model call goes through backend/crucible/models/llm.py. Prompts go in prompts/*.md files.
Done means every "Done when" item passes and `make check` is green.
If the plan is wrong or missing something, stop and tell me instead of guessing.
```

Read every diff before you commit it. Agents are fast at writing code that looks right; the rules in PLAN §22
exist because of that.

---

## Open decisions

| Decision | Proposal | Who decides | By |
|---|---|---|---|
| ~~Engine hooks for defense~~ | **Decided:** built in ENG-1, written up in PLAN §9.1 (`plan_session` added for session setup) | SG + SS | Done |
| Eval file format | [sharvil-data.md](sharvil-data.md#eval-format-proposed) | SG + ST, then copy into PLAN §13.3 | Wed Oct 28 |
| Sample-app reference attack file and the problem input generator | [sharvil-data.md](sharvil-data.md#data-4--defense-sample-apps) | SS + ST (attacks), SG + ST (generator) | Wed Oct 28 |
| `ChaosPlan` has no latency threshold, but the chaos verdict needs one (PLAN §11.4) | [shreyas-defense-and-runner.md](shreyas-defense-and-runner.md#s-1--contracts-v1-with-srinithin) | SG + SS in S-1 (SS proposes `p95_threshold_ms: int \| None`, PR #4) | Tue Oct 27 |
| Backend host: Railway or Fly.io | SS | SS | Fri Oct 30 |
| Who submits (the Representative) and who edits the video | | Everyone | IC3, Sun Nov 1 |
| Make the repo public | After the secrets check in PLAN §20.2 | The repo owner (QuantumGuy99) | Tue Nov 3 |
