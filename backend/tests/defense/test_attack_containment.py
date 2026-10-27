"""Defense in depth for attack scripts (PR #15 review): even a URL the validator can't see, built at runtime,
never leaves the machine. The template's client refuses every host but the app under test."""

import json

import pytest

from crucible.contracts.defense import AttackFunctions
from crucible.defense.attack_writer import render_attack
from crucible.defense.validator import validate_functions
from crucible.runner.local import LocalRunner

pytestmark = pytest.mark.e2e

SNEAKY = AttackFunctions(
    setup_body="return {}",
    # "://" never appears as one literal, so this gets past the validator by design
    request_body='return await client.get("http" + ":" + "//" + "example.com" + "/")',
    invariant_body='return True, 0, "n/a"',
    rationale="test",
)


async def test_runtime_built_outside_url_is_blocked_by_the_template(local_settings, bank):
    validate_functions(SNEAKY)  # the validator alone can't catch it...
    runner = LocalRunner(local_settings)
    h = await runner.start_project(bank.project, bank.files)
    try:
        script = render_attack(SNEAKY, port=h.port, concurrency=5, duration_s=1)
        await runner.put_file(h, "attack.py", script)
        lines = [x async for x in runner.stream_exec(h, ["python", "attack.py"], timeout_s=30)]
    finally:
        await runner.stop_project(h)
    done = json.loads(next(x for x in lines if x.startswith('{"done"')))
    # ...but the template's hook refuses every request before it is sent: all of them count as errors.
    assert done["requests"] > 0 and done["errors"] == done["requests"]
