"""What the "Under the hood" strip shows for each model call (docs/STORY.md): plain task labels, display names.

Labels say which model did what kind of task, never the content, so the strip can't leak anything.
"""

from crucible.contracts.events import ModelActivity, ModelName
from crucible.models.llm import CallActivity

TASKS: dict[str, str] = {
    "analyzer": "watching your code",
    "interviewer": "answering your question",
    "classifier": "listening for questions",
    "complexity": "checking your complexity answer",
    "conversation": "talking with you",
    "grill_eval": "grading your answer",
    "grill_check": "double-checking your answer",
    "audit": "reading your project",
    "report": "writing your report",
    "attacker": "writing an attack",
    "vision": "finding what you circled",
    "replay": "replaying the race step by step",
    "drafter": "drafting problems",
}
VOICE: ModelName = "Muse Voice"
LISTENING = "listening"
TRANSCRIBING = "transcribing"


def to_activity(call: CallActivity, t: int) -> ModelActivity:
    return ModelActivity(
        call_id=call.call_id,
        t=t,
        model_name=display_name(call),
        task=TASKS.get(call.role, "working"),
        status=call.status,
        latency_ms=call.latency_ms,
    )


def display_name(call: CallActivity) -> ModelName:
    """The chip a call lights: never a raw model id (STORY.md)."""
    if call.provider == "baseten":
        return "Muse Spark Open"
    return "Muse Wonder" if call.model and "wonder" in call.model else "Muse Spark"
