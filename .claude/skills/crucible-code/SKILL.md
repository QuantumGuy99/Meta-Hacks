---
name: crucible-code
description: File templates and the layout every Crucible backend file follows (Defense, Runner, models, mock, contracts, tests, prompts). Use before creating any new Python module, contract model, model call, policy/decision function, runner/streaming code, prompt file or test in backend/, and when finishing a work package.
---

# Crucible code format

Templates for the shapes that recur in this codebase. Copy the closest one, then fill it in. The rules
behind them are in `backend/CLAUDE.md`; the architecture is in `PLAN.md`. Where a template calls a shared
API (`Timeline.append`, `hub.broadcast`, `llm.complete_json`), the signature comes from PLAN §9.2 / §9.1
/ §15.1. Once that code exists, read it and match the real signature instead.

## 1. Module layout

Every module, in this order:

```python
"""Grill: turn a candidate's answer into a code-computed score (PLAN §11.5)."""

from __future__ import annotations

import asyncio
import logging

from crucible.config import settings
from crucible.contracts.defense import Finding, GrillEval, GrillTurn

logger = logging.getLogger(__name__)

GRILL_EVAL_TIMEOUT_S = 10          # PLAN §21
SAM_BONUS = 1


class GrillError(Exception):
    """Raised when an answer can't be graded at all (not for fallbacks)."""


# --- public API ---------------------------------------------------------------

async def grade_answer(...) -> GrillTurn: ...

def score_answer(...) -> tuple[int, bool]: ...


# --- private helpers ------------------------------------------------------------

def _normalize(...) -> ...: ...
```

Imports: stdlib, blank line, third-party, blank line, `crucible.*` (ruff's isort enforces this). No
wildcard imports. No relative imports beyond the same package.

## 2. Contract model (`backend/crucible/contracts/*.py`)

```python
class ChaosMetric(Strict):
    run_id: str
    t_ms: int                    # ms since the attack started
    p99_ms: float
    errors: int
```

LLM-output model (used as `response_format`): no defaults, every field required, `X | None` for optional,
no tuples, no recursion, nesting ≤ 10.

```python
class GrillEval(Strict):         # LLM output
    points_hit: list[int]
    points_missed: list[int]
    needs_follow_up: bool
    feedback: str
```

After any change: add or update a fixture in `backend/tests/fixtures/`, run `make contracts`, and list
the change in the PR for SG + SS approval.

## 3. Model call with timeout and fallback

The model returns a judgement; nothing here decides anything.

```python
async def evaluate_answer(finding: Finding, transcript: str, *, session_id: str) -> GrillEval | None:
    """Ask the grill_eval model which expected points the answer hit. None if every model failed."""
    messages = [
        {"role": "system", "content": PROMPTS["grill_eval_system"]},
        {"role": "user", "content": _grill_context(finding, transcript)},
    ]
    try:
        return await llm.complete_json(
            "grill_eval", messages, GrillEval, timeout_s=GRILL_EVAL_TIMEOUT_S
        )  # walks the role's fallback chain itself (PLAN §15.1)
    except llm.AllModelsFailed as exc:
        logger.warning("grill_eval failed for %s: %s", finding.id, exc)
        await timeline.append(
            session_id, TimelineKind.SYSTEM,
            SystemNote(level="warning", message=f"Grill grading unavailable for {finding.id}; asked to answer in chat"),
        )
        return None
```

## 4. Decision function (pure: LLM suggests, code decides)

No I/O, no clock, no randomness: everything comes in as arguments.

```python
def score_answer(spec: GrillSpec, ev: GrillEval, *, sam_node_id: str | None,
                 finding_node_id: str | None) -> tuple[int, bool]:
    """Return (score 0–10, root_cause_hit). PLAN §11.5."""
    hits = {i for i in ev.points_hit if 0 <= i < len(spec.expected_points)}  # ignore invented indexes
    root_cause_hit = 0 in hits
    score = round(10 * len(hits) / len(spec.expected_points))
    if sam_node_id is not None and sam_node_id == finding_node_id:
        score = min(10, score + SAM_BONUS)
    return score, root_cause_hit
```

## 5. Streaming from the Runner

```python
@dataclass(slots=True)
class ChaosDone:
    invariant_ok: bool
    detail: str


async def stream_attack(runner: Runner, handle: ProjectHandle,
                        run_id: str) -> AsyncIterator[ChaosMetric | ChaosDone]:
    """Yield a ChaosMetric per metric line, then one ChaosDone for the template's final line."""
    argv = ["python", "/work/attack.py"]
    async for line in runner.stream_exec(handle, argv, timeout_s=CHAOS_RUN_TIMEOUT_S):
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("non-JSON line from attack: %.200s", line)
            continue
        if raw.get("done"):
            yield ChaosDone(invariant_ok=bool(raw["invariant_ok"]), detail=str(raw["detail"]))
            return
        try:
            yield ChaosMetric.model_validate({**raw, "run_id": run_id})
        except ValidationError as exc:
            logger.warning("bad metric line: %s", exc)
```

The caller appends each metric to the timeline, then broadcasts it (section 6). If the stream ends
without a `ChaosDone`, the run's verdict is `error`.

## 6. Timeline first, then broadcast

Every handler records the event before reacting or telling the browser.

```python
event = await timeline.append(session_id, TimelineKind.CHAOS_METRIC, metric)
await hub.broadcast(session_id, DefenseChaosMetric(type="defense.chaos.metric", metric=metric))
```

Never send the browser something the timeline doesn't have. Never send `Finding.explanation` before the
grill (use `FindingPublic`).

## 7. Mock switch

Only the explicit flag selects mock data, at the boundary, once:

```python
def make_runner() -> Runner:
    if settings.MOCK:
        return MockRunner(fixture="defense-bank-transfer")
    if settings.RUNNER == "local":
        return LocalRunner()   # refuses to start unless ALLOW_LOCAL_RUNNER=1
    return ModalRunner()
```

Never `except TimeoutError: return load_fixture(...)`.

## 8. Prompt file (`<package>/prompts/<name>.md`)

```markdown
# grill_eval_system
<!-- Used by defense/grill.py evaluate_answer. Output schema: GrillEval. -->

You grade a developer's spoken explanation of a production failure.

## Inputs
- The finding: title, category, file and lines, explanation (ground truth).
- Expected points, numbered from 0. Point 0 is the root cause.
- The candidate's transcript.

## Rules
- Mark a point hit only if the transcript states it in substance, not just a keyword.
- Never include code, a fix or the root cause in `feedback`.
- ...
```

The first heading is the key the loader uses. Keep the static part first and put per-request data in the
user message (prompt caching).

## 9. Test file (`backend/tests/<area>/test_<module>.py`)

```python
"""Tests for defense/grill.py scoring (PLAN §11.5)."""

import pytest

from crucible.defense.grill import score_answer
from tests.factories import grill_eval, grill_spec


def test_root_cause_required_even_with_full_bonus():
    score, root = score_answer(grill_spec(points=3), grill_eval(hit=[1, 2]),
                               sam_node_id="n1", finding_node_id="n1")
    assert root is False
    assert score == 8


def test_invented_point_indexes_are_ignored():
    score, _ = score_answer(grill_spec(points=3), grill_eval(hit=[0, 7]),
                            sam_node_id=None, finding_node_id="n1")
    assert score == 3


@pytest.mark.asyncio
async def test_evaluate_answer_returns_none_when_all_models_fail(fake_llm, timeline):
    fake_llm.fail("grill_eval")
    assert await evaluate_answer(...) is None
    assert timeline.kinds() == ["system"]
```

Shared builders go in `tests/factories.py`; fakes (`fake_llm`, `fake_runner`, `timeline`) in
`tests/conftest.py`. One behaviour per test.

## 10. Finishing a work package

1. Run the checks in `backend/CLAUDE.md` ("Before you say you're done").
2. If your area keeps a working-memory file (Defense + Runner: `docs/defense/MEMORY.md`), update its
   status row, handoff and session log, and release your claim. Add any
   ⚠️ VERIFY results to PLAN.md §23 as well.
3. Commit on `feat/<area>-<thing>` with a Conventional Commit (`feat(defense): grill scoring`), PR
   < 400 changed lines, naming the work package ID (e.g. "Closes DEF-5 (scoring part)").
