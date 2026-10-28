"""Is a spoken turn a question for the interviewer, or thinking aloud? (COD-6, PLAN §9.7)

Typed chat is classified in code (`policy.is_question`) and a turn spoken while Ask is held is a question already;
this is for the rest of what the candidate says out loud. One cheap Spark call per turn, off the critical path;
any failure counts as thinking aloud, which never interrupts the candidate.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from crucible.contracts.events import TurnLabel
from crucible.engine.prompts import PROMPTS

if TYPE_CHECKING:
    from crucible.engine.analyzer import StructuredModel

logger = logging.getLogger(__name__)

CLASSIFY_DEADLINE_S = 4  # the registry's 3 s classifier timeout, plus a little
CONTEXT_TURNS = 3  # the candidate's turns just before, so "and the empty case?" reads in context


async def is_question_for_interviewer(
    model: StructuredModel, text: str, earlier: Sequence[str], *, session_id: str | None = None
) -> bool | None:
    """True if the candidate asked the interviewer something, False for thinking aloud, None if the call failed
    (the caller treats that as thinking aloud and says so on the timeline)."""
    user = json.dumps({"earlier_turns": list(earlier)[-CONTEXT_TURNS:], "latest_turn": text})
    messages = [{"role": "system", "content": PROMPTS["classifier"]}, {"role": "user", "content": user}]
    try:
        async with asyncio.timeout(CLASSIFY_DEADLINE_S):
            result = await model.complete_json("classifier", messages, TurnLabel, session_id=session_id)
    except Exception:  # task boundary: a missed question is better than interrupting someone thinking
        logger.warning("voice classifier failed in %s", session_id, exc_info=True)
        return None
    return result.label == "question_to_interviewer"
