"""Product evals without model keys: scripted sessions through the real backend (REST + WebSocket).

Each check records pass / fail / blocked with a timing and a one-line detail. Model-graded behavior (does the
analyzer see the bug, does the nudge fire) needs MODEL_API_KEY and lives in PR #40's runner instead.
Usage: python product_evals.py <repo> <out.json>   (backend on :8000, MOCK backend on :8001, frontend on :3000)
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import websockets

API = "http://127.0.0.1:8000"
WS = "ws://127.0.0.1:8000"
MOCK_API = "http://127.0.0.1:8001"
MOCK_WS = "ws://127.0.0.1:8001"
FRONTEND = "http://localhost:3000"
REPO = Path(sys.argv[1])
OUT = Path(sys.argv[2])
WINDOWS_RUNNER = "SIGALRM"

results: list[dict] = []


def record(group: str, check: str, status: str, detail: str, ms: float | None = None) -> None:
    results.append({"group": group, "check": check, "status": status, "detail": detail, "ms": None if ms is None else round(ms)})
    print(f"[{status:7}] {group} · {check}: {detail}" + (f" ({ms:.0f} ms)" if ms is not None else ""), flush=True)


class Session:
    """One session socket with every received message kept in order."""

    def __init__(self, ws_base: str, sid: str) -> None:
        self.url = f"{ws_base}/ws/sessions/{sid}"
        self.msgs: list[tuple[float, dict]] = []
        self.ws = None
        self.reader: asyncio.Task | None = None

    async def open(self) -> None:
        self.ws = await websockets.connect(self.url, open_timeout=10, max_size=4 * 2**20)
        self.reader = asyncio.create_task(self._read())
        await self.send({"type": "hello", "client_now_ms": int(time.time() * 1000)})

    async def _read(self) -> None:
        try:
            async for raw in self.ws:
                self.msgs.append((time.perf_counter(), json.loads(raw)))
        except websockets.ConnectionClosed:
            pass

    async def send(self, msg: dict) -> None:
        await self.ws.send(json.dumps(msg))

    async def wait(self, pred, timeout: float, since: int = 0) -> tuple[dict | None, float]:
        """The first message (from index `since`) matching pred, and how long the wait took."""
        start = time.perf_counter()
        while time.perf_counter() - start < timeout:
            for _, m in self.msgs[since:]:
                if pred(m):
                    return m, (time.perf_counter() - start) * 1000
            await asyncio.sleep(0.05)
        return None, (time.perf_counter() - start) * 1000

    async def close(self) -> None:
        if self.ws:
            await self.ws.close()
        if self.reader:
            await asyncio.wait_for(self.reader, 5)


def phase_is(p):
    return lambda m: m["type"] == "session.state" and m["phase"] == p


async def coding_eval(client: httpx.AsyncClient, slug: str) -> None:
    g = f"coding · {slug}"
    problem = json.loads((REPO / "data/problems" / slug / "problem.json").read_text(encoding="utf-8"))
    reference = (REPO / "data/problems" / slug / "reference.py").read_text(encoding="utf-8")
    authored_hints = {h for s in problem["rubric"]["steps"] for h in s.get("hints", [])}

    t0 = time.perf_counter()
    r = await client.post("/api/sessions", json={"mode": "coding", "problem_slug": slug, "feedback": "active", "voice": False})
    ms = (time.perf_counter() - t0) * 1000
    if r.status_code != 201:
        record(g, "Create session", "fail", f"HTTP {r.status_code}: {r.text[:120]}", ms)
        return
    sid = r.json()["id"]
    record(g, "Create session", "pass", f"201, session {sid}", ms)

    pub = (await client.get(f"/api/problems/{slug}")).json()
    leaked = [k for k in ("tests_hidden", "rubric", "reference", "reference_solution") if k in pub]
    record(g, "Problem API hides the answer", "fail" if leaked else "pass",
           f"exposes {leaked}" if leaked else "no hidden tests, rubric or reference in GET /api/problems/{slug}")

    s = Session(WS, sid)
    t0 = time.perf_counter()
    await s.open()
    m, _ = await s.wait(lambda m: m["type"] == "session.state", 10)
    record(g, "Socket hello → session.state", "pass" if m else "fail", f"phase {m['phase']}" if m else "no session.state", (time.perf_counter() - t0) * 1000)
    greet, ms = await s.wait(lambda m: m["type"] == "interviewer.message", 10)
    warm = greet is not None and greet["intervention"]["trigger"] == "warmup"
    record(g, "Warm-up greeting before the problem", "pass" if warm else "fail",
           (greet["intervention"]["text"][:70] + "…") if warm else
           f"first line is a {greet['intervention']['trigger']} line, not the warm-up" if greet else "none within 10 s", ms)

    # The clock holds through the warm-up (#57): session.state keeps the full time while the phase is intro.
    async def state_now(sock: Session) -> dict | None:
        n = len(sock.msgs)
        await sock.send({"type": "hello", "client_now_ms": int(time.time() * 1000)})
        st, _ = await sock.wait(lambda m: m["type"] == "session.state", 5, n)
        return st

    full = m["remaining_s"] if m else None
    await asyncio.sleep(3)
    st = await state_now(s)
    held = st is not None and full is not None and st["phase"] == "intro" and st["remaining_s"] >= full - 1
    record(g, "Clock holds during the warm-up", "pass" if held else "fail",
           f"{full} s left, still {st['remaining_s']} s 3 s later, phase {st['phase']}" if st else "no session.state")

    # Skip Intro: straight to clarify, with the whole time still to come; then the clock runs.
    n = len(s.msgs)
    await s.send({"type": "phase.advance", "to": "clarify"})
    clar, ms = await s.wait(lambda m: phase_is("clarify")(m) or m["type"] == "error", 10, n)
    if clar and clar["type"] == "error":
        record(g, "Skip Intro → clarify", "fail", f"error {clar['code']}: {clar['message'][:60]}", ms)
        clar = None
    elif clar:
        record(g, "Skip Intro → clarify", "pass" if full is None or clar["remaining_s"] >= full - 1 else "fail",
               f"clarify with {clar['remaining_s']} s left", ms)
    else:
        record(g, "Skip Intro → clarify", "fail", "still in the warm-up after 10 s", ms)
    if clar:
        await asyncio.sleep(3)
        st = await state_now(s)
        runs = st is not None and st["remaining_s"] <= clar["remaining_s"] - 2
        record(g, "Clock runs once the problem is presented", "pass" if runs else "fail",
               f"{clar['remaining_s']} s, then {st['remaining_s']} s 3 s later" if st else "no session.state")
    started_at = datetime.fromisoformat((clar or m)["session"]["started_at"].replace("Z", "+00:00"))
    now_t = lambda: int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)  # noqa: E731

    # Chat round-trip: the candidate's turn comes back as a transcript turn.
    n = len(s.msgs)
    await s.send({"type": "chat.send", "text": "Can the list be empty, and does a change of exactly k count?"})
    turn, ms = await s.wait(lambda m: m["type"] == "transcript.update" and m["turn"]["speaker"] == "candidate", 5, n)
    record(g, "Chat → transcript turn", "pass" if turn else "fail", "candidate turn recorded" if turn else "no echo", ms)
    reply, ms = await s.wait(lambda m: m["type"] == "interviewer.message", 8, n)
    record(g, "Interviewer answers a question", "pass" if reply else "blocked",
           reply["intervention"]["text"][:70] if reply else "no answer: needs MODEL_API_KEY", ms if reply else None)

    # Phase rules: clarify → coding is the candidate's to make; going back is refused.
    n = len(s.msgs)
    await s.send({"type": "phase.advance", "to": "coding"})
    cod, ms = await s.wait(phase_is("coding"), 5, n)
    record(g, "Start coding (clarify → coding)", "pass" if cod else "fail", "phase coding" if cod else "not accepted", ms)
    n = len(s.msgs)
    await s.send({"type": "phase.advance", "to": "clarify"})
    err, ms = await s.wait(lambda m: m["type"] == "error", 5, n)
    ok = err is not None and err["code"] == "bad_phase"
    record(g, "Refuses going back (coding → clarify)", "pass" if ok else "fail", f"error {err['code']}" if err else "no error", ms)

    # Hint: should be one of the problem's authored hints (the leak guard may swap it for a generic line).
    n = len(s.msgs)
    await s.send({"type": "hint.request"})
    hint, ms = await s.wait(lambda m: m["type"] in ("interviewer.message", "error"), 30, n)
    if not hint:
        record(g, "Hint button", "fail", "no hint or error within 30 s", ms)
    elif hint["type"] == "error":
        # without a model the server attaches no live engine (analyzer, policy, hints) to the session
        record(g, "Hint button", "blocked" if hint["code"] == "unsupported" else "fail",
               f"server: {hint['message']} (the live engine needs MODEL_API_KEY)", ms)
    else:
        text = hint["intervention"]["text"]
        authored = text in authored_hints
        record(g, "Hint is the authored one", "pass" if authored else "fail",
               ("authored: " if authored else "generic instead of an authored hint: ") + text[:70], ms)

    # Edits: type the reference solution a line at a time, then a paste.
    file = "solution.py"
    code = problem["starter_code"]
    version = 1
    await s.send({"type": "editor.snapshot", "snapshot": {"t": now_t(), "file": file, "version": version, "code": code}})
    version += 1
    await s.send({"type": "editor.events", "events": [{"t": now_t(), "file": file, "version": version, "kind": "change",
                                                         "changes": [{"range_offset": 0, "range_length": len(code), "text": ""}]}]})
    code = ""
    n_flags_before = sum(1 for _, m in s.msgs if m["type"] == "integrity.flag")
    for line in reference.splitlines(keepends=True):
        version += 1
        await s.send({"type": "editor.events", "events": [{"t": now_t(), "file": file, "version": version, "kind": "change",
                                                             "changes": [{"range_offset": len(code), "range_length": 0, "text": line}]}]})
        code += line
        await asyncio.sleep(0.25)
    version += 1
    await s.send({"type": "editor.snapshot", "snapshot": {"t": now_t(), "file": file, "version": version, "code": code}})
    await asyncio.sleep(1.0)
    flags_typed = sum(1 for _, m in s.msgs if m["type"] == "integrity.flag") - n_flags_before
    record(g, "Typing raises no integrity note", "pass" if flags_typed == 0 else "fail", f"{flags_typed} notes while typing line by line")
    n = len(s.msgs)
    pasted = "\n# helper pasted from elsewhere\n" + "x = 1\n" * 12
    version += 1
    await s.send({"type": "editor.events", "events": [{"t": now_t(), "file": file, "version": version, "kind": "paste", "pasted_chars": len(pasted),
                                                         "changes": [{"range_offset": len(code), "range_length": 0, "text": pasted}]}]})
    flag, ms = await s.wait(lambda m: m["type"] == "integrity.flag", 5, n)
    record(g, "A paste becomes a neutral note", "pass" if flag else "fail", flag["flag"]["detail"][:70] if flag else "no integrity.flag", ms)
    version += 1
    await s.send({"type": "editor.events", "events": [{"t": now_t(), "file": file, "version": version, "kind": "change",
                                                         "changes": [{"range_offset": len(code), "range_length": len(pasted), "text": ""}]}]})
    version += 1
    await s.send({"type": "editor.snapshot", "snapshot": {"t": now_t(), "file": file, "version": version, "code": code}})

    # An infinite loop comes back as per-test timeouts, not a hung or killed run.
    n = len(s.msgs)
    looping = f"def {problem['function']['name']}(*args):\n    while True:\n        pass\n"
    await s.send({"type": "code.run", "file": file, "code": looping})
    res, ms = await s.wait(lambda m: m["type"] in ("run.result", "error"), 60, n)
    if not res or res["type"] == "error":
        record(g, "An infinite loop times out", "fail", f"error {res['code']}" if res else "no result within 60 s", ms)
    else:
        rr = res["result"]
        per_test = rr["cases"] and all("timed out" in (c["error"] or "") or "not run" in (c["error"] or "") for c in rr["cases"])
        record(g, "An infinite loop times out", "pass" if rr["timed_out"] and per_test else "fail",
               f"timed_out={rr['timed_out']}, {rr['cases'][0]['error'] if rr['cases'] else rr['stderr'][:60]}"[:110], ms)

    # Run and submit the reference solution. A submit that passes every test moves on to the wrap-up.
    for kind in ("run", "submit"):
        n = len(s.msgs)
        n_submit = n
        await s.send({"type": f"code.{kind}", "file": file, "code": code})
        res, ms = await s.wait(lambda m: m["type"] in ("run.result", "error"), 60, n)
        if not res:
            record(g, f"{kind.title()} the reference solution", "fail", "no result within 60 s", ms)
        elif res["type"] == "error":
            record(g, f"{kind.title()} the reference solution", "fail", f"error {res['code']}: {res['message'][:60]}", ms)
        else:
            rr = res["result"]
            if rr["compile_error"] and WINDOWS_RUNNER in rr["compile_error"]:
                record(g, f"{kind.title()} the reference solution", "blocked", "Windows LocalRunner: signal.SIGALRM (needs Modal or Linux/Mac)", ms)
            else:
                good = rr["passed"] == rr["total"] and rr["total"] > 0
                record(g, f"{kind.title()} the reference solution", "pass" if good else "fail", f"{rr['passed']} of {rr['total']} tests passed", ms)

    # The public timeline while live: no analyses or system notes, hidden tests redacted.
    tl = (await client.get(f"/api/sessions/{sid}/timeline")).json()
    kinds = {e["kind"] for e in tl}
    hidden_kinds = kinds & {"analysis", "system"}
    record(g, "Live timeline hides analyses and notes", "fail" if hidden_kinds else "pass",
           f"shows {sorted(hidden_kinds)}" if hidden_kinds else f"{len(tl)} events, kinds {sorted(kinds)}"[:120])
    last_snap = [e for e in tl if e["kind"] == "snapshot" and e["payload"].get("file") == file]
    record(g, "Edits reach the timeline", "pass" if last_snap and last_snap[-1]["payload"]["code"] == code else "fail",
           f"{sum(1 for e in tl if e['kind'] == 'editor')} edit events, last snapshot matches the typed code"
           if last_snap and last_snap[-1]["payload"]["code"] == code else "last snapshot differs from the typed code")
    rep = await client.get(f"/api/sessions/{sid}/report")
    record(g, "No report while live", "pass" if rep.status_code == 409 else "fail", f"HTTP {rep.status_code}")

    # Reconnect: drop the socket and come back in the same phase.
    states = [m for _, m in s.msgs if m["type"] == "session.state"]
    phase_before = states[-1]["phase"] if states else None
    await s.close()
    s2 = Session(WS, sid)
    t0 = time.perf_counter()
    await s2.open()
    st, _ = await s2.wait(lambda m: m["type"] == "session.state", 10)
    record(g, "Reconnect keeps the session", "pass" if st and st["phase"] == phase_before else "fail",
           f"back in {st['phase']} (was {phase_before})" if st else "no state after reconnect", (time.perf_counter() - t0) * 1000)

    # Wrap-up: scripted questions. A passing submit has already moved there and asked the first one;
    # otherwise the candidate moves on with "I'm done".
    is_question = lambda m: m["type"] == "interviewer.message" and m["intervention"]["level"] == "question"  # noqa: E731
    if phase_before == "wrap_up":
        q, ms = await s.wait(is_question, 1, n_submit)
        how = "after the passing submit: "
    else:
        n = len(s2.msgs)
        await s2.send({"type": "phase.advance", "to": "wrap_up"})
        q, ms = await s2.wait(is_question, 10, n)
        how = "after I'm done: "
    record(g, "Wrap-up asks its questions", "pass" if q else "fail", how + (q["intervention"]["text"][:60] if q else "no question"), ms)
    await s2.send({"type": "chat.send", "text": "O(n) time, one pass, and O(1) extra space."})
    await asyncio.sleep(1)

    # End → report.
    t0 = time.perf_counter()
    await client.post(f"/api/sessions/{sid}/end")
    report = None
    while time.perf_counter() - t0 < 150:
        rep = await client.get(f"/api/sessions/{sid}/report")
        if rep.status_code == 200:
            report = rep.json()
            break
        await asyncio.sleep(1)
    ms = (time.perf_counter() - t0) * 1000
    if not report:
        record(g, "Report after End", "fail", "not ready within 150 s", ms)
    else:
        record(g, "Report after End", "pass" if ms <= 90_000 else "fail",
               f"{len(report['dimensions'])} dimensions, {len(report['moments'])} moments, model {report['model']}", ms)
        written = bool(report["strengths"] or report["improvements"])
        record(g, "Written review in the report", "pass" if written else "blocked",
               "strengths and improvements written" if written else "metrics only: needs MODEL_API_KEY")
    final_tl = (await client.get(f"/api/sessions/{sid}/timeline")).json()
    false_notes = [e for e in final_tl if e["kind"] == "system" and "replaced the edits" in json.dumps(e["payload"])]
    record(g, "No false 'replaced the edits' note", "pass" if not false_notes else "fail",
           f"{len(false_notes)} such notes (fixed by PR #36, not merged)" if false_notes else "none")
    await s2.close()
    results.append({"group": g, "check": "_session", "status": "info", "detail": sid, "ms": None})


async def mock_defense_eval() -> None:
    g = "defense · recorded run (MOCK)"
    async with httpx.AsyncClient(base_url=MOCK_API, timeout=30) as client:
        h = (await client.get("/api/health")).json()
        if not h.get("mock"):
            record(g, "MOCK backend", "fail", "port 8001 isn't in MOCK mode")
            return
        r = await client.post("/api/sessions", json={"mode": "defense", "project_id": "bank-transfer-min"})
        sid = r.json()["id"]
        record(g, "Create session", "pass" if r.status_code == 201 else "fail", f"{r.status_code}, scenario {sid}")
    s = Session(MOCK_WS, sid)
    t0 = time.perf_counter()
    await s.open()
    order = []
    ver, _ = await s.wait(lambda m: m["type"] == "defense.verdict", 60)
    await asyncio.sleep(0.5)
    for _, m in s.msgs:
        if m["type"] == "session.state" and (not order or order[-1] != m["phase"]):
            order.append(m["phase"])
    want = ["audit", "chaos", "grill", "fix", "verify", "verdict", "ended"]
    record(g, "Stages in order", "pass" if [p for p in order if p in want] == want else "fail", " → ".join(order), (time.perf_counter() - t0) * 1000)
    count = lambda t: sum(1 for _, m in s.msgs if m["type"] == t)  # noqa: E731
    audit = next((m for _, m in s.msgs if m["type"] == "defense.audit"), None)
    no_explain = audit is not None and all("explanation" not in f for f in audit["audit"]["findings"])
    record(g, "Audit hides explanations", "pass" if no_explain else "fail", f"{len(audit['audit']['findings'])} findings, no explanation field" if audit else "no audit")
    record(g, "Live attack metrics stream", "pass" if count("defense.chaos.metric") >= 10 else "fail", f"{count('defense.chaos.metric')} metric messages")
    runs = [m["run"] for _, m in s.msgs if m["type"] == "defense.chaos.done"]
    record(g, "Baseline breaks, verify holds", "pass" if [r["verdict"] for r in runs] == ["broke", "held"] else "fail",
           "; ".join(f"{r['kind']}: {r['verdict']}" for r in runs))
    grill = next((m for _, m in s.msgs if m["type"] == "defense.grill.eval"), None)
    record(g, "Grill graded with the finding revealed", "pass" if grill and grill["finding"].get("explanation") else "fail",
           f"score {grill['turn']['score']}/10" if grill else "no grill eval")
    record(g, "Merge gate verdict", "pass" if ver and ver["verdict"]["passed"] else "fail", "PASS" if ver and ver["verdict"]["passed"] else str(ver))
    await s.close()


async def real_defense_eval(client: httpx.AsyncClient) -> None:
    g = "defense · live on this machine"
    t0 = time.perf_counter()
    r = await client.post("/api/sessions", json={"mode": "defense", "project_id": "bank-transfer-min", "feedback": "active"})
    if r.status_code != 201:
        record(g, "Create session", "fail", f"HTTP {r.status_code}: {r.text[:100]}", (time.perf_counter() - t0) * 1000)
        return
    sid = r.json()["id"]
    record(g, "Create session", "pass", f"201, session {sid}", (time.perf_counter() - t0) * 1000)
    s = Session(WS, sid)
    await s.open()
    audit, ms = await s.wait(lambda m: m["type"] == "defense.audit", 130)
    record(g, "Audit arrives", "pass" if audit else "fail",
           f"{len(audit['audit']['findings'])} finding(s), {len(audit['audit']['nodes'])} node(s); without a key it uses the sample's flaws.json"
           if audit else "no audit", ms)
    metric, ms = await s.wait(lambda m: m["type"] == "defense.chaos.metric", 90)
    record(g, "Attack starts and streams metrics", "pass" if metric else "fail", "first metric received" if metric else "no metrics", ms)
    done, ms = await s.wait(lambda m: m["type"] in ("defense.chaos.done", "error"), 90)
    if done and done["type"] == "defense.chaos.done":
        record(g, "Attack finishes with a verdict", "pass", f"{done['run']['verdict']}: {done['run']['summary'][:60]}", ms)
    else:
        record(g, "Attack finishes with a verdict", "blocked",
               "Windows LocalRunner: stop_project can't delete an open log file (WinError 32)" if done else "no result", ms)
    # The session must never dead-end after the attack: it moves on to the grill (or past it).
    later = {"grill", "fix", "verify", "verdict", "ended", "reporting", "reported"}
    moved, ms = await s.wait(lambda m: m["type"] == "session.state" and m["phase"] in later, 30)
    if moved:
        record(g, "Session moves on after the attack", "pass", f"reached {moved['phase']}", ms)
    else:
        state = (await client.get(f"/api/sessions/{sid}")).json()
        record(g, "Session moves on after the attack", "fail", f"stuck in phase {state['phase']} with nothing to retry", ms)
    await s.close()


async def frontend_eval(sids: list[str]) -> None:
    g = "frontend · pages"
    routes = ["/", "/coding", "/defense", "/coding/demo", "/defense/demo", "/report/demo"] + [f"/coding/{sids[0]}", f"/report/{sids[0]}"]
    async with httpx.AsyncClient(base_url=FRONTEND, timeout=60, follow_redirects=True) as client:
        for path in routes:
            await client.get(path)  # warm the dev compile
            t0 = time.perf_counter()
            r = await client.get(path)
            ms = (time.perf_counter() - t0) * 1000
            record(g, f"GET {path}", "pass" if r.status_code == 200 else "fail", f"HTTP {r.status_code}, {len(r.content) // 1024} KB", ms)


async def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    async with httpx.AsyncClient(base_url=API, timeout=30) as client:
        h = (await client.get("/api/health")).json()
        record("setup", "Backend health", "pass" if h["ok"] and not h["mock"] else "fail", json.dumps(h))
        for slug in ("thermostat-swings", "ingredient-groups", "genre-sampler"):
            try:
                await coding_eval(client, slug)
            except Exception as exc:  # keep going: one broken problem shouldn't hide the rest
                record(f"coding · {slug}", "Eval crashed", "fail", f"{type(exc).__name__}: {exc}"[:150])
        try:
            await real_defense_eval(client)
        except Exception as exc:
            record("defense · live on this machine", "Eval crashed", "fail", f"{type(exc).__name__}: {exc}"[:150])
    try:
        await mock_defense_eval()
    except Exception as exc:
        record("defense · recorded run (MOCK)", "Eval crashed", "fail", f"{type(exc).__name__}: {exc}"[:150])
    sids = [r["detail"] for r in results if r["check"] == "_session"]
    await frontend_eval(sids or ["missing"])
    OUT.write_text(
        json.dumps({"started": started, "finished": datetime.now(timezone.utc).isoformat(), "results": results}, indent=1),
        encoding="utf-8",
    )
    tally = {k: sum(1 for r in results if r["status"] == k) for k in ("pass", "fail", "blocked")}
    print("TOTAL", tally)


# Details hold "→" and "·", which a Windows console's default code page can't print.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
asyncio.run(main())
