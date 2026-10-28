"""Checkout: assigns the best open seat in a section and charges for it."""

import uuid
from datetime import datetime, timezone

from .models import CheckoutRequest, Order, Seat, SeatBlock
from .payments import PaymentDeclined, PaymentGateway
from .venue import Venue


class CheckoutError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class CheckoutService:
    def __init__(self, venue: Venue, payments: PaymentGateway) -> None:
        self.venue = venue
        self.payments = payments

    async def checkout(self, req: CheckoutRequest) -> Order:
        if not self.venue.has_section(req.section):
            raise CheckoutError(f"Unknown section {req.section}", status_code=404)

        seat = await self.venue.first_available(req.section)
        if seat is None:
            raise CheckoutError("Section is sold out", status_code=409)

        try:
            payment_id = await self.payments.authorize(req.buyer_email, seat.price_cents)
        except PaymentDeclined as exc:
            raise CheckoutError(str(exc), status_code=402)

        seat.status = "sold"
        await self.venue.save_seat(seat)

        order = Order(
            id=f"ord_{uuid.uuid4().hex[:12]}",
            seat_id=seat.id,
            section=seat.section,
            buyer_email=req.buyer_email,
            price_cents=seat.price_cents,
            payment_id=payment_id,
            created_at=datetime.now(timezone.utc),
        )
        await self.venue.record_order(order)
        return order


def find_adjacent_blocks(seats: list[Seat], party_size: int, limit: int = 5) -> list[SeatBlock]:
    """Blocks of `party_size` open seats next to each other in the same row."""
    available = [s for s in seats if s.status == "available"]
    blocks: list[SeatBlock] = []
    for seat in available:
        block = [seat]
        while len(block) < party_size:
            neighbour = None
            for other in available:
                if other.row == block[-1].row and other.number == block[-1].number + 1:
                    neighbour = other
                    break
            if neighbour is None:
                break
            block.append(neighbour)
        if len(block) == party_size:
            blocks.append(
                SeatBlock(
                    row=seat.row,
                    seat_ids=[s.id for s in block],
                    total_cents=sum(s.price_cents for s in block),
                )
            )
    blocks.sort(key=lambda b: (b.row, b.seat_ids[0]))
    return blocks[:limit]
