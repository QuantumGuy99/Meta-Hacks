"""Live check of the model wrapper: one tiny structured call per role (`python -m crucible.models.smoke`)."""

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Mapping
from typing import get_args

from pydantic import BaseModel

from crucible.models import llm
from crucible.models.registry import ROLES, ModelRole

# A 32x32 solid-blue PNG, so the vision role has an image to look at.
_IMAGE = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAKklEQVR42mNQSDhAU8QwasGoBaMWjFowasGo"
    "BaMWjFowasGoBaMWDBULAFLBAEyhc/EzAAAAAElFTkSuQmCC"
)
_MESSAGES = [
    {"role": "system", "content": "You are a health check. Reply in the requested JSON format."},
    {"role": "user", "content": "Set ok to true and word to 'pong'."},
]
_ROLE_ENV: dict[ModelRole, str] = {
    "analyzer": "MODEL_ANALYZER",
    "interviewer": "MODEL_INTERVIEWER",
    "grill_eval": "MODEL_GRILL",
    "audit": "MODEL_AUDIT",
    "report": "MODEL_REPORT",
}


class Ping(BaseModel):
    ok: bool
    word: str


def settings_from_env(env: Mapping[str, str]) -> llm.LLMSettings:
    # TODO(S-0): build this from crucible.config.settings once the scaffold lands; env until then.
    return llm.LLMSettings(
        api_key=env.get("MODEL_API_KEY", ""),
        base_url=env.get("META_BASE_URL") or llm.META_BASE_URL,
        use_contributor_models=env.get("USE_CONTRIBUTOR_MODELS", "0") == "1",
        role_models={role: env[name] for role, name in _ROLE_ENV.items() if env.get(name)},
        baseten_base_url=env.get("BASETEN_BASE_URL") or None,
        baseten_api_key=env.get("BASETEN_API_KEY") or None,
        baseten_model=env.get("SPARK_OPEN_MODEL") or None,
    )


async def smoke(wrapper: llm.LLM, roles: list[ModelRole], records: list[llm.CallRecord]) -> bool:
    """Call each role once and print every attempt. True only if no role needed a fallback."""
    all_ok = True
    for role in roles:
        first = len(records)
        images = [_IMAGE] if role == "vision" else []
        try:
            await wrapper.complete_json(role, _MESSAGES, Ping, images=images)
            failed = any(r.error for r in records[first:])
            print(f"{'PASS via fallback' if failed else 'PASS'}  {role}")
            all_ok = all_ok and not failed
        except llm.AllModelsFailed as exc:
            print(f"FAIL  {role}: {exc}")
            all_ok = False
        for r in records[first:]:
            cost = "n/a" if r.cost_usd is None else f"${r.cost_usd:.5f}"
            status = "ok" if r.error is None else r.error
            print(
                f"      {r.model:<34} effort={r.effort} {r.latency_ms:>6} ms "
                f"in={r.prompt_tokens} out={r.completion_tokens} cost={cost} {status}"
            )
    return all_ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--role", action="append", choices=get_args(ModelRole), help="repeatable; default: all"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    env = os.environ
    settings = settings_from_env(env)
    if not settings.api_key:
        sys.exit("MODEL_API_KEY is not set")
    records: list[llm.CallRecord] = []

    async def collect(record: llm.CallRecord) -> None:
        records.append(record)

    wrapper = llm.LLM(settings, on_call=collect)
    roles: list[ModelRole] = args.role or list(ROLES)
    sys.exit(0 if asyncio.run(smoke(wrapper, roles, records)) else 1)


if __name__ == "__main__":
    main()
