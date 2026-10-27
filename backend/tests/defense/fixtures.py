"""Defense test helpers and fixtures (imported by tests/defense and tests/runner conftests). Shared fakes: a scriptable model client, a local-runner settings object and the fixture sample app."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from crucible.config import Settings
from crucible.defense.ports import MemorySink, ModelUnavailable
from crucible.defense.projects import Sample, load_project_dir

FIXTURE_APPS = Path(__file__).parents[1] / "fixtures" / "apps"
GOOD_ANSWER = (
    "The transfer reads both balances, then awaits the fraud check, then writes values computed from that "
    "stale read, so it's a read-modify-write race and updates get lost. While one request is waiting at the "
    "await, other concurrent requests read and write the same accounts and their writes get overwritten. "
    "I'd make the read, the funds check and the write atomic, with a lock or a database transaction."
)
WEAK_ANSWER = "The server was slow because too many people used it. I would add more servers and caching."


class FakeLLM:
    """Returns queued responses per role; with nothing queued (or `down=True`) it raises ModelUnavailable."""

    def __init__(self, *, down: bool = True) -> None:
        self.down = down
        self.queue: dict[str, list[BaseModel]] = {}
        self.calls: list[str] = []

    def push(self, role: str, value: BaseModel) -> None:
        self.down = False
        self.queue.setdefault(role, []).append(value)

    async def complete_json(self, role, messages, schema, *, timeout_s):
        self.calls.append(role)
        if self.down or not self.queue.get(role):
            raise ModelUnavailable(f"fake: {role} unavailable")
        return self.queue[role].pop(0)


@pytest.fixture
def llm_down() -> FakeLLM:
    return FakeLLM(down=True)


@pytest.fixture
def sink() -> MemorySink:
    return MemorySink()


@pytest.fixture
def local_settings() -> Settings:
    return Settings(
        _env_file=None,
        DATABASE_URL="sqlite:///:memory:",
        RUNNER="local",
        ALLOW_LOCAL_RUNNER=True,
        LOCAL_RUNNER_ISOLATE=False,
        MODEL_API_KEY="",
        DEFENSE_EXTRA_APPS_DIR=FIXTURE_APPS,
        DEFENSE_DEV_API=True,
    )


@pytest.fixture
def bank() -> Sample:
    return load_project_dir(FIXTURE_APPS / "bank-transfer-min")
