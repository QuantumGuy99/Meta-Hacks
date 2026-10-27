"""Model roles: each role's model, reasoning effort, timeout and model fallbacks (PLAN §15.1, §21).

Model ids live only in this file (PLAN §22 rule 3). Only model fallbacks are listed here; the non-model
fallbacks (skip the tick, canned text, flaws.json, the metrics template) are the caller's job after it
catches `llm.AllModelsFailed`.
"""

from dataclasses import dataclass
from typing import Literal

ModelRole = Literal[
    "analyzer", "interviewer", "classifier", "grill_eval", "audit", "report", "attacker", "drafter", "vision"
]
# "none" returns 400 on Spark and Wonder (PLAN §15.2).
Effort = Literal["minimal", "low", "medium", "high", "xhigh", "max"]
Provider = Literal["meta", "baseten", "glimmer"]

SPARK = "muse-spark-1.3"
SPARK_CONTRIBUTOR = "muse-spark-1.3-contributor"
WONDER = "muse-wonder-1.0"
# The hackathon guide says to use this id, not "muse-spark-open" (PLAN §15.1).
SPARK_OPEN = "meta-models/muse-spark-open-1026"

# USE_CONTRIBUTOR_MODELS=1: cheaper, but content may be used for training. Dev with synthetic data only.
CONTRIBUTOR_MODELS: dict[str, str] = {SPARK: SPARK_CONTRIBUTOR}
CONTRIBUTOR_MAX_EFFORT: Effort = "xhigh"  # contributor models don't support "max"


@dataclass(frozen=True, slots=True)
class ModelTarget:
    provider: Provider
    model: str | None  # None: the provider's configured model (Glimmer's id comes from GLIMMER_MODEL, V5)
    effort: Effort | None  # None: don't send reasoning_effort


@dataclass(frozen=True, slots=True)
class RoleSpec:
    primary: ModelTarget
    timeout_s: float
    fallbacks: tuple[ModelTarget, ...] = ()

    @property
    def chain(self) -> tuple[ModelTarget, ...]:
        return (self.primary, *self.fallbacks)


@dataclass(frozen=True, slots=True)
class Price:
    """List price in USD per 1M tokens (PLAN §15.3; re-check before the demo)."""

    input_per_m: float
    output_per_m: float
    cached_input_per_m: float | None = None  # None: cached input is billed at the input price


def _spark(effort: Effort) -> ModelTarget:
    return ModelTarget("meta", SPARK, effort)


def _wonder(effort: Effort) -> ModelTarget:
    return ModelTarget("meta", WONDER, effort)


# reasoning_effort support on Baseten and on the Glimmer host is unverified (V5, V6), so neither sends it.
_SPARK_OPEN = ModelTarget("baseten", SPARK_OPEN, None)
_GLIMMER = ModelTarget("glimmer", None, None)

ROLES: dict[ModelRole, RoleSpec] = {
    "analyzer": RoleSpec(_spark("low"), timeout_s=12),
    "interviewer": RoleSpec(_spark("low"), timeout_s=6),
    "classifier": RoleSpec(_spark("minimal"), timeout_s=3),
    "grill_eval": RoleSpec(_spark("medium"), timeout_s=10, fallbacks=(_SPARK_OPEN,)),
    "audit": RoleSpec(_wonder("high"), timeout_s=120, fallbacks=(_spark("high"),)),
    "report": RoleSpec(_wonder("high"), timeout_s=90, fallbacks=(_spark("high"),)),
    "attacker": RoleSpec(_GLIMMER, timeout_s=30, fallbacks=(_spark("medium"),)),
    "drafter": RoleSpec(_spark("medium"), timeout_s=60, fallbacks=(_SPARK_OPEN,)),
    "vision": RoleSpec(_spark("low"), timeout_s=10),
}

PRICES: dict[str, Price] = {
    SPARK: Price(1.25, 4.25, cached_input_per_m=0.15),
    SPARK_CONTRIBUTOR: Price(0.10, 0.20),
    WONDER: Price(4.00, 20.00),
}
