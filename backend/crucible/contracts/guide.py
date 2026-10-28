"""The "Ask Crucible" guide: a Muse helper on every page that explains the app and runs a few app commands
(#25). It never sees hidden tests, rubrics, findings or config, and code decides every action."""

from typing import Literal

from pydantic import Field

from crucible.contracts.common import Difficulty, Strict

MAX_GUIDE_QUESTION_CHARS = 1_000
MAX_GUIDE_HISTORY = 6

GuidePage = Literal["home", "coding_setup", "defense_picker", "room", "report", "other"]
GuideTarget = Literal["home", "coding", "defense", "report"]


class GuideAction(Strict):  # what the browser does after the reply; the model suggests, code decides
    kind: Literal["none", "open_page", "start_coding", "start_defense"]
    page: GuideTarget | None  # open_page only
    difficulty: Difficulty | None  # start_coding only
    project_id: str | None  # start_defense only: a sample id from GET /api/defense/samples


class GuideDraft(Strict):  # LLM output (Muse Spark)
    reply: str
    action: GuideAction


class GuideTurn(Strict):
    role: Literal["user", "guide"]
    text: str = Field(max_length=MAX_GUIDE_QUESTION_CHARS)


class GuideAsk(Strict):  # POST /api/guide
    question: str = Field(min_length=1, max_length=MAX_GUIDE_QUESTION_CHARS)
    page: GuidePage
    in_session: bool  # true inside a live interview: the guide then only explains the screen, never acts
    history: list[GuideTurn] = Field(default_factory=list, max_length=MAX_GUIDE_HISTORY)


class GuideReply(Strict):  # the response
    reply: str
    action: GuideAction
    source: Literal["model", "fallback"]  # fallback: no model answered; a rule-based reply
