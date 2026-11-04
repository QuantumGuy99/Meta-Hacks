"""Replay the race step by step (DEF-14, PLAN §11.11).

After a race finding broke under load, the sandbox replays the same validated attack with exactly two requests,
A and B, started together, until the invariant breaks (a few tries at most). Muse Wonder then narrates the
interleaving that lost the update as steps in two lanes. Code decides what is shown: only a replay that
reproduced the loss, only well-formed steps, and only after the finding's grill is final (it explains the cause).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from crucible.contracts.defense import (
    AttackFunctions,
    Finding,
    Project,
    RaceReplay,
    ReplayLane,
    ReplayNarrative,
    ReplayStep,
)
from crucible.defense.attack_writer import render_attack
from crucible.defense.chaos import ChaosDone, parse_line
from crucible.defense.grill import looks_like_code
from crucible.defense.ports import EventSink, ModelClient, ModelUnavailable, note
from crucible.defense.prompts import PROMPTS
from crucible.runner.base import Runner, RunnerError
from crucible.runner.harness import REPLAY_RUNNER

logger = logging.getLogger(__name__)

REPLAY_TRIES = 5
REPLAY_EXEC_TIMEOUT_S = 30
NARRATE_TIMEOUT_S = 60
MIN_STEPS, MAX_STEPS = 4, 12
MAX_ACTION_CHARS = 140
_RUNNER_MARK = "async def _main() -> None:"


@dataclass(slots=True)
class Reproduction:
    reproduced: bool
    detail: str
    attempts: int
    lanes: list[ReplayLane] = field(default_factory=list)


def render_replay(fn: AttackFunctions, *, port: int, tries: int = REPLAY_TRIES) -> str:
    """The attack template with its load runner swapped for the two-request one: same bodies, same guard."""
    load = render_attack(fn, port=port, concurrency=2, duration_s=1)
    script = load[: load.index(_RUNNER_MARK)] + REPLAY_RUNNER.replace("__TRIES__", str(int(tries)))
    compile(script, "replay.py", "exec")
    return script


async def reproduce(
    runner: Runner, project: Project, files: dict[str, str], fn: AttackFunctions
) -> Reproduction:
    """Two requests at once against the original code, up to REPLAY_TRIES times."""
    lanes: list[ReplayLane] = []
    attempts = 0
    done: ChaosDone | None = None
    h = await runner.start_project(project, files)
    try:
        await runner.put_file(h, "replay.py", render_replay(fn, port=h.port))
        async for line in runner.stream_exec(h, ["python", "replay.py"], timeout_s=REPLAY_EXEC_TIMEOUT_S):
            if line.startswith('{"lanes"'):
                raw = json.loads(line)
                lanes = [ReplayLane.model_validate(x) for x in raw["lanes"]]
                attempts = int(raw["attempts"])
            elif isinstance(item := parse_line(line, "replay"), ChaosDone):
                done = item
    finally:
        await runner.stop_project(h)
    if done is None:
        return Reproduction(reproduced=False, detail="the replay printed no result", attempts=attempts)
    return Reproduction(reproduced=not done.invariant_ok, detail=done.detail, attempts=attempts, lanes=lanes)


async def narrate(
    finding: Finding, files: dict[str, str], rep: Reproduction, llm: ModelClient, sink: EventSink
) -> ReplayNarrative | None:
    try:
        return await llm.complete_json(
            "replay", _messages(finding, files, rep), ReplayNarrative, timeout_s=NARRATE_TIMEOUT_S
        )
    except ModelUnavailable as exc:
        await note(sink, "warning", f"Race replay narration unavailable for {finding.id}: {exc}")
        return None


def check_steps(steps: list[ReplayStep], file_lines: int) -> list[ReplayStep] | None:
    """Code decides: both lanes appear, a sane number of steps, plain words (no code), lines in the file.
    Anything else isn't shown at all, rather than shown half-right."""
    clean = [
        s.model_copy(
            update={
                "action": s.action.strip()[:MAX_ACTION_CHARS],
                "line": s.line if s.line is not None and 1 <= s.line <= file_lines else None,
            }
        )
        for s in steps
        if s.action.strip() and not looks_like_code(s.action)
    ]
    if not MIN_STEPS <= len(clean) <= MAX_STEPS or {s.lane for s in clean} != {"A", "B"}:
        return None
    return clean


async def race_replay(
    finding: Finding,
    project: Project,
    files: dict[str, str],
    fn: AttackFunctions,
    runner: Runner,
    llm: ModelClient,
    sink: EventSink,
) -> RaceReplay | None:
    """The replay for one broken race finding, or None when it can't be shown honestly."""
    try:
        rep = await reproduce(runner, project, files, fn)
    except RunnerError as exc:
        await note(sink, "warning", f"Race replay for {finding.id} couldn't run: {exc}")
        return None
    if not rep.reproduced:
        await note(
            sink, "info", f"Two requests didn't reproduce {finding.id} in {rep.attempts} tries; no replay."
        )
        return None
    narration = await narrate(finding, files, rep, llm, sink)
    steps = check_steps(narration.steps, files[finding.file].count("\n") + 1) if narration else None
    if steps is None:
        if narration is not None:
            await note(sink, "warning", f"Race replay steps for {finding.id} were malformed; not shown.")
        return None
    return RaceReplay(
        finding_id=finding.id,
        file=finding.file,
        lanes=rep.lanes,
        steps=steps,
        detail=rep.detail,
        attempts=rep.attempts,
    )


def _messages(finding: Finding, files: dict[str, str], rep: Reproduction) -> list[dict]:
    user = {
        "finding": finding.model_dump(include={"title", "file", "line_start", "line_end", "explanation"}),
        "file": files.get(finding.file, ""),
        "replayed": {
            "requests": [lane.model_dump() for lane in rep.lanes],
            "result": rep.detail,
        },
    }
    return [
        {"role": "system", "content": PROMPTS["replay_system"]},
        {"role": "user", "content": json.dumps(user)},
    ]
