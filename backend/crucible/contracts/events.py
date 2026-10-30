"""Live events and timeline records (PLAN §7.2). Times `t` are int ms since the session started."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from crucible.contracts.common import Phase, Strict

# Size limits on what a browser can send (§8.2). Generous for real use; they stop a client from sending
# megabytes of text that would end up in model prompts and the timeline.
MAX_FILE_CHARS = 200_000  # one source file (projects are ≤ 6,000 lines in all, §11.1)
MAX_PATH_CHARS = 256
MAX_CHANGES_PER_EVENT = 100  # Monaco sends one change per cursor


class EditorChange(Strict):
    range_offset: int  # Monaco rangeOffset (offset in the model BEFORE this event)
    range_length: int  # Monaco rangeLength
    text: str = Field(max_length=MAX_FILE_CHARS)  # inserted text


class EditorEvent(Strict):
    t: int
    file: str = Field(default="solution.py", max_length=MAX_PATH_CHARS)
    version: int  # Monaco model versionId after the event
    kind: Literal["change", "paste", "undo", "redo", "focus", "blur", "hidden", "visible"]
    changes: list[EditorChange] = Field(default_factory=list, max_length=MAX_CHANGES_PER_EVENT)
    pasted_chars: int | None = None


class CodeSnapshot(Strict):
    t: int
    file: str = Field(max_length=MAX_PATH_CHARS)
    version: int
    code: str = Field(max_length=MAX_FILE_CHARS)


class TranscriptTurn(Strict):
    turn_id: str
    speaker: Literal["candidate", "interviewer"]
    text: str
    start_ms: int
    end_ms: int
    final: bool
    source: Literal["voice", "text"]


class CaseResult(Strict):  # not named Test*, so pytest won't try to collect it
    id: str
    visible: bool
    passed: bool
    input_repr: str | None  # hidden tests: None (never sent to the browser)
    expected_repr: str | None
    actual_repr: str | None
    error: str | None
    runtime_ms: int


class RunResult(Strict):
    run_id: str
    t: int
    kind: Literal["run", "submit"]
    passed: int
    total: int
    cases: list[CaseResult]
    stdout: str  # truncated to 4 KB
    stderr: str  # truncated to 4 KB
    timed_out: bool
    compile_error: str | None


class InterventionTrigger(StrEnum):
    IDLE = "idle"
    SILENT = "silent"
    RUN_FAILED = "run_failed"
    MISSED_STEP = "missed_step"
    BUG_SUSPECTED = "bug_suspected"
    PLAN_MISMATCH = "plan_mismatch"
    CODED_BEFORE_PLAN = "coded_before_plan"
    PASTE = "paste"
    ASKED = "asked"
    HINT_REQUESTED = "hint_requested"
    TIME_WARNING = "time_warning"
    PHASE = "phase"
    PRAISE = "praise"
    GRILL = "grill"
    # The interviewer's side of the conversation, not help (§9.5): the warm-up before the problem, a short reply
    # to what the candidate said, and a question that checks they understand what they wrote.
    WARMUP = "warmup"
    REPLY = "reply"
    PROBE = "probe"


class InterventionLevel(StrEnum):
    INFO = "info"
    NUDGE = "nudge"
    QUESTION = "question"
    HINT = "hint"
    CONCEPT = "concept"


class Intervention(Strict):
    id: str
    t: int
    trigger: InterventionTrigger
    level: InterventionLevel
    text: str
    step_id: str | None
    speak: bool
    suppressed: bool  # passive mode: decided but not shown; still in the report


class InterventionText(Strict):  # LLM output of Interviewer.phrase()
    text: str


class TurnLabel(Strict):  # LLM output of the voice classifier (COD-6, §9.7)
    label: Literal["question_to_interviewer", "thinking_aloud"]


class IntegrityFlag(Strict):
    id: str
    t: int
    kind: Literal["paste", "bulk_insert", "tab_hidden", "phone_in_frame", "extra_person"]
    detail: str  # neutral wording: "pasted 32 lines at 06:14"
    chars: int | None
    duration_ms: int | None


class PhaseChange(Strict):  # timeline payload for kind=phase
    from_phase: Phase
    to_phase: Phase
    reason: str


class SystemNote(Strict):  # timeline payload for kind=system: fallbacks, warnings, model errors
    level: Literal["info", "warning", "error"]
    message: str


ModelName = Literal["Muse Spark", "Muse Wonder", "Muse Spark Open", "Muse Voice", "SAM 3.1", "Muse Image"]


class ModelActivity(Strict):  # the "Under the hood" strip (docs/STORY.md): which model did what kind of task
    call_id: str  # pairs a call's "started" with how it ended
    t: int
    model_name: ModelName
    task: str  # a plain verb phrase ("reading your project"); never content, prompts or ids
    # fallback: a backup model answered; stopped: cancelled mid-call (e.g. the session moved on)
    status: Literal["started", "done", "fallback", "cached", "failed", "stopped"]
    latency_ms: int | None  # None while started


class TimelineKind(StrEnum):
    PHASE = "phase"
    EDITOR = "editor"
    SNAPSHOT = "snapshot"
    TRANSCRIPT = "transcript"
    RUN = "run"
    ANALYSIS = "analysis"
    INTERVENTION = "intervention"
    INTEGRITY = "integrity"
    AUDIT = "audit"
    CHAOS_METRIC = "chaos_metric"
    CHAOS_RUN = "chaos_run"
    GRILL = "grill"
    SAM_HIGHLIGHT = "sam_highlight"
    VERDICT = "verdict"
    SYSTEM = "system"
    MODEL_ACTIVITY = "model_activity"


class TimelineEvent(Strict):
    seq: int
    t: int
    kind: TimelineKind
    payload: dict[str, Any]  # validated against PAYLOAD_MODELS[kind] in engine/timeline.py
