"""The latency budget (PLAN §18), measured end to end against a running backend on the client's clock.

    uv run python -m tests.evals.latency                       # the local backend on :8000
    uv run python -m tests.evals.latency --url https://…       # the deployed build (IC3)

- pause → nudge: a candidate types a solution that skips clarifying, then pauses; time from the last keystroke to
  the missed-step nudge (nothing earlier is said, so the 45 s cooldown doesn't hold it).
- question → answer, Run → results, Submit → results: round trips on a second session.
Costs a few model calls per session.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import httpx
from websockets.asyncio.client import ClientConnection, connect

from tests.evals.runner import typing_changes

HEADER = "def count_big_swings(temps: list[int], k: int) -> int:\n"
LINES = [
    "    swings = 0\n",
    "    for i in range(1, len(temps)):\n",
    "        if abs(temps[i] - temps[i - 1]) > k:\n",
    "            swings += 1\n",
    "    return swings\n",
]
SOLUTION = HEADER + "".join(LINES)
NUDGE_WAIT_S = 60


class Client:
    """One candidate tab: a session socket plus everything the server sent, stamped on arrival."""

    def __init__(self, ws: ClientConnection, started_at: float) -> None:
        self.ws = ws
        self.started_at = started_at
        self.inbox: list[tuple[float, dict[str, Any]]] = []
        self.code = HEADER + "    pass\n"
        self.version = 1
        self.last_input = time.monotonic()

    def t(self) -> int:
        return round((time.time() - self.started_at) * 1000)

    async def send(self, msg: dict[str, Any]) -> None:
        await self.ws.send(json.dumps(msg))

    async def type_code(self, new: str) -> None:
        events = []
        for change in typing_changes(self.code, new):
            self.version += 1
            events.append(
                {
                    "t": self.t(),
                    "file": "solution.py",
                    "version": self.version,
                    "kind": "change",
                    "changes": [change.model_dump()],
                }
            )
        self.code = new
        await self.send({"type": "editor.events", "events": events})
        self.last_input = time.monotonic()

    async def wait_for(
        self, match: Callable[[dict[str, Any]], bool], after: float, timeout_s: float
    ) -> float | None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            for at, m in self.inbox:
                if at >= after and match(m):
                    return at
            await asyncio.sleep(0.02)
        return None


async def session(url: str, body: Callable[[Client], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=url, timeout=30) as http:
        config = {"mode": "coding", "problem_slug": "thermostat-swings", "voice": False}
        sid = (await http.post("/api/sessions", json=config)).json()["id"]
    ws_url = url.replace("http", "ws", 1) + f"/ws/sessions/{sid}"
    async with connect(ws_url) as ws:
        await ws.send(json.dumps({"type": "hello", "client_now_ms": 0}))
        started = None
        while started is None:
            m = json.loads(await ws.recv())
            if m["type"] == "session.state" and m["session"]["started_at"]:
                started = datetime.fromisoformat(m["session"]["started_at"]).timestamp()
        client = Client(ws, started)

        async def read() -> None:
            async for raw in ws:
                client.inbox.append((time.monotonic(), json.loads(raw)))

        reader = asyncio.create_task(read())
        try:
            snapshot = {"t": client.t(), "file": "solution.py", "version": 1, "code": client.code}
            await client.send({"type": "editor.snapshot", "snapshot": snapshot})
            return await body(client)
        finally:
            reader.cancel()


async def pause_to_nudge(c: Client) -> dict[str, Any]:
    await c.send(
        {"type": "chat.send", "text": "I'll walk the list once and compare neighbors."}
    )  # a plan, not a question
    await asyncio.sleep(3)
    code = HEADER
    for line in LINES:
        code += line
        await c.type_code(code)
        await asyncio.sleep(1.0)
    deadline = time.monotonic() + NUDGE_WAIT_S
    while time.monotonic() < deadline:
        at = await c.wait_for(_nudge, after=0, timeout_s=12)
        if at is not None:
            return {"pause_to_nudge_s": at - c.last_input if c.last_input <= at else None}
        await c.type_code(c.code + "\n")  # a small edit and another pause, as a thinking candidate would
    return {"pause_to_nudge_s": None}


async def round_trips(c: Client) -> dict[str, Any]:
    out: dict[str, Any] = {}
    sent = time.monotonic()
    await c.send({"type": "chat.send", "text": "Can the list be empty?"})
    at = await c.wait_for(lambda m: _said(m, "asked"), after=sent, timeout_s=30)
    out["question_to_answer_s"] = at - sent if at else None
    for kind in ("run", "submit"):
        sent = time.monotonic()
        await c.send({"type": f"code.{kind}", "file": "solution.py", "code": SOLUTION})
        at = await c.wait_for(lambda m: m["type"] == "run.result", after=sent, timeout_s=30)
        out[f"{kind}_to_results_s"] = at - sent if at else None
    return out


def _said(m: dict[str, Any], trigger: str) -> bool:
    return m["type"] == "interviewer.message" and m["intervention"]["trigger"] == trigger


def _nudge(m: dict[str, Any]) -> bool:
    return m["type"] == "interviewer.message" and m["intervention"]["trigger"] not in (
        "phase",
        "asked",
        "paste",
    )


def summarize(name: str, values: list[float]) -> str:
    if not values:
        return f"{name}: no samples"
    return f"{name}: n={len(values)} p50={statistics.median(values):.2f}s max={max(values):.2f}s"


async def measure(url: str, n: int) -> list[str]:
    results = await asyncio.gather(
        *(session(url, pause_to_nudge) for _ in range(n)), *(session(url, round_trips) for _ in range(n))
    )
    keys = ("pause_to_nudge_s", "question_to_answer_s", "run_to_results_s", "submit_to_results_s")
    return [summarize(k, [r[k] for r in results if r.get(k) is not None]) for k in keys]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.evals.latency")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--sessions", type=int, default=4)
    args = parser.parse_args(argv)
    for line in asyncio.run(measure(args.url.rstrip("/"), args.sessions)):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
