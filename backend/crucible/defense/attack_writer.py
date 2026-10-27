"""AttackWriter: model-written attack bodies → validated → rendered into the fixed template (PLAN §11.4)."""

from __future__ import annotations

import json
import logging
import textwrap

from crucible.contracts.defense import AttackFunctions, Finding
from crucible.defense.ports import EventSink, ModelClient, ModelUnavailable, note
from crucible.defense.prompts import PROMPTS
from crucible.defense.validator import AttackRejected, validate_functions
from crucible.runner.harness import CHAOS_TEMPLATE

logger = logging.getLogger(__name__)

ATTACKER_TIMEOUT_S = 30
MAX_CONCURRENCY = 200
MAX_DURATION_S = 30


def clamp_load(concurrency: int, duration_s: int) -> tuple[int, int]:
    return max(1, min(concurrency, MAX_CONCURRENCY)), max(1, min(duration_s, MAX_DURATION_S))


def render_attack(fn: AttackFunctions, *, port: int, concurrency: int, duration_s: int) -> str:
    """Fill the template. Call validate_functions first; the rendered script must also compile."""
    concurrency, duration_s = clamp_load(concurrency, duration_s)
    script = (
        CHAOS_TEMPLATE.replace("__PORT__", str(int(port)))
        .replace("__CONCURRENCY__", str(concurrency))
        .replace("__DURATION_S__", str(duration_s))
        .replace("__SETUP_BODY__", _indent(fn.setup_body))
        .replace("__REQUEST_BODY__", _indent(fn.request_body))
        .replace("__INVARIANT_BODY__", _indent(fn.invariant_body))
    )
    compile(script, "attack.py", "exec")
    return script


async def write_attack(
    finding: Finding,
    files: dict[str, str],
    llm: ModelClient,
    sink: EventSink,
    *,
    reference: AttackFunctions | None = None,
) -> AttackFunctions:
    """Model attack (one regeneration on rejection) → else the sample's reference attack → else raise."""
    if finding.chaos is None:
        raise AttackRejected(f"finding {finding.id} has no chaos plan")
    messages = _messages(finding, files)
    for attempt in (1, 2):
        try:
            fn = await llm.complete_json("attacker", messages, AttackFunctions, timeout_s=ATTACKER_TIMEOUT_S)
        except ModelUnavailable as exc:
            await note(sink, "warning", f"Attack writer unavailable for {finding.id}: {exc}")
            break
        try:
            validate_functions(fn)
            render_attack(fn, port=8080, concurrency=1, duration_s=1)
            return fn
        except (AttackRejected, SyntaxError) as exc:
            await note(sink, "warning", f"Attack for {finding.id} rejected (attempt {attempt}): {exc}")
            messages = [
                *messages,
                {"role": "assistant", "content": fn.model_dump_json()},
                {"role": "user", "content": f"The validator rejected that: {exc}. Fix it and resend."},
            ]
    if reference is not None:
        validate_functions(reference)  # the reference attack obeys the same rules
        await note(sink, "info", f"Using the sample's reference attack for {finding.id}")
        return reference
    raise AttackRejected(f"no valid attack for {finding.id}")


def _indent(body: str) -> str:
    return textwrap.indent(textwrap.dedent(body).strip("\n"), "    ")


def _messages(finding: Finding, files: dict[str, str]) -> list[dict]:
    relevant = {p: c for p, c in files.items() if p.endswith(".py")}
    user = {
        "finding": finding.model_dump(
            include={"title", "category", "file", "line_start", "line_end", "explanation", "chaos"}
        ),
        "files": relevant,
    }
    return [
        {"role": "system", "content": PROMPTS["attacker_system"]},
        {"role": "user", "content": json.dumps(user)},
    ]
