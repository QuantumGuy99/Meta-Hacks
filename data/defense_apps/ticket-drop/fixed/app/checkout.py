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

        # Find and hold the seat with no await in between, so two checkouts
        # can never be handed the same seat.
        seat = await self.venue.first_available(req.section)
        if seat is None:
            raise CheckoutError("Section is sold out", status_code=409)
        seat.status = "held"
        await self.venue.save_seat(seat)

        try:
            payment_id = await self.payments.authorize(req.buyer_email, seat.price_cents)
        except PaymentDeclined as exc:
            seat.status = "available"
            await self.venue.save_seat(seat)
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
    open_seats = {(s.row, s.number): s for s in seats if s.status == "available"}
    blocks: list[SeatBlock] = []
    for (row, number), seat in sorted(open_seats.items()):
        block = [seat]
        while len(block) < party_size:
            neighbour = open_seats.get((row, block[-1].number + 1))
            if neighbour is None:
                break
            block.append(neighbour)
        if len(block) == party_size:
            blocks.append(
                SeatBlock(
                    row=row,
                    seat_ids=[s.id for s in block],
                    total_cents=sum(s.price_cents for s in block),
                )
            )
            if len(blocks) == limit:
                break
    return blocks
