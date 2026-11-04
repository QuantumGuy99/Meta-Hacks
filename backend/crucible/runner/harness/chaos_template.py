"""Chaos attack template (PLAN §11.4). The model writes ONLY the three bodies marked below; this file owns
imports, concurrency, timing and the JSON-lines output, so every metric line matches ChaosMetric.

Rendered by crucible.defense.attack_writer.render_attack(). Runs with the standard library + httpx only.
check_invariant returns (ok, violations, detail): violations is a count shown live (seats double-booked,
dollars missing), detail is the human headline ("$1,240 disappeared").
"""

import asyncio
import json
import math
import random
import string
import sys
import time
import uuid

import httpx

BASE = "http://127.0.0.1:__PORT__"
CONCURRENCY = __CONCURRENCY__
DURATION_S = __DURATION_S__
METRIC_INTERVAL_S = 0.5
POOL_SIZE = 10            # connections per httpx client: one big pool collapses past ~50 concurrent requests
RAMP_S = 0.4              # workers start spread over this window, not in one burst (listen-queue overflow)


async def setup(client: httpx.AsyncClient) -> dict:
__SETUP_BODY__


async def make_request(client: httpx.AsyncClient, i: int, ctx: dict) -> httpx.Response:
__REQUEST_BODY__


async def check_invariant(client: httpx.AsyncClient, ctx: dict) -> tuple[bool, int, str]:
__INVARIANT_BODY__


# --- fixed runner below: the model never edits this part ---------------------------------------------


_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


async def _loopback_only(request: httpx.Request) -> None:
    # The validator checks the code; this checks the traffic: any host but the app under test is refused.
    if request.url.host not in _LOOPBACK:
        raise RuntimeError(f"blocked: the attack may only call the app under test, not {request.url.host!r}")


_SEND = httpx.AsyncClient.send


async def _send_loopback_only(self, request: httpx.Request, **kwargs):
    # Enforced on the class, not only through a client's event hook: a body that builds its own client
    # (type(client)()) or clears `event_hooks` still sends through here. Redirects are off, so a modified app
    # can't bounce the attack to another host.
    await _loopback_only(request)
    kwargs["follow_redirects"] = False
    return await _SEND(self, request, **kwargs)


httpx.AsyncClient.send = _send_loopback_only


def _client(**kwargs) -> httpx.AsyncClient:
    return httpx.AsyncClient(event_hooks={"request": [_loopback_only]}, follow_redirects=False, **kwargs)


def _pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = min(len(sorted_vals) - 1, max(0, math.ceil(p * len(sorted_vals)) - 1))
    return round(sorted_vals[k], 2)


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


async def _main() -> None:
    _ = (random, string, uuid)   # available to the model's bodies
    n_pools = max(1, math.ceil(CONCURRENCY / POOL_SIZE))
    limits = httpx.Limits(max_connections=POOL_SIZE, max_keepalive_connections=POOL_SIZE)
    clients = [_client(limits=limits, timeout=10.0) for _ in range(n_pools)]
    client = clients[0]
    try:
        await _run(clients, client)
    finally:
        for c in clients:
            await c.aclose()


async def _run(clients: list, client: httpx.AsyncClient) -> None:
    ctx = await setup(client)
    state = {"i": 0, "in_flight": 0, "requests": 0, "errors": 0, "violations": 0}
    window: list[float] = []
    all_lat: list[float] = []
    start = time.monotonic()
    deadline = start + DURATION_S

    async def worker(k: int) -> None:
        pool = clients[k % len(clients)]
        await asyncio.sleep(RAMP_S * k / max(CONCURRENCY, 1))
        while time.monotonic() < deadline:
            i = state["i"]
            state["i"] += 1
            state["in_flight"] += 1
            t0 = time.monotonic()
            try:
                resp = await make_request(pool, i, ctx)
                if resp.status_code >= 400:
                    state["errors"] += 1
            except Exception:
                state["errors"] += 1
            finally:
                state["in_flight"] -= 1
                state["requests"] += 1
                ms = (time.monotonic() - t0) * 1000
                window.append(ms)
                all_lat.append(ms)

    async def checker(probe: httpx.AsyncClient) -> None:
        # Own client and own loop: the attack's pool is saturated by design, so sharing it would
        # stall the live violation count (and with it every metric line).
        while True:
            try:
                _, v, _ = await check_invariant(probe, ctx)
                state["violations"] = max(int(v), 0)
            except Exception:
                pass
            await asyncio.sleep(METRIC_INTERVAL_S)

    async def reporter() -> None:
        last_t = start
        while True:
            await asyncio.sleep(METRIC_INTERVAL_S)
            now = time.monotonic()
            lat = sorted(window)
            window.clear()
            _emit({
                "t_ms": int((now - start) * 1000),
                "in_flight": state["in_flight"],
                "rps": round(len(lat) / max(now - last_t, 1e-6), 1),
                "p50_ms": _pct(lat, 0.50),
                "p95_ms": _pct(lat, 0.95),
                "p99_ms": _pct(lat, 0.99),
                "errors": state["errors"],
                "violations": state["violations"],
            })
            last_t = now

    async with _client(timeout=5.0) as probe:
        chk = asyncio.create_task(checker(probe))
        rep = asyncio.create_task(reporter())
        await asyncio.gather(*(worker(k) for k in range(CONCURRENCY)))
        rep.cancel()
        chk.cancel()
    try:
        ok, violations, detail = await check_invariant(client, ctx)
    except Exception as exc:
        ok, violations, detail = False, 0, f"invariant check crashed: {type(exc).__name__}: {exc}"
    lat = sorted(all_lat)
    _emit({  # one last metric line, so the chart and the verdict end on the final count, not the last tick
        "t_ms": int((time.monotonic() - start) * 1000),
        "in_flight": 0,
        "rps": 0.0,
        "p50_ms": _pct(lat, 0.50),
        "p95_ms": _pct(lat, 0.95),
        "p99_ms": _pct(lat, 0.99),
        "errors": state["errors"],
        "violations": max(int(violations), 0),
    })
    _emit({
        "done": True,
        "invariant_ok": bool(ok),
        "violations": int(violations),
        "detail": str(detail),
        "requests": state["requests"],
        "errors": state["errors"],
        "p95_ms": _pct(lat, 0.95),
        "p99_ms": _pct(lat, 0.99),
        "elapsed_s": round(time.monotonic() - start, 2),
    })


if __name__ == "__main__":
    asyncio.run(_main())
