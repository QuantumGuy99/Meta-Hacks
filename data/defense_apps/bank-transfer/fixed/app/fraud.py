"""Fraud screening for outgoing transfers.

In production this calls the risk-scoring service over HTTP. Locally we
simulate its latency and scoring so the transfer flow behaves realistically.
"""

import asyncio
from dataclasses import dataclass

RISK_SERVICE_LATENCY_S = 0.03  # typical round trip to the risk service
BLOCK_THRESHOLD = 0.9


@dataclass
class RiskResult:
    score: float
    blocked: bool
    reason: str | None = None


class FraudScreen:
    async def screen(self, from_account: str, to_account: str, amount_cents: int) -> RiskResult:
        # Simulates the network call to the risk service.
        await asyncio.sleep(RISK_SERVICE_LATENCY_S)
        score = self._score(amount_cents)
        if score >= BLOCK_THRESHOLD:
            return RiskResult(score=score, blocked=True, reason="Amount exceeds risk limit")
        return RiskResult(score=score, blocked=False)

    @staticmethod
    def _score(amount_cents: int) -> float:
        # Larger transfers are riskier; $10,000 and up scores 1.0.
        return round(min(1.0, amount_cents / 1_000_000), 3)
