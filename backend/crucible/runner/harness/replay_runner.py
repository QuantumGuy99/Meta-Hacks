# Appended to the chaos template in place of its load runner (DEF-14, PLAN §11.11): the same three
# model-written bodies and the same loopback guard, but exactly two requests, A and B, started together
# on two connections. Repeats until the invariant breaks or the tries run out, then prints the lanes as
# measured and the usual done line.

TRIES = __TRIES__


async def _main() -> None:
    _ = (random, string, uuid, CONCURRENCY, DURATION_S)   # available to the model's bodies
    async with _client(timeout=10.0) as a, _client(timeout=10.0) as b, _client(timeout=5.0) as probe:
        lanes: dict = {}
        ok, violations, detail, attempt = True, 0, "", 0
        start = time.monotonic()
        for attempt in range(1, TRIES + 1):
            ctx = await setup(probe)
            t0 = time.monotonic()

            async def one(lane: str, client: httpx.AsyncClient, i: int) -> None:
                begun = time.monotonic()
                try:
                    status = (await make_request(client, i, ctx)).status_code
                except Exception:
                    status = 0
                lanes[lane] = {
                    "lane": lane,
                    "start_ms": round((begun - t0) * 1000, 1),
                    "end_ms": round((time.monotonic() - t0) * 1000, 1),
                    "status": status,
                }

            await asyncio.gather(one("A", a, 0), one("B", b, 1))
            try:
                ok, violations, detail = await check_invariant(probe, ctx)
            except Exception as exc:
                ok, violations, detail = True, 0, f"invariant check crashed: {type(exc).__name__}"
            if not ok:
                break
        _emit({"lanes": [lanes[k] for k in sorted(lanes)], "attempts": attempt})
        _emit({
            "done": True,
            "invariant_ok": bool(ok),
            "violations": int(violations),
            "detail": str(detail),
            "requests": 2 * attempt,
            "errors": sum(1 for x in lanes.values() if x["status"] == 0 or x["status"] >= 400),
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "elapsed_s": round(time.monotonic() - start, 2),
        })


if __name__ == "__main__":
    asyncio.run(_main())
