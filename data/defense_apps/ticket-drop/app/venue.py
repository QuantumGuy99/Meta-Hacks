"""In-memory seat map and order book for one event.

Riverside Arena: 100 sections x 50 rows x 20 seats = 100,000 seats.
The interface is async so it can move to a real database later.
"""

from .models import Order, Seat

SECTIONS = [f"S{n:03d}" for n in range(1, 101)]
ROWS_PER_SECTION = 50
SEATS_PER_ROW = 20


def _price_for_row(row: int) -> int:
    # Front rows cost more: $120 in row 1 down to $45 in the back.
    return 12_000 - (row - 1) * 150


class Venue:
    def __init__(self) -> None:
        self._sections: dict[str, list[Seat]] = {}
        self._seats: dict[str, Seat] = {}
        # The event's sales ledger. Each order is for one seat, so it's bounded
        # by the venue's capacity; indexed by buyer for fast lookups.
        self._orders_by_email: dict[str, list[Order]] = {}
        self._orders_by_section: dict[str, int] = {}

    def build(self) -> None:
        for section in SECTIONS:
            seats = []
            for row in range(1, ROWS_PER_SECTION + 1):
                for number in range(1, SEATS_PER_ROW + 1):
                    seat = Seat(
                        id=f"{section}-R{row:02d}-{number:02d}",
                        section=section,
                        row=row,
                        number=number,
                        price_cents=_price_for_row(row),
                    )
                    seats.append(seat)
                    self._seats[seat.id] = seat
            self._sections[section] = seats

    def has_section(self, section: str) -> bool:
        return section in self._sections

    async def first_available(self, section: str) -> Seat | None:
        """Best open seat in a section (front row first, then left to right)."""
        for seat in self._sections.get(section, []):
            if seat.status == "available":
                return seat.model_copy()
        return None

    async def save_seat(self, seat: Seat) -> None:
        stored = self._seats[seat.id]
        stored.status = seat.status

    async def seats_in_section(self, section: str) -> list[Seat]:
        return [s.model_copy() for s in self._sections.get(section, [])]

    async def record_order(self, order: Order) -> None:
        self._orders_by_email.setdefault(order.buyer_email, []).append(order)
        self._orders_by_section[order.section] = self._orders_by_section.get(order.section, 0) + 1

    async def orders_for(self, email: str) -> list[Order]:
        return list(self._orders_by_email.get(email, []))

    async def summary(self) -> list[dict]:
        return [
            {
                "section": section,
                "capacity": len(seats),
                "seats_sold": sum(1 for s in seats if s.status == "sold"),
                "orders": self._orders_by_section.get(section, 0),
            }
            for section, seats in self._sections.items()
        ]
