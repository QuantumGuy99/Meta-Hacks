"""Client for the fraud-scoring service. Simulated here: a short network round trip."""

import asyncio
import random

FRAUD_LIMIT = 50_000


async def score(src: str, dst: str, amount: int) -> float:
    await asyncio.sleep(random.uniform(0.01, 0.03))  # the round trip to the scoring service
    return min(1.0, amount / FRAUD_LIMIT)


async def is_suspicious(src: str, dst: str, amount: int) -> bool:
    return await score(src, dst, amount) >= 1.0
