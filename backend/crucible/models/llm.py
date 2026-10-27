"""The one way the product calls a model: structured or text output, retries and fallbacks (PLAN §15.1)."""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

import openai
from openai import AsyncOpenAI
from openai.types import CompletionUsage
from pydantic import BaseModel, ValidationError

from crucible.models.registry import (
    CONTRIBUTOR_MAX_EFFORT,
    CONTRIBUTOR_MODELS,
    PRICES,
    ROLES,
    Effort,
    ModelRole,
    ModelTarget,
    Provider,
)

logger = logging.getLogger(__name__)

META_BASE_URL = "https://api.meta.ai/v1"
RETRY_BACKOFF_S = 1.0  # jittered to 0.5 to 1.5 s

# 429, 5xx and dropped connections get one more try on the same model; any other error moves down the chain.
_RETRYABLE = (openai.RateLimitError, openai.InternalServerError, openai.APIConnectionError)
_CONTRIBUTOR_IDS = frozenset(CONTRIBUTOR_MODELS.values())

Messages = Sequence[Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class LLMSettings:
    """What the wrapper needs from config. `crucible.config.settings` fills it once the S-0 scaffold lands."""

    api_key: str = field(repr=False)
    base_url: str = META_BASE_URL
    use_contributor_models: bool = False
    role_models: Mapping[ModelRole, str] = field(default_factory=dict)  # MODEL_ANALYZER etc.: primary only
    baseten_base_url: str | None = None
    baseten_api_key: str | None = field(default=None, repr=False)
    baseten_model: str | None = None  # SPARK_OPEN_MODEL; None keeps the registry's id


@dataclass(frozen=True, slots=True)
class CallRecord:
    """One call to one model. Passed to `on_call`, which ENG-1 turns into a `system` timeline note."""

    role: ModelRole
    provider: Provider
    model: str
    effort: Effort | None
    latency_ms: int
    error: str | None = None  # None: the call succeeded
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float | None = None
    session_id: str | None = None


OnCall = Callable[[CallRecord], Awaitable[None]]
type _Call[R] = Callable[[AsyncOpenAI, ModelTarget], Awaitable[tuple[R, CompletionUsage | None]]]


class AllModelsFailed(Exception):
    """Every model in the role's chain failed. The caller runs its non-model fallback (PLAN §15.1)."""

    def __init__(self, role: ModelRole, errors: list[str]) -> None:
        super().__init__(f"{role}: every model failed ({'; '.join(errors)})")
        self.role = role
        self.errors = errors


class LLMNotConfigured(RuntimeError):
    """A module-level call came before `configure()`."""


class LLM:
    """The model clients plus the retry and fallback loop. Tests inject fake clients, sleep and rng."""

    def __init__(
        self,
        settings: LLMSettings,
        *,
        clients: Mapping[Provider, AsyncOpenAI] | None = None,
        on_call: OnCall | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self._settings = settings
        self._clients = dict(clients) if clients is not None else _build_clients(settings)
        self._provider_models: dict[Provider, str] = {}
        if settings.baseten_model:
            self._provider_models["baseten"] = settings.baseten_model
        self._on_call = on_call
        self._sleep = sleep
        self._rng = rng

    def register_provider(self, provider: Provider, client: AsyncOpenAI, model: str) -> None:
        """Plug in a partner client (Glimmer, from `models/glimmer.py`) for every role that lists it."""
        self._clients[provider] = client
        self._provider_models[provider] = model

    async def complete_json[T: BaseModel](
        self,
        role: ModelRole,
        messages: Messages,
        schema: type[T],
        *,
        effort: Effort | None = None,
        timeout_s: float | None = None,
        images: Sequence[str] = (),
        session_id: str | None = None,
    ) -> T:
        """Structured output parsed into `schema`. `timeout_s` (default: the role's) applies per attempt."""
        result, _model = await self.complete_json_with_model(
            role, messages, schema, effort=effort, timeout_s=timeout_s, images=images, session_id=session_id
        )
        return result

    async def complete_json_with_model[T: BaseModel](
        self,
        role: ModelRole,
        messages: Messages,
        schema: type[T],
        *,
        effort: Effort | None = None,
        timeout_s: float | None = None,
        images: Sequence[str] = (),
        session_id: str | None = None,
    ) -> tuple[T, str]:
        """`complete_json`, plus the id of the model that answered (the report records it, PLAN §7.5)."""
        request_messages = _with_images(messages, images)

        async def call(client: AsyncOpenAI, target: ModelTarget) -> tuple[T, CompletionUsage | None]:
            completion = await client.beta.chat.completions.parse(
                response_format=schema, **_request(target, request_messages)
            )
            message = completion.choices[0].message
            if message.parsed is None:
                raise _NoOutput("refused" if message.refusal else "no parsed output")
            return message.parsed, completion.usage

        return await self._run(role, call, effort=effort, timeout_s=timeout_s, session_id=session_id)

    async def complete_text(
        self,
        role: ModelRole,
        messages: Messages,
        *,
        effort: Effort | None = None,
        timeout_s: float | None = None,
        session_id: str | None = None,
    ) -> str:
        request_messages = [dict(m) for m in messages]

        async def call(client: AsyncOpenAI, target: ModelTarget) -> tuple[str, CompletionUsage | None]:
            completion = await client.chat.completions.create(**_request(target, request_messages))
            content = completion.choices[0].message.content
            if not content:
                raise _NoOutput("empty reply")
            return content, completion.usage

        text, _model = await self._run(role, call, effort=effort, timeout_s=timeout_s, session_id=session_id)
        return text

    async def _run[R](
        self,
        role: ModelRole,
        call: _Call[R],
        *,
        effort: Effort | None,
        timeout_s: float | None,
        session_id: str | None,
    ) -> tuple[R, str]:
        """The first answer down the role's chain, with the id of the model that gave it."""
        budget_s = timeout_s if timeout_s is not None else ROLES[role].timeout_s
        errors: list[str] = []
        for target in self._chain(role, effort):
            client = self._clients.get(target.provider)
            if client is None or target.model is None:
                logger.debug("llm %s: skipping %s, not configured", role, target.provider)
                errors.append(f"{target.provider}: not configured")
                continue
            try:
                result = await self._attempt(role, client, target, call, budget_s, session_id)
            except _Failed as exc:
                errors.append(f"{target.model}: {exc}")
            else:
                return result, target.model
        raise AllModelsFailed(role, errors)

    def _chain(self, role: ModelRole, effort: Effort | None) -> list[ModelTarget]:
        """The role's targets with model overrides, the per-call effort and the contributor switch applied."""
        chain: list[ModelTarget] = []
        for index, target in enumerate(ROLES[role].chain):
            model = self._provider_models.get(target.provider, target.model)
            if index == 0:
                model = self._settings.role_models.get(role, model)
            resolved = replace(target, model=model)
            # A per-call effort only replaces efforts the registry sends; Baseten and Glimmer never get one.
            if effort is not None and target.effort is not None:
                resolved = replace(resolved, effort=effort)
            if self._settings.use_contributor_models and resolved.provider == "meta":
                resolved = replace(resolved, model=CONTRIBUTOR_MODELS.get(resolved.model, resolved.model))
            if resolved.model in _CONTRIBUTOR_IDS and resolved.effort == "max":
                resolved = replace(resolved, effort=CONTRIBUTOR_MAX_EFFORT)
            if resolved not in chain:  # an override can turn a fallback into a repeat of the primary
                chain.append(resolved)
        return chain

    async def _attempt[R](
        self,
        role: ModelRole,
        client: AsyncOpenAI,
        target: ModelTarget,
        call: _Call[R],
        timeout_s: float,
        session_id: str | None,
    ) -> R:
        """Call one model, with one jittered retry on 429/5xx. Raises `_Failed` to move down the chain."""
        try:
            return await self._once(role, client, target, call, timeout_s, session_id)
        except _Failed as exc:
            if not exc.retryable:
                raise
        await self._sleep(RETRY_BACKOFF_S * (0.5 + self._rng()))
        return await self._once(role, client, target, call, timeout_s, session_id)

    async def _once[R](
        self,
        role: ModelRole,
        client: AsyncOpenAI,
        target: ModelTarget,
        call: _Call[R],
        timeout_s: float,
        session_id: str | None,
    ) -> R:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(timeout_s):
                result, usage = await call(client, target)
        except TimeoutError as exc:
            # A model that just timed out will likely time out again, so it isn't retried.
            failure, cause = _Failed(f"timeout after {timeout_s:g}s", retryable=False), exc
        except (openai.OpenAIError, ValidationError, _NoOutput) as exc:
            failure, cause = _Failed(_describe(exc), retryable=isinstance(exc, _RETRYABLE)), exc
        else:
            await self._record(role, target, started, session_id, usage=usage)
            return result
        await self._record(role, target, started, session_id, error=str(failure))
        raise failure from cause

    async def _record(
        self,
        role: ModelRole,
        target: ModelTarget,
        started: float,
        session_id: str | None,
        *,
        usage: CompletionUsage | None = None,
        error: str | None = None,
    ) -> None:
        model = target.model or target.provider
        prompt, completion, cached = _tokens(usage)
        record = CallRecord(
            role=role,
            provider=target.provider,
            model=model,
            effort=target.effort,
            latency_ms=round((time.perf_counter() - started) * 1000),
            error=error,
            prompt_tokens=prompt,
            completion_tokens=completion,
            cached_tokens=cached,
            cost_usd=None if error else estimate_cost_usd(model, prompt, completion, cached),
            session_id=session_id,
        )
        _log(record)
        if self._on_call is not None:
            await self._on_call(record)


def estimate_cost_usd(
    model: str, prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0
) -> float | None:
    """List-price estimate (PLAN §15.3). None for models without a known price (Spark Open, Glimmer)."""
    price = PRICES.get(model)
    if price is None:
        return None
    cached_price = price.input_per_m if price.cached_input_per_m is None else price.cached_input_per_m
    uncached = prompt_tokens - cached_tokens
    total = (
        uncached * price.input_per_m + cached_tokens * cached_price + completion_tokens * price.output_per_m
    )
    return total / 1_000_000


_default: LLM | None = None


def configure(settings: LLMSettings, *, on_call: OnCall | None = None) -> LLM:
    """Build the process-wide wrapper behind `complete_json`/`complete_text`. Call once at startup."""
    global _default
    _default = LLM(settings, on_call=on_call)
    return _default


def default_llm() -> LLM:
    if _default is None:
        raise LLMNotConfigured("call crucible.models.llm.configure(settings) at startup first")
    return _default


async def complete_json[T: BaseModel](
    role: ModelRole,
    messages: Messages,
    schema: type[T],
    *,
    effort: Effort | None = None,
    timeout_s: float | None = None,
    images: Sequence[str] = (),
    session_id: str | None = None,
) -> T:
    """Structured output for `role`, walking its fallback chain. Raises `AllModelsFailed` (PLAN §15.1)."""
    return await default_llm().complete_json(
        role, messages, schema, effort=effort, timeout_s=timeout_s, images=images, session_id=session_id
    )


async def complete_text(
    role: ModelRole,
    messages: Messages,
    *,
    effort: Effort | None = None,
    timeout_s: float | None = None,
    session_id: str | None = None,
) -> str:
    """Plain text for `role`, walking its fallback chain. Raises `AllModelsFailed` (PLAN §15.1)."""
    return await default_llm().complete_text(
        role, messages, effort=effort, timeout_s=timeout_s, session_id=session_id
    )


class _NoOutput(Exception):
    """The model answered with nothing usable: a refusal or an empty reply."""


class _Failed(Exception):
    """One call to one model failed; `retryable` says whether that model gets one more try."""

    def __init__(self, reason: str, *, retryable: bool) -> None:
        super().__init__(reason)
        self.retryable = retryable


def _build_clients(settings: LLMSettings) -> dict[Provider, AsyncOpenAI]:
    # max_retries=0: this module owns retries, so the SDK's own can't stack up under the role timeout.
    clients: dict[Provider, AsyncOpenAI] = {
        "meta": AsyncOpenAI(base_url=settings.base_url, api_key=settings.api_key, max_retries=0)
    }
    if settings.baseten_base_url and settings.baseten_api_key:
        clients["baseten"] = AsyncOpenAI(
            base_url=settings.baseten_base_url, api_key=settings.baseten_api_key, max_retries=0
        )
    return clients


def _request(target: ModelTarget, messages: list[dict[str, Any]]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"model": target.model, "messages": messages}
    if target.effort is not None:
        kwargs["reasoning_effort"] = target.effort
    return kwargs


def _with_images(messages: Messages, images: Sequence[str]) -> list[dict[str, Any]]:
    """Attach image URLs (https or data:) to the last user message as `image_url` parts."""
    out = [dict(m) for m in messages]
    if not images:
        return out
    parts = [{"type": "image_url", "image_url": {"url": url}} for url in images]
    for message in reversed(out):
        if message.get("role") == "user":
            content = message.get("content") or []
            text = [{"type": "text", "text": content}] if isinstance(content, str) else list(content)
            message["content"] = text + parts
            return out
    out.append({"role": "user", "content": parts})
    return out


def _tokens(usage: CompletionUsage | None) -> tuple[int, int, int]:
    """(prompt, completion, cached) tokens; zeros when the provider sends no usage block."""
    if usage is None:
        return 0, 0, 0
    details = usage.prompt_tokens_details
    cached = (details.cached_tokens or 0) if details is not None else 0
    return usage.prompt_tokens or 0, usage.completion_tokens or 0, cached


def _describe(exc: Exception) -> str:
    """A short reason for logs and `AllModelsFailed`; never the prompt or the reply."""
    if isinstance(exc, openai.APIStatusError):
        return f"HTTP {exc.status_code}"
    if isinstance(exc, _NoOutput):
        return str(exc)
    return type(exc).__name__


def _log(record: CallRecord) -> None:
    if record.error is not None:
        logger.warning(
            "llm failed role=%s model=%s latency_ms=%d error=%s session=%s",
            record.role,
            record.model,
            record.latency_ms,
            record.error,
            record.session_id,
        )
        return
    cost = "n/a" if record.cost_usd is None else f"{record.cost_usd:.5f}"
    logger.info(
        "llm ok role=%s model=%s effort=%s latency_ms=%d tokens_in=%d tokens_out=%d cached=%d cost_usd=%s "
        "session=%s",
        record.role,
        record.model,
        record.effort,
        record.latency_ms,
        record.prompt_tokens,
        record.completion_tokens,
        record.cached_tokens,
        cost,
        record.session_id,
    )
