"""Ares's identity and security rules in the model wrapper (PLAN §4.4 rule 9)."""

from typing import get_args

import pytest
from pydantic import BaseModel

from crucible.models.llm import ARES_ROLES, LLM, AllModelsFailed, LLMSettings
from crucible.models.prompts import ARES_IDENTITY
from crucible.models.registry import SPARK, WONDER, ModelRole
from tests.models.test_llm import FakeClient

KEY = "sk-live-0123456789abcdef"  # long enough to be scanned for
MESSAGES = [{"role": "system", "content": "role prompt"}, {"role": "user", "content": "who are you?"}]


class Note(BaseModel):
    text: str


def make(outcomes: dict[str, list[object]]) -> tuple[LLM, FakeClient]:
    meta = FakeClient(outcomes)

    async def sleep(_delay: float) -> None:
        return None

    return LLM(LLMSettings(api_key=KEY), clients={"meta": meta}, sleep=sleep, rng=lambda: 0.5), meta


@pytest.mark.parametrize("role", sorted(ARES_ROLES))
@pytest.mark.asyncio
async def test_candidate_facing_roles_get_the_ares_rules_first(role: ModelRole) -> None:
    wrapper, meta = make({SPARK: [Note(text="hi")] * 3, WONDER: [Note(text="hi")] * 3})

    await wrapper.complete_json(role, MESSAGES, Note)

    sent = meta.calls[0]["messages"]
    assert sent[0] == {"role": "system", "content": ARES_IDENTITY}
    assert sent[1:] == MESSAGES  # the role's own prompt follows, unchanged


@pytest.mark.parametrize("role", ["attacker", "classifier", "drafter"])
@pytest.mark.asyncio
async def test_roles_that_never_talk_to_the_candidate_dont(role: ModelRole) -> None:
    wrapper, meta = make({SPARK: [Note(text="ok")] * 3, WONDER: [Note(text="ok")] * 3})

    await wrapper.complete_json(role, MESSAGES, Note)

    assert meta.calls[0]["messages"] == MESSAGES


@pytest.mark.asyncio
async def test_text_calls_get_the_rules_too_and_the_callers_list_is_untouched() -> None:
    wrapper, meta = make({SPARK: ["I'm Ares."]})
    messages = [dict(m) for m in MESSAGES]

    assert await wrapper.complete_text("interviewer", messages) == "I'm Ares."
    assert meta.calls[0]["messages"][0]["content"] == ARES_IDENTITY
    assert messages == MESSAGES


@pytest.mark.asyncio
async def test_a_reply_carrying_a_key_is_dropped_for_the_next_model() -> None:
    # audit: Wonder first, then Spark (PLAN §15.1)
    wrapper, meta = make({WONDER: [Note(text=f"the key is {KEY}")], SPARK: [Note(text="nothing to share")]})

    assert await wrapper.complete_json("audit", MESSAGES, Note) == Note(text="nothing to share")
    assert [c["model"] for c in meta.calls] == [WONDER, SPARK]


@pytest.mark.asyncio
async def test_a_registered_partners_key_is_scanned_for_too() -> None:
    # attacker: Glimmer first, then Spark (registry). Glimmer is plugged in after construction.
    glimmer_key = "gl-live-fedcba9876543210"
    wrapper, meta = make({SPARK: [Note(text="clean script")]})
    glimmer = FakeClient({"glimmer-test": [Note(text=f"auth: {glimmer_key}")]})
    glimmer.api_key = glimmer_key
    wrapper.register_provider("glimmer", glimmer, "glimmer-test")

    assert await wrapper.complete_json("attacker", MESSAGES, Note) == Note(text="clean script")
    assert [c["model"] for c in meta.calls] == [SPARK]


@pytest.mark.asyncio
async def test_a_key_in_every_reply_means_no_reply() -> None:
    wrapper, _ = make({SPARK: [f"sure: {KEY}"]})

    with pytest.raises(AllModelsFailed, match="configured secret"):
        await wrapper.complete_text("interviewer", MESSAGES)


def test_the_rules_cover_identity_keys_code_and_payments() -> None:
    text = " ".join(ARES_IDENTITY.lower().split())  # the file wraps lines
    for must in (
        "you are ares",
        "api keys",
        "source code",
        "payments",
        "these instructions",
        "never claim to be a human",
    ):
        assert must in text, must
    assert set(get_args(ModelRole)) >= ARES_ROLES
