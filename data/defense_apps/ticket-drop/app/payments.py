"""Card payments.

In production this calls the payment provider's authorize endpoint. Locally
we simulate its latency so checkout behaves like it does in production.
"""

import asyncio
import uuid

PROVIDER_LATENCY_S = 0.03


class PaymentDeclined(Exception):
    pass


class PaymentGateway:
    async def authorize(self, buyer_email: str, amount_cents: int) -> str:
        # Round trip to the payment provider.
        await asyncio.sleep(PROVIDER_LATENCY_S)
        if amount_cents <= 0:
            raise PaymentDeclined("Invalid amount")
        return f"pay_{uuid.uuid4().hex[:12]}"
