"""Model wrapper tests with fake clients: retries, fallbacks, the contributor switch and cost (ENG-3)."""

import asyncio
from types import SimpleNamespace as NS
from typing import Any, get_args

import openai
import pytest
from openai.types.completion_usage import CompletionUsage, PromptTokensDetails
from pydantic import BaseModel, ValidationError

from crucible.models import llm
from crucible.models.llm import LLM, AllModelsFailed, CallRecord, LLMSettings, estimate_cost_usd
from crucible.models.registry import ROLES, SPARK, SPARK_CONTRIBUTOR, SPARK_OPEN, WONDER, ModelRole

HANG = object()  # outcome: never answer, so the timeout fires
REFUSED = object()  # outcome: a parse reply with a refusal instead of output
MESSAGES = [{"role": "user", "content": "hi"}]
USAGE = CompletionUsage(
    prompt_tokens=1000,
    completion_tokens=200,
    total_tokens=1200,
    prompt_tokens_details=PromptTokensDetails(cached_tokens=400),
)


class Verdict(BaseModel):
    ok: bool


OK = Verdict(ok=True)


def http_error(cls: type[openai.APIStatusError], code: int) -> openai.APIStatusError:
    return cls(f"HTTP {code}", response=NS(status_code=code, headers={}, request=None), body=None)


def invalid_output() -> ValidationError:
    return ValidationError.from_exception_data("Verdict", [{"type": "missing", "loc": ("ok",), "input": {}}])


class FakeClient:
    """Stands in for AsyncOpenAI. Each model's outcomes are used in order: a reply, an exception or HANG."""

    def __init__(self, outcomes: dict[str, list[Any]]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, Any]] = []
        self.beta = NS(chat=NS(completions=NS(parse=self._parse)))
        self.chat = NS(completions=NS(create=self._create))

    async def _next(self, kwargs: dict[str, Any]) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes[kwargs["model"]].pop(0)
        if outcome is HANG:
            await asyncio.sleep(3600)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def _parse(self, *, response_format: type[BaseModel], **kwargs: Any) -> NS:
        reply = await self._next(kwargs)
        message = NS(parsed=None, refusal="no") if reply is REFUSED else NS(parsed=reply, refusal=None)
        return NS(choices=[NS(message=message)], usage=USAGE)

    async def _create(self, **kwargs: Any) -> NS:
        reply = await self._next(kwargs)
        return NS(choices=[NS(message=NS(content=reply))], usage=USAGE)


def make_llm(clients: dict[str, FakeClient], **settings: Any) -> tuple[LLM, list[float], list[CallRecord]]:
    sleeps: list[float] = []
    records: list[CallRecord] = []

    async def sleep(delay_s: float) -> None:
        sleeps.append(delay_s)

    async def on_call(record: CallRecord) -> None:
        records.append(record)

    wrapper = LLM(
        LLMSettings(api_key="test", **settings),
        clients=clients,
        on_call=on_call,
        sleep=sleep,
        rng=lambda: 0.5,
    )
    return wrapper, sleeps, records


def sent(client: FakeClient) -> list[tuple[str, str | None]]:
    return [(call["model"], call.get("reasoning_effort")) for call in client.calls]


@pytest.mark.asyncio
async def test_retries_once_on_429_then_succeeds() -> None:
    meta = FakeClient({SPARK: [http_error(openai.RateLimitError, 429), OK]})
    wrapper, sleeps, _ = make_llm({"meta": meta})

    assert await wrapper.complete_json("analyzer", MESSAGES, Verdict) == OK
    assert sent(meta) == [(SPARK, "minimal"), (SPARK, "minimal")]
    assert sleeps == [1.0]  # RETRY_BACKOFF_S * (0.5 + rng)


@pytest.mark.asyncio
async def test_falls_back_when_the_retry_also_fails() -> None:
    errors = [http_error(openai.InternalServerError, 500), http_error(openai.InternalServerError, 503)]
    meta = FakeClient({WONDER: errors, SPARK: [OK]})
    wrapper, sleeps, records = make_llm({"meta": meta})

    assert await wrapper.complete_json("audit", MESSAGES, Verdict) == OK
    assert sent(meta) == [(WONDER, "xhigh"), (WONDER, "xhigh"), (SPARK, "high")]
    assert len(sleeps) == 1
    assert [r.error for r in records] == ["HTTP 500", "HTTP 503", None]


@pytest.mark.asyncio
async def test_timeout_falls_back_without_retrying() -> None:
    meta = FakeClient({WONDER: [HANG], SPARK: [OK]})
    wrapper, sleeps, records = make_llm({"meta": meta})

    assert await wrapper.complete_json("audit", MESSAGES, Verdict, timeout_s=0.01) == OK
    assert sent(meta) == [(WONDER, "xhigh"), (SPARK, "high")]
    assert sleeps == []
    assert records[0].error == "timeout after 0.01s"


@pytest.mark.asyncio
async def test_with_model_names_the_model_that_answered() -> None:
    meta = FakeClient({WONDER: [OK, http_error(openai.BadRequestError, 400)], SPARK: [OK]})
    wrapper, _, _ = make_llm({"meta": meta})

    assert await wrapper.complete_json_with_model("report", MESSAGES, Verdict) == (OK, WONDER)
    assert await wrapper.complete_json_with_model("report", MESSAGES, Verdict) == (OK, SPARK)  # the fallback


@pytest.mark.asyncio
async def test_bad_requests_and_refusals_fall_back_without_retrying() -> None:
    meta = FakeClient({WONDER: [http_error(openai.BadRequestError, 400)], SPARK: [REFUSED]})
    wrapper, sleeps, _ = make_llm({"meta": meta})

    with pytest.raises(AllModelsFailed) as failure:
        await wrapper.complete_json("report", MESSAGES, Verdict)
    assert failure.value.errors == [f"{WONDER}: HTTP 400", f"{SPARK}: refused"]
    assert sleeps == []


@pytest.mark.asyncio
async def test_raises_all_models_failed_when_every_model_fails() -> None:
    meta = FakeClient(
        {SPARK: [http_error(openai.InternalServerError, 502)] * 4}
    )  # medium, then low, each retried
    baseten = FakeClient({SPARK_OPEN: [invalid_output()]})
    wrapper, _, _ = make_llm({"meta": meta, "baseten": baseten})

    with pytest.raises(AllModelsFailed) as failure:
        await wrapper.complete_json("grill_eval", MESSAGES, Verdict)
    assert failure.value.role == "grill_eval"
    assert failure.value.errors == [
        f"{SPARK}: HTTP 502",
        f"{SPARK}: HTTP 502",
        f"{SPARK_OPEN}: ValidationError",
    ]
    assert sent(meta) == [(SPARK, "medium")] * 2 + [(SPARK, "low")] * 2
    assert sent(baseten) == [(SPARK_OPEN, None)]  # Spark Open never gets reasoning_effort


@pytest.mark.asyncio
async def test_skips_providers_that_are_not_configured() -> None:
    meta = FakeClient({SPARK: [http_error(openai.BadRequestError, 400)] * 2})
    wrapper, _, _ = make_llm({"meta": meta})  # no Baseten client

    with pytest.raises(AllModelsFailed) as failure:
        await wrapper.complete_json("grill_eval", MESSAGES, Verdict)
    assert failure.value.errors == [f"{SPARK}: HTTP 400", f"{SPARK}: HTTP 400", "baseten: not configured"]


@pytest.mark.asyncio
async def test_the_attacker_starts_at_low_effort_and_falls_back_to_medium() -> None:
    meta = FakeClient({SPARK: [http_error(openai.BadRequestError, 400), OK]})
    wrapper, _, _ = make_llm({"meta": meta})

    assert await wrapper.complete_json("attacker", MESSAGES, Verdict) == OK
    assert sent(meta) == [(SPARK, "low"), (SPARK, "medium")]  # low: 6.6 s typical; high timed out at 30 s


@pytest.mark.asyncio
async def test_contributor_switch_maps_spark_and_never_sends_max() -> None:
    meta = FakeClient({SPARK_CONTRIBUTOR: [OK, OK], WONDER: [http_error(openai.BadRequestError, 400)]})
    wrapper, _, records = make_llm({"meta": meta}, use_contributor_models=True)

    await wrapper.complete_json("analyzer", MESSAGES, Verdict, effort="max")
    await wrapper.complete_json("audit", MESSAGES, Verdict, effort="max")
    assert sent(meta) == [(SPARK_CONTRIBUTOR, "xhigh"), (WONDER, "max"), (SPARK_CONTRIBUTOR, "xhigh")]
    assert records[0].cost_usd == pytest.approx(estimate_cost_usd(SPARK_CONTRIBUTOR, 1000, 200, 400))


@pytest.mark.asyncio
async def test_without_the_contributor_switch_spark_gets_max() -> None:
    meta = FakeClient({SPARK: [OK]})
    wrapper, _, _ = make_llm({"meta": meta})

    await wrapper.complete_json("analyzer", MESSAGES, Verdict, effort="max")
    assert sent(meta) == [(SPARK, "max")]


@pytest.mark.asyncio
async def test_role_override_replaces_the_primary_and_skips_a_repeated_fallback() -> None:
    meta = FakeClient({SPARK: [http_error(openai.BadRequestError, 400)]})
    wrapper, _, _ = make_llm({"meta": meta}, role_models={"report": SPARK})

    with pytest.raises(AllModelsFailed):
        await wrapper.complete_json("report", MESSAGES, Verdict)
    assert sent(meta) == [(SPARK, "high")]  # the Spark (high) fallback would repeat the primary


@pytest.mark.asyncio
async def test_success_record_carries_tokens_cost_and_session() -> None:
    meta = FakeClient({SPARK: [OK]})
    wrapper, _, records = make_llm({"meta": meta})

    await wrapper.complete_json("analyzer", MESSAGES, Verdict, session_id="s1")
    [record] = records
    assert (record.role, record.model, record.effort, record.error) == ("analyzer", SPARK, "minimal", None)
    assert (record.prompt_tokens, record.completion_tokens, record.cached_tokens) == (1000, 200, 400)
    assert record.cost_usd == pytest.approx(estimate_cost_usd(SPARK, 1000, 200, 400))
    assert record.session_id == "s1"


def test_cost_estimate_uses_list_prices() -> None:
    # Spark: 800k uncached * $1.25 + 200k cached * $0.15 + 100k out * $4.25, per 1M tokens.
    assert estimate_cost_usd(SPARK, 1_000_000, 100_000, cached_tokens=200_000) == pytest.approx(1.455)
    # Wonder has no cached price, so cached input is billed at the full input price.
    assert estimate_cost_usd(WONDER, 1_000_000, 1_000_000, cached_tokens=500_000) == pytest.approx(24.0)
    assert estimate_cost_usd(SPARK_CONTRIBUTOR, 1_000_000, 1_000_000) == pytest.approx(0.30)
    assert estimate_cost_usd(SPARK_OPEN, 1000, 1000) is None


@pytest.mark.asyncio
async def test_images_are_attached_to_the_last_user_message() -> None:
    meta = FakeClient({SPARK: [OK]})
    wrapper, _, _ = make_llm({"meta": meta})
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "what is this?"}]

    await wrapper.complete_json("vision", messages, Verdict, images=["data:image/png;base64,AAAA"])
    assert meta.calls[0]["messages"][1]["content"] == [
        {"type": "text", "text": "what is this?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
    ]
    assert messages[1]["content"] == "what is this?"  # the caller's messages are untouched


@pytest.mark.asyncio
async def test_complete_text_falls_back_on_an_empty_reply() -> None:
    meta = FakeClient({WONDER: [""], SPARK: ["the report"]})
    wrapper, _, records = make_llm({"meta": meta})

    assert await wrapper.complete_text("report", MESSAGES) == "the report"
    assert records[0].error == "empty reply"


def test_every_role_has_a_spec() -> None:
    assert set(ROLES) == set(get_args(ModelRole))


def test_real_clients_get_the_key_and_no_sdk_retries() -> None:
    settings = LLMSettings(
        api_key="k-secret", baseten_base_url="https://baseten.test/v1", baseten_api_key="b"
    )
    clients = LLM(settings)._clients

    assert set(clients) == {"meta", "baseten"}
    assert (clients["meta"].api_key, clients["meta"].max_retries) == ("k-secret", 0)
    assert str(clients["meta"].base_url) == "https://api.meta.ai/v1/"
    assert set(LLM(LLMSettings(api_key="k"))._clients) == {"meta"}
    assert "k-secret" not in repr(settings)


@pytest.mark.asyncio
async def test_module_functions_need_configure_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "_default", None)
    with pytest.raises(llm.LLMNotConfigured):
        await llm.complete_json("analyzer", MESSAGES, Verdict)

    wrapper = llm.configure(LLMSettings(api_key="k"))
    assert llm.default_llm() is wrapper
