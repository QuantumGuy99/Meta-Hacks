"""Configures the shared model wrapper from settings, for the app (`main.py`) and the Defense terminal
harness (`python -m crucible.defense`), so both run with the same models (#35)."""

from __future__ import annotations

import logging

from crucible.config import Settings
from crucible.models import llm

logger = logging.getLogger(__name__)

# Env var → model role override for the wrapper (PLAN §19.2). Roles not listed keep the registry default.
ROLE_ENV: dict[str, str] = {
    "analyzer": "MODEL_ANALYZER",
    "interviewer": "MODEL_INTERVIEWER",
    "grill_eval": "MODEL_GRILL",
    "audit": "MODEL_AUDIT",
    "report": "MODEL_REPORT",
}


def configure_models(s: Settings) -> llm.LLM | None:
    """The process-wide wrapper, or None without a key (every model stage then takes its fallback)."""
    if not s.has_meta_key:
        logger.warning("MODEL_API_KEY is empty: model calls will fail until it's set in .env")
        return None
    return llm.configure(
        llm.LLMSettings(
            api_key=s.MODEL_API_KEY,
            base_url=s.META_BASE_URL,
            use_contributor_models=s.USE_CONTRIBUTOR_MODELS,
            role_models={role: getattr(s, env) for role, env in ROLE_ENV.items()},
            baseten_base_url=s.BASETEN_BASE_URL or None,
            baseten_api_key=s.BASETEN_API_KEY or None,
            baseten_model=s.SPARK_OPEN_MODEL or None,
        )
    )
