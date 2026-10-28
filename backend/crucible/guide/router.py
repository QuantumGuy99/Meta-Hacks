"""POST /api/guide: the "Ask Crucible" helper (#25). Rate-limited per client; rule-based without a model."""

from __future__ import annotations

from typing import TypeVar

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from crucible.contracts.guide import GuideAsk, GuideReply
from crucible.guide.assistant import GuideModelUnavailable, ask, fallback_reply
from crucible.models import llm as llm_mod
from crucible.quota import DailyQuota, client_ip

T = TypeVar("T", bound=BaseModel)

router = APIRouter(prefix="/api", tags=["guide"])


class WrapperGuideModel:
    """The shared model wrapper, with its failures turned into GuideModelUnavailable."""

    def __init__(self, model: llm_mod.LLM) -> None:
        self._model = model

    async def complete_json(self, role: str, messages: list[dict], schema: type[T], *, timeout_s: float) -> T:
        try:
            return await self._model.complete_json(role, messages, schema, timeout_s=timeout_s)
        except llm_mod.AllModelsFailed as exc:
            raise GuideModelUnavailable(str(exc)) from exc


@router.post("/guide", response_model=GuideReply)
async def guide(body: GuideAsk, request: Request) -> GuideReply:
    s = request.app.state.settings
    quota: DailyQuota = request.app.state.guide_quota
    if not quota.take(client_ip(request, behind_proxy=s.BEHIND_PROXY)):
        raise HTTPException(429, "You've asked the guide a lot today. Try again tomorrow.")
    if s.MOCK:
        return fallback_reply(body)
    try:
        model = WrapperGuideModel(llm_mod.default_llm())
    except llm_mod.LLMNotConfigured:
        model = None
    samples = set(getattr(request.app.state, "samples", {}))
    return await ask(body, model, samples)
