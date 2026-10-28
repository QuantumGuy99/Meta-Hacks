# Srinithin: shared engine + Live Coding Interview

Your slice of [PLAN.md](../PLAN.md). PLAN has the spec details; this file has the order, the handoffs and the
checklists. Team overview and the handoff calendar: [plan/README.md](README.md).

## Your job

You build the part that makes Crucible feel alive: the interviewer that watches the edit stream, decides when
to speak, and writes the report. Both modes run on it. Coding mode uses it for the whole session; defense
mode uses it for the fix stage and sends its grill questions through it. You also own the coding-mode backend
and the browser libraries that feed the engine (editor and audio capture) and play back what it recorded
(`codeAt`).

The engine is the product (PLAN §1). If you fall behind, cut P1 coding features before you cut engine quality.

## What you own

| Path | What |
|---|---|
| `backend/crucible/engine/` | `hub`, `timeline`, `codestate`, `analyzer`, `policy`, `interviewer`, `voice`, `report`, `context`, `prompts/` |
| `backend/crucible/models/` | `llm.py`, `asr.py`, `image.py`, `sam.py`, `registry.py`, `smoke.py` |
| `backend/crucible/coding/` | `problems`, `session` (phases, timers), `tests` (RunService), `integrity`, `prompts/` |
| `backend/crucible/vision/` | P2 SAM 3.1 features |
| `backend/crucible/contracts/` | Co-owned with Shreyas; you both approve every change |
| `backend/crucible/mock/fixtures/coding-*.jsonl`, `report-coding.jsonl` | Coding fixtures (Shreyas owns the replay engine) |
| `frontend/src/lib/capture/editor.ts`, `frontend/src/lib/capture/audio/*`, `frontend/src/lib/replay.ts` | Non-visual browser code |
| `backend/tests/engine/`, `backend/tests/coding/`, `backend/tests/models/`, `backend/tests/evals/` | Tests and the eval runner |

**Don't touch:** pages and components (Likhil), `defense/`, `runner/`, `store/`, `main.py`, `config.py`
(Shreyas), `data/` (Sharvil). If you need a change there, note it in your PR or ask the owner.

## Setup (Day 0, Mon Oct 26)

- [ ] Claim your Meta credits (each person fills in the form individually), add a card, and set a spend-limit
      notification on the Billing page (PLAN §15.3).
- [ ] Get `MODEL_API_KEY` and make one `beta.chat.completions.parse` call against `muse-spark-1.3` and one
      against `muse-wonder-1.0`. That answers V3 and V4 early.
- [ ] Python 3.12 + uv; Node ≥ 22 + pnpm (`corepack enable`).
- [ ] Muse Code: install it and try it on a throwaway task before using it on real work. Use the agent
      prompt in [plan/README.md](README.md#using-a-coding-agent-muse-code-claude-code).
- [ ] Read PLAN §4, §7–§10, §15 and §22.

---

## Handoffs

### You provide

| What | To | By | Notes |
|---|---|---|---|
| S-1 contracts (with Shreyas) | Everyone | Tue Oct 27 | Tell Likhil the day it merges so he can delete `contracts.draft.ts` |
| `models/llm.py`: `complete_json`, `complete_text`, roles in `registry.py`, `smoke.py` | Shreyas (audit, grill, attacker fallback), Sharvil (drafter) | Tue Oct 27 | ENG-3. Share the smoke script so they can check their own keys |
| `attachEditorCapture` | Likhil | Wed Oct 28, morning | ENG-2. Signature below |
| `POST/GET /api/sessions`, WS `/ws/sessions/{id}` with `hello` → `session.state` | Likhil | Wed Oct 28 | ENG-1, needed for IC1 |
| Hand-written fixtures `coding-active.jsonl`, `report-coding.jsonl` | Likhil (FixtureTransport), Shreyas (OPS-2) | Wed Oct 28 | Format in PLAN §14.6. Replace them with recorded ones after IC2 |
| Engine hooks for defense, built | Shreyas | Thu Oct 29 | [Below](#engine-hooks-for-defense-proposed); agree on them by Wed |
| `startAudioCapture` | Likhil | Fri Oct 30 | ENG-7. Signature below |
| `codeAt` (`lib/replay.ts`) | Likhil | Fri Oct 30 | He needs it for FE-7 on Sat |
| ReportBuilder for both modes | Shreyas (DEF-7), Likhil (FE-7) | Sat Oct 31 | ENG-8 |

### You need

| What | From | By | Until then |
|---|---|---|---|
| S-0 backend skeleton (`main.py`, `config.py`, `store/`) | Shreyas | Tue Oct 27, morning | Start `engine/` on a branch and rebase |
| RUN-1: `Runner`, `RunRequest` (PLAN §12), LocalRunner | Shreyas | Tue Oct 27 | A fake runner in tests that returns a canned `RunResult` |
| DATA-1: 3 gold problems | Sharvil | Tue Oct 27, night | The example problem in [sharvil-data.md](sharvil-data.md#problem-format), for smoke tests only |
| `skips-empty-input` and `off-by-one` evals | Sharvil | Thu Oct 29 | Script them yourself in the [eval format](sharvil-data.md#eval-format-proposed) |
| The interview room UI | Likhil | Wed Oct 28 | A Python WebSocket client script |
| RUN-2: warm Modal sandbox | Shreyas | Fri Oct 30 | LocalRunner |
| OPS-1: deployed backend | Shreyas | Sat Oct 31 | Local |

### Browser library signatures (agree with Likhil)

```ts
// lib/capture/editor.ts. Behavior is in PLAN §14.3.
export function attachEditorCapture(
  editor: CapturableEditor,                       // structural: any Monaco editor fits
  send: (msg: ClientMessage) => void,
  opts: { file?: string; startedAtMs: number },   // session.started_at from session.state
): { snapshot(): void; flush(): void; setFile(file: string): void;
     programmatic(edit: () => void): void; dispose(): void };
// Call snapshot() before sending code.run / code.submit / defense.verify.
// Wrap programmatic edits (reset to starter code, loading a file) in programmatic() so they aren't typing.

// lib/capture/audio/index.ts. Behavior is in PLAN §14.3 and §8.3.
export function startAudioCapture(opts: {
  wsUrl: string;                                  // /ws/sessions/{id}/audio
  onState?: (s: "starting" | "live" | "error" | "stopped") => void;
}): Promise<{ setPaused(paused: boolean): void; setAsking(holding: boolean): void; stop(): void }>;
// tts.ts calls setPaused(true) while the interviewer is speaking, so we don't transcribe it (silence is sent).
// The Ask button calls setAsking(true) on press and setAsking(false) on release (ENG-7 added this).
// "error" covers a denied mic and the server refusing voice (4403/4409/4503): show "use chat".

// lib/replay.ts. Same algorithm as engine/codestate.py (PLAN §9.3).
export function codeAt(timeline: TimelineEvent[], file: string, t: number): string;
```

---

## Engine hooks for defense (proposed)

Shreyas's defense code needs to plug into the engine without editing it. This isn't in PLAN yet. Agree on it
with Shreyas by **Wed Oct 28**, then copy the agreed version into PLAN §9.

```python
# engine/context.py
@dataclass(frozen=True)
class RubricContext:
    """What the analyzer, policy and leak guard grade against. Coding mode builds one from a ProblemSpec;
    the defense fix stage builds one from a Finding (plus the sample app's fix.patch)."""
    title: str
    brief_md: str                    # problem statement, or finding explanation + chaos summary
    steps: list[RubricStep]          # rubric.steps, or finding.fix_steps
    edge_cases: list[EdgeCase]       # [] in defense
    common_mistakes: list[Mistake]   # [] in defense
    wrap_up_questions: list[str]     # [] in defense
    reference_text: str | None       # leak guard source: reference.py, or fix.patch
    files: list[str]                 # editable files: ["solution.py"], or the finding's files

# engine/hub.py
class ModeController(Protocol):
    def allowed_transitions(self) -> dict[Phase, set[Phase]]: ...
    async def on_start(self, rt: SessionRuntime) -> None: ...
    async def on_client_message(self, rt: SessionRuntime, msg: ClientMessage) -> bool: ...  # True = handled
    async def on_timeline(self, rt: SessionRuntime, ev: TimelineEvent) -> None: ...      # e.g. final transcript turns
    async def report_extra(self, rt: SessionRuntime) -> CodingExtra | DefenseExtra: ...

# engine/interviewer.py
async def say(rt: SessionRuntime, text: str, trigger: InterventionTrigger, level: InterventionLevel,
              speak: bool, step_id: str | None = None) -> Intervention:
    """Leak guard → timeline → interviewer.message (+ an interviewer TranscriptTurn).
    Used for phase lines and for Shreyas's grill questions."""
```

- The hub handles the shared messages (`hello`, `editor.*`, `chat.send`, `hint.request`, `session.end`) and
  passes everything else to the session's controller. `CodingController` (`coding/session.py`) is yours;
  `DefenseController` (`defense/`) is Shreyas's.
- `rt.engine.attach(ctx)` turns the analyzer and policy on for a `RubricContext`; `rt.engine.detach()` turns
  them off. Coding attaches at `clarify`; defense attaches at `fix`.
- During the grill the engine is detached, so a chat answer becomes a candidate `TranscriptTurn` that only the
  `DefenseController` reacts to (through `on_timeline`). The `ASKED` rule doesn't fire on it.

---

## Work packages, in build order

Each one lists what to read, the files, the steps and the "done when". Hand any of them to an agent with the
prompt in [plan/README.md](README.md#using-a-coding-agent-muse-code-claude-code).

### S-1 — Contracts v1 (with Shreyas)
**P0 · Mon–Tue · needs S-0** · Read: PLAN §7, §8.2
**Files:** `contracts/*.py`, `contracts/export.py`, `backend/tests/fixtures/*.json`, `backend/tests/contracts/`
1. Transcribe §7 exactly. Every model inherits `Strict`. LLM output models (`Analysis`, `InterventionText`,
   `AuditResult`, `AttackFunctions`, `GrillEval`, `ReportDraft`) have no defaults.
2. `ws.py`: one class per row of §8.2 with `type: Literal[...]`, and the two discriminated unions.
3. `PhaseChange` and `SystemNote` payload models for the timeline (§7.2).
4. `export.py`: a JSON Schema of every top-level model and both unions → `pnpm dlx json-schema-to-typescript`
   → `frontend/src/types/contracts.ts`.
5. One fixture JSON per top-level model, and a test that each one validates.
6. A test that every LLM output model's JSON Schema has every field required and
   `additionalProperties: false`. This catches strict-mode mistakes before the API returns a 400.
7. Settle the `ChaosPlan` threshold question with Shreyas
   ([details](shreyas-defense-and-runner.md#s-1--contracts-v1-with-srinithin)).

**Done when:** `make contracts` is clean, and Likhil and Sharvil have reviewed the PR.

### ENG-3 — Model wrapper
**P0 · Tue · needs S-1** · Read: PLAN §15.1, §15.2; V3, V4
**Files:** `models/llm.py`, `models/registry.py`, `models/smoke.py`, `backend/tests/models/`
1. `AsyncOpenAI(base_url=settings.META_BASE_URL, api_key=settings.MODEL_API_KEY)`. Pass the key explicitly.
2. `complete_json(role, messages, schema, effort=, timeout_s=, images=)` via
   `client.beta.chat.completions.parse(response_format=schema, reasoning_effort=...)`.
3. Retry once on 429/5xx with jittered backoff, then walk the role's fallback chain (§15.1 table).
4. Log model, latency, tokens and estimated cost to stdout, and as a `system` timeline note when you have a
   session id.
5. `USE_CONTRIBUTOR_MODELS=1` maps `muse-spark-1.3` → `muse-spark-1.3-contributor` and never sends `max`
   effort.
6. Baseten (Spark Open) is a second client with its own `base_url`, created in the same module.
7. `python -m crucible.models.smoke`: one tiny `parse` call per role.

**Tests:** with a fake client: retry, then fallback; timeout, then fallback; the contributor mapping.
**Done when:** the smoke script passes against the live API. Record the V3 and V4 results in PLAN §23.

### ENG-1 — Hub, sessions, timeline, store glue
**P0 · Tue · needs S-1** · Read: PLAN §8.1, §8.2, §9.1, §9.2
**Files:** `engine/hub.py`, `engine/timeline.py`, `engine/context.py`, the sessions router, `backend/tests/engine/`
1. `POST /api/sessions` (coding: pick a problem through `ProblemBank`, stubbed until COD-1), `GET
   /api/sessions/{id}`, `POST /api/sessions/{id}/end`, `GET /api/sessions/{id}/timeline` (strip hidden-test
   inputs).
2. WebSocket `/ws/sessions/{id}`: a `SessionRuntime` created on first connect and destroyed 10 min after the
   last disconnect; `hello` → `session.state`; `broadcast()` to every socket.
3. `Timeline.append(kind, payload, t=None)` validates against `PAYLOAD_MODELS`, assigns `seq` and `t`, writes
   through Shreyas's `store/repo.py` in 250 ms batches, and keeps an in-memory tail.
4. `runtime.set_phase(to, reason)` checks `controller.allowed_transitions()`, appends a `phase` event and
   broadcasts `session.state`. `phase.advance` from the client accepts only clarify → coding and coding →
   wrap_up.
5. The `ModeController` routing from the hooks above.
6. Ask Shreyas to `include_router` your routers in `main.py`. Don't edit it yourself.

**Tests:** a test client connects, sends events and reads them back from `/timeline` in order; an invalid
payload is rejected; reconnecting gets `session.state` again.
**Done when:** PLAN §16 ENG-1.

### ENG-2 — CodeState, editor capture, replay parity
**P0 · Wed (ship the capture lib first thing Wed) · needs ENG-1** · Read: PLAN §9.3, §14.3
**Files:** `engine/codestate.py`, `frontend/src/lib/capture/editor.ts`, `frontend/src/lib/replay.ts`,
`backend/tests/fixtures/replay_case.json`
1. Apply each `EditorEvent`'s changes sorted by `range_offset` descending:
   `code = code[:off] + text + code[off + length:]`.
2. A snapshot that disagrees with the reconstruction wins; log a `system` warning.
3. Counters: `chars_typed`, `chars_pasted`; a single change of ≥ 80 chars without a paste event is a bulk
   insert. `diff_since_analysis()` with difflib.
4. `editor.ts` per §14.3: event kinds, paste flag, visibility/blur, 500 ms batches, snapshots every 20 changes
   or 15 s, `t` aligned to `session.started_at`.
5. `replay.ts`: `codeAt` = the last snapshot ≤ t plus the edits after it.
6. Parity test: `replay_case.json` reconstructs identically in Python (pytest) and TypeScript. Run the TS
   side with `node --experimental-strip-types`, or add `vitest` as a dev dependency (list it in the PR).

**Done when:** PLAN §16 ENG-2.

### COD-1 — ProblemBank + problem API
**P0 · Wed · needs S-1, DATA-1** · Read: PLAN §10.2, §8.1, §7.3
**Files:** `coding/problems.py`, the problems router, `backend/tests/coding/`
1. Load `data/problems/*/` (skip `_drafts/`), validate against `ProblemSpec`, load the sibling files. An
   invalid problem fails startup in dev and is skipped with a log in prod.
2. `random(difficulty, topic)`, excluding problems used in the last 5 sessions from the same IP.
3. `GET /api/problems`, `GET /api/problems/{slug}` → `ProblemPublic`; the illustration route (P1).
4. `RubricContext.from_problem(spec)`.

**Tests:** `ProblemPublic` never contains hidden test ids, rubric text or the reference solution.

### COD-3 — Test service (thin version Wed for IC1, finished Thu)
**P0 · needs RUN-1** · Read: PLAN §10.3, §12
**Files:** `coding/tests.py`, `backend/tests/coding/`
1. `code.run` / `code.submit` → build a `RunRequest` (Run: visible cases; Submit: visible + hidden) →
   `runner.run_tests`.
2. Store the full result in the timeline (`run`). Broadcast a redacted copy as `run.result`: hidden cases get
   `input_repr`, `expected_repr` and `actual_repr` set to `None`, and `error` reduced to the error class.
3. Trigger the analyzer. Call `runner.open_session` when the session starts (warm sandbox) and
   `close_session` when it ends.

**Tests:** hidden inputs never appear in a broadcast; compile errors; timeouts.
PLAN §17 puts COD-3 on Thu, but IC1 needs Run to work on Wed, so land the thin version Wed.

### ENG-4 — Analyzer (thin path Wed for IC1, finished Thu)
**P0 · needs ENG-2, ENG-3, DATA-1** · Read: PLAN §4.2, §9.4
**Files:** `engine/analyzer.py`, `engine/prompts/analyzer_system.md`, `backend/tests/engine/`
1. Single-flight scheduler: run on a ≥ 2.5 s typing pause with changed code, a run result, a final candidate
   turn or `chat.send`, or 30 s with any change. At most once per 8 s (asks skip the floor). Set `dirty` while
   a call is in flight and run once more when it returns.
2. Prompt in three blocks, static first: system, problem (from `RubricContext`), then dynamic state (code
   with line numbers, diff, last 3 runs, last 90 s of transcript, step statuses, interventions already given,
   hint levels, feedback mode).
3. Spark 1.3, `reasoning_effort="low"`, 12 s timeout, `Analysis` schema. On timeout or error, skip the tick
   and log a `system` note.
4. Append `analysis` to the timeline; broadcast `notes.update`.

**Thin path for IC1 (Wed 9 PM):** analyzer → a minimal policy with only `MISSED_STEP` and the 45 s cooldown →
the proposal text through a code-fence check → `interviewer.message`. ENG-5 and ENG-6 replace it.
**Tests:** the scheduler with a fake clock (pause, 8 s floor, ask bypass, dirty re-run); a prompt-builder
snapshot test.
**Done when:** PLAN §16 ENG-4: on the 3 gold problems, `skips-empty-input` and `off-by-one` produce the
expected step or issue in ≥ 2 of 3 runs. Those two evals come from Sharvil on Thu.

### ENG-5 — Policy, hint ladder, passive mode
**P0 · Thu · needs ENG-4** · Read: PLAN §9.5 · **Built Tue Oct 27** (PR "feat(engine): ENG-5 policy")
**Files:** `engine/policy.py`, `engine/live.py` (policy task), `engine/interviewer.py` (fallback text),
`engine/hub.py` (`hint.request`), `engine/prompts/canned.md`, `backend/tests/engine/test_policy.py`,
`backend/tests/engine/test_live.py`
1. Per-session state and the global guards: no unsolicited message within 2.5 s of an edit or during
   speech (one-slot queue, dropped after 20 s), 45 s between unsolicited messages, at most 8 per 30 min, and
   no repeat of the same `(trigger, step_id)` at the same level.
2. The 12 rules in table order; the first match wins.
3. The hint ladder (nudge → question → hint → concept) counted into `hints_by_level`.
4. Passive mode: evaluate everything, log `Intervention(suppressed=True)`, deliver only `ASKED`,
   `HINT_REQUESTED` and `TIME_WARNING`.

**Tests:** a "fires" and a "doesn't fire" test per rule, plus each guard.
**Done when:** PLAN §16 ENG-5.
**Left for later:** `PRAISE` needs a `tricky` flag on `RubricStep` (contract change, SG + SS). `ASKED` replies
through ENG-6's `answer()` (canned line as its fallback). The coding evals' policy expectations (§16) run once
Sharvil's evals land.

### ENG-7 — VoiceBridge + audio capture
**P1, but start Thu · finish Fri · needs ENG-1** · Read: PLAN §8.3, §9.7, §14.3; V1 first
**Files:** `engine/voice.py`, `models/asr.py`, `frontend/src/lib/capture/audio/*`
1. Check V1 in the realtime docs first and write down what you find in PLAN §23.
2. On the audio socket's `start`, open the realtime ASR socket and send the handshake within 10 s. Forward
   binary frames as they arrive; never buffer and burst.
3. Partials → `transcript.update` (not stored); completed turns → a final `TranscriptTurn` in the timeline.
4. Close codes and the fallbacks: 3 realtime failures → 10 s WAV chunks to `/v1/asr/transcribe` → "voice
   unavailable, use chat".
5. Browser: `getUserMedia` → AudioWorklet → 24 kHz Int16 → 1,920-sample frames, with `setPaused` for TTS.

**Done when:** PLAN §16 ENG-7.
**As built** (PR "feat(engine): voice in (ENG-7)", stacked on ENG-8): see PLAN §8.3 and §9.7. V1 is done (§23).
Added beyond the list: the Ask button (`setAsking`, a voice turn held on Ask is a question), silence while
paused, and close codes for "use chat". Live: final turns 0.1–0.2 s after speech ends; with realtime disabled,
the 10 s chunk fallback produced timed turns from the real file endpoint.

### ENG-6 — Interviewer + leak guard
**P0 · Fri · needs ENG-5** · Read: PLAN §9.6 · **Built Tue Oct 27** (PR #27, stacked on #21)
**Files:** `engine/interviewer.py`, `engine/prompts/*.md` (canned lines: `engine/prompts/canned.md`, from ENG-5)
1. `phrase()`, `answer()`, phase lines, and `say()` for Shreyas. Generate the intro when the session is
   created, so it plays instantly.
2. Leak guard on every outgoing text: a code fence; ≥ 2 lines that parse as Python statements; any normalized
   line with ≥ 0.6 token overlap with a non-trivial line of `reference_text`. On rejection, regenerate once at
   a lower level, then fall back to the rubric hint. Log every rejection.
3. `speak` follows `config.speak_replies`, except `PASTE` and `TIME_WARNING`, which are text only.

**Tests:** a leak guard corpus. It should catch fenced code, two-statement lines and a paraphrased reference
line, and let "What happens when the list is empty?" through.
**Done when:** PLAN §16 ENG-6: `asks-for-answer` never leaks in 20 attempts, and the intro plays within 1 s of
joining.
**As built:** no `phrase()` call. Nudges use the analyzer's draft, else the rubric hint, else the canned line, since a
second Spark call would add 2–6 s to each. The intro is a canned phase line (COD-2), so nothing is generated at
session creation. On a leak, `answer()` retries once asking for a Socratic question, then sends the canned
line. Live check: 20 of 20 safe against Muse Spark; intro in ~1 ms.

### COD-2 — Coding phases, timers, wrap-up
**P0 · Fri · needs ENG-1, ENG-6** · Read: PLAN §10.1
**Files:** `coding/session.py` (`CodingController`)
Phases intro → clarify → coding → wrap_up → ended, with the transitions in §10.1; time warnings at 50% and
80%; `remaining_s` in `session.state`; the 10-minute demo preset; wrap-up questions from the rubric.

### COD-4 — Integrity detectors
**P0 · Fri · needs ENG-2** · Read: PLAN §10.4
**Files:** `coding/integrity.py`
A paste of ≥ 40 chars or ≥ 2 lines, a bulk insert of ≥ 80 chars, and a hidden tab for ≥ 10 s each produce an
`IntegrityFlag` and an `integrity.flag` broadcast, and feed the `PASTE` rule. All wording is neutral: "pasted
32 lines at 06:14".

### ENG-8 — ReportBuilder
**P0 · Sat · needs ENG-5** · Read: PLAN §9.8, §7.5
**Files:** `engine/report.py`, `engine/prompts/report_system.md`
1. `Metrics` computed in code from the timeline.
2. 8–14 candidate moments selected in code.
3. `ReportDraft` from Wonder (`high`, 90 s) → Spark 1.3 → a metrics-only template.
4. Merge with `controller.report_extra()` into a `Report`, store it, set phase `reported`, broadcast
   `report.ready`. `GET /report` returns 202 while it's generating.

**Done when:** PLAN §16 ENG-8: a coding session and a defense session (both mock-free) each produce a valid
`Report` within 90 s, and the fallback works with Wonder disabled.
**As built** (PR "feat(engine): ReportBuilder for both modes (ENG-8)", stacked on #27): see PLAN §9.8. Code
replaces the scores it can measure and computes `overall`. The model wrapper gained `complete_json_with_model`
so the report records which model answered. Live: coding report 14.8 s and defense report 17.0 s on Wonder;
with Wonder disabled, Spark 1.3 in 14.9 s.

### P1 and P2 (only after the P0 path is solid)
- **For DEF-11 (Shreyas's Muse fix assistant, P1, PLAN §11.9):** an `assistant` role in `registry.py`
  (`muse-spark-1.3`, low, 20 s); a `chars_ai` counter in CodeState for edits applied through
  `programmatic()` after an accepted `assistant.apply`; independence scoring (§9.8) that accounts for the AI
  share; and review of the proposed contract additions with Shreyas.
- **COD-5 — Coding report extras** (P1 · Sun): final step statuses, approach, whether the complexity answer
  matched an acceptable approach. Step statuses and approach came with ENG-8 (from the latest analyses);
  grading the complexity answer is left.
- **COD-6 — Classifier, `PLAN_MISMATCH`, `CODED_BEFORE_PLAN`** (P1 · Sun · needs ENG-7). **Built Oct 28**: the voice
  classifier (spoken questions without Ask are answered), and plan memory (the policy and the analyzer keep the
  stated plan past the 90 s window, which fixed a false "what's your approach?"). Evals: coded-before-plan,
  states-plan-early, plan-mismatch, spoken-question, all 3/3.
- **VIS-1 — SAM sketch + proctor** (P2): only after both P0 paths pass the demo script twice in a row on the
  deployed build. Check V9 first.

---

## Day by day

| Day | Date | Build | End-of-day check |
|---|---|---|---|
| 0 | Mon Oct 26 | Setup, S-1 with Shreyas | Contracts PR open |
| 1 | Tue Oct 27 | ENG-3, ENG-1; S-1 merged | Smoke script passes live; a test client round-trips events |
| 2 | Wed Oct 28 | Capture lib (morning), ENG-2, COD-1, thin COD-3, thin ENG-4 path; agree on the hooks with Shreyas | **IC1** |
| 3 | Thu Oct 29 | ENG-4 finished, ENG-5, COD-3 finished, defense hooks built, start ENG-7 | Policy tests green |
| 4 | Fri Oct 30 | ENG-6, COD-2, COD-4, ENG-7, `codeAt` | **IC2**; latency measured |
| 5 | Sat Oct 31 | ENG-8 | Reports for both modes |
| 6 | Sun Nov 1 | COD-5, COD-6 (P1); integration fixes | **IC3** + cut-line review |
| 7 | Mon Nov 2 | Eval tuning, latency, demo-problem tuning with Sharvil; P2 only if green | Demo script passes twice |
| 8 | Tue Nov 3 | **Feature freeze 12 PM.** Bug fixes only; record demo takes | Takes recorded |
| 9 | Wed Nov 4 | Final video edit; **submit by 6 PM** | Submitted |

Wednesday is your heaviest day. Give the mechanical pieces (COD-1, the capture lib) to Muse Code and keep the
analyzer for yourself.

## What you show at each checkpoint

- **IC1 (Wed):** the coding room on LocalRunner. Typing triggers the analyzer, a nudge appears, and Run returns
  results.
- **IC2 (Fri):** Run on a warm Modal sandbox in under 2 s; voice transcripts appear in the room; the latency
  budget (PLAN §18) measured and written down. **Latency budget measured Oct 28** (PLAN §18): pause → nudge
  p50 5.0 s; voice transcripts appear in Likhil's room in a real browser. Modal waits on RUN-2.
- **IC3 (Sun):** a full coding session on the deployed build, including the report and replay; the defense fix
  stage runs on your engine.

## Your part of the demo (PLAN §20.1, 0:15–1:25)

The coding segment needs, on the demo problem: the skipped empty-input case reliably firing `MISSED_STEP`, the
notes panel showing that step go red and then green, a neutral paste note, then Run and Submit passing. Tune
the thresholds against Sharvil's demo problem on Mon Nov 2, and rehearse the exact script with his DATA-7
notes.

## Risks to watch

- **Noisy interventions:** keep the thresholds conservative and require persistence across 2 analyses. Passive
  mode is the safe default for skeptics.
- **Latency over budget (pause → message ≤ 6 s):** trim the dynamic prompt block (transcript window, run
  history) before lowering `reasoning_effort`. Check V2 (prompt caching).
- **Credits:** run evals in dev with `USE_CONTRIBUTOR_MODELS=1` and synthetic data only.

## PR checklist

- [ ] One work package, or a clearly named part of one; branch `feat/engine-…` or `feat/coding-…`
- [ ] Unit tests for the logic; fixtures updated if any message changed
- [ ] `make check` is green
- [ ] Prompts are in `prompts/*.md`; no model ids outside `registry.py`
- [ ] PLAN.md and this file updated if the plan changed; VERIFY results recorded in PLAN §23
