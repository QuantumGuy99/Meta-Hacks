"""Model roles: each role's model, reasoning effort, timeout and model fallbacks (PLAN §15.1, §21).

Model ids live only in this file (PLAN §22 rule 3). Only model fallbacks are listed here; the non-model
fallbacks (skip the tick, canned text, flaws.json, the metrics template) are the caller's job after it
catches `llm.AllModelsFailed`.
"""

from dataclasses import dataclass
from typing import Literal

ModelRole = Literal[
    "analyzer",
    "interviewer",
    "classifier",
    "complexity",
    "conversation",
    "grill_eval",
    "grill_check",
    "audit",
    "report",
    "attacker",
    "drafter",
    "vision",
]
# "none" returns 400 on Spark and Wonder (PLAN §15.2).
Effort = Literal["minimal", "low", "medium", "high", "xhigh", "max"]
Provider = Literal["meta", "baseten"]

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
    model: str | None  # None: the provider's configured model
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


# reasoning_effort support on Baseten is unverified (V6), so it never sends one.
_SPARK_OPEN = ModelTarget("baseten", SPARK_OPEN, None)

# Live roles stay on fast Spark. One-shot roles use the strongest setting that reliably fits their timeout
# (PLAN §15.1). Audit: Wonder xhigh, 44-60 s. Attacker, timed on the real prompt on 2026-10-28: Spark high
# p50 26 s (max 30 s, so it timed out against its 30 s budget), medium 18.5 s, low 6.6 s, every attack valid,
# and at low both full Defense runs broke the app; so it starts at low and falls back to medium. grill_eval:
# medium 4.2 s, low 3.0 s, same points marked; low catches a slow spike before Spark Open does. The report's
# Wonder took 15-21 s on real coding sessions but once ran past 90 s, so each model gets 45 s.
ROLES: dict[ModelRole, RoleSpec] = {
    "analyzer": RoleSpec(_spark("minimal"), timeout_s=12),
    "interviewer": RoleSpec(_spark("low"), timeout_s=6),
    "classifier": RoleSpec(_spark("minimal"), timeout_s=3),
    "complexity": RoleSpec(_spark("low"), timeout_s=8),
    # The interviewer's talk: the warm-up, short replies and check-ins (§9.5). A separate role from `interviewer`
    # (which answers questions) so the strip says what it's doing and its budget can be tuned on its own.
    # Minimal effort: these lines are short and every second of thinking is a pause the candidate hears.
    "conversation": RoleSpec(_spark("minimal"), timeout_s=6),
    # Low, not medium: with two graders checking each other (DEF-13), medium's 11 s on bank-transfer's finding
    # (2026-10-29) bought nothing; low and Wonder low marked the same points in 4-6 s.
    "grill_eval": RoleSpec(_spark("low"), timeout_s=10, fallbacks=(_spark("minimal"), _SPARK_OPEN)),
    # The second grader (DEF-13): a different Meta model, so two must agree. Spark Open (open-weight) takes
    # over once Baseten is configured; until then Wonder at low effort, in parallel with grill_eval.
    "grill_check": RoleSpec(_wonder("low"), timeout_s=15, fallbacks=(_SPARK_OPEN,)),
    "audit": RoleSpec(_wonder("xhigh"), timeout_s=120, fallbacks=(_spark("high"),)),
    "report": RoleSpec(_wonder("high"), timeout_s=45, fallbacks=(_spark("high"),)),
    "attacker": RoleSpec(_spark("low"), timeout_s=30, fallbacks=(_spark("medium"),)),
    "drafter": RoleSpec(_wonder("high"), timeout_s=120, fallbacks=(_spark("medium"), _SPARK_OPEN)),
    "vision": RoleSpec(_spark("low"), timeout_s=10),
}

PRICES: dict[str, Price] = {
    SPARK: Price(1.25, 4.25, cached_input_per_m=0.15),
    SPARK_CONTRIBUTOR: Price(0.10, 0.20),
    WONDER: Price(4.00, 20.00),
}
