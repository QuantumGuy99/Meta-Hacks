"""Client for the sales data warehouse.

Wraps the warehouse vendor's Python SDK, which is synchronous. Locally we
simulate the query time and return deterministic sample rows.
"""

import random
import time

from .models import Transaction

QUERY_LATENCY_S = 0.2  # typical time for a month-long scan
CATEGORIES = ["groceries", "travel", "software", "hardware", "dining", "services"]
MONTHS = [f"2026-{m:02d}" for m in range(1, 11)]


class WarehouseClient:
    def __init__(self, rows_per_month: int = 400) -> None:
        self.rows_per_month = rows_per_month

    def fetch_transactions(self, month: str) -> list[Transaction]:
        time.sleep(QUERY_LATENCY_S)  # the SDK call blocks until the query finishes
        rng = random.Random(month)
        return [
            Transaction(
                id=f"tx_{month}_{i:05d}",
                month=month,
                category=rng.choice(CATEGORIES),
                amount_cents=rng.randint(500, 250_000),
            )
            for i in range(self.rows_per_month)
        ]
