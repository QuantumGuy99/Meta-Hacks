"""Shared base model, enums and session models (PLAN §7.1)."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Strict(BaseModel):
    """Base for every contract: unknown fields are rejected, so drift fails loudly."""

    model_config = ConfigDict(extra="forbid")


class Mode(StrEnum):
    CODING = "coding"
    DEFENSE = "defense"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class FeedbackLevel(StrEnum):
    ACTIVE = "active"
    PASSIVE = "passive"


class Phase(StrEnum):
    SETUP = "setup"
    # coding
    INTRO = "intro"
    CLARIFY = "clarify"
    CODING = "coding"
    WRAP_UP = "wrap_up"
    # defense
    AUDIT = "audit"
    CHAOS = "chaos"
    GRILL = "grill"
    FIX = "fix"
    VERIFY = "verify"
    VERDICT = "verdict"
    # both
    ENDED = "ended"
    REPORTING = "reporting"
    REPORTED = "reported"
    FAILED = "failed"


class SessionConfig(Strict):
    mode: Mode
    feedback: FeedbackLevel = FeedbackLevel.ACTIVE
    voice: bool = True  # mic + Muse Voice Transcribe
    speak_replies: bool = True  # browser TTS for interviewer messages
    proctor: bool = False  # P2: SAM 3.1 webcam checks (opt-in)
    problem_slug: str | None = None  # coding: explicit problem
    difficulty: Difficulty | None = None  # coding: random problem at this difficulty
    topic: str | None = None
    project_id: str | None = None  # defense
    time_limit_s: int | None = None  # default from problem/difficulty


class Session(Strict):
    id: str
    config: SessionConfig
    phase: Phase
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    time_limit_s: int
    problem_slug: str | None
    project_id: str | None


# --- REST envelopes (PLAN §8.1) ----------------------------------------------------------------------------


class Health(Strict):  # GET /api/health
    ok: bool
    version: str
    mock: bool


class ApiErrorBody(Strict):
    code: str
    message: str


class ApiError(Strict):  # every non-2xx REST response
    error: ApiErrorBody


class ReportPending(Strict):  # GET /api/sessions/{id}/report while it's still generating (HTTP 202)
    status: Literal["generating"]
