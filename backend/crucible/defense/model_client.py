"""ModelClient for Defense on top of the shared model wrapper (`models/llm.py`, ENG-3).

Defense code talks to the small `ModelClient` port (defense/ports.py) so it can run with fakes in tests.
This adapter maps the wrapper's `AllModelsFailed` (and "not configured") to `ModelUnavailable`, which is
the signal every Defense stage uses to take its non-model fallback.
"""

from __future__ import annotations

from typing import Any

from crucible.defense.ports import ModelUnavailable, T
from crucible.models import llm as llm_mod


class WrapperModelClient:
    def __init__(self, llm: Any | None = None, *, session_id: str | None = None) -> None:
        """`llm`: a configured `models.llm.LLM`; None uses the process-wide one (main.py configures it).
        `session_id` routes each call's activity to that session's "Under the hood" strip."""
        self._llm = llm
        self._session_id = session_id

    def for_session(self, session_id: str) -> WrapperModelClient:
        return WrapperModelClient(self._llm, session_id=session_id)

    async def complete_json(self, role: str, messages: list[dict], schema: type[T], *, timeout_s: float) -> T:
        try:
            model = self._llm or llm_mod.default_llm()
        except llm_mod.LLMNotConfigured as exc:
            raise ModelUnavailable("model wrapper not configured") from exc
        try:
            return await model.complete_json(
                role, messages, schema, timeout_s=timeout_s, session_id=self._session_id
            )
        except llm_mod.AllModelsFailed as exc:
            raise ModelUnavailable(str(exc)) from exc
