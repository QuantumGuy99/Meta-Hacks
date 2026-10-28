"""Seatly: ticket checkout for Riverside Arena."""

from fastapi import FastAPI, HTTPException, Query

from .checkout import CheckoutError, CheckoutService, find_adjacent_blocks
from .models import CheckoutRequest, Order, SeatBlock, SectionSummary
from .payments import PaymentGateway
from .venue import Venue

app = FastAPI(title="Seatly", version="0.9.0")

venue = Venue()
venue.build()
service = CheckoutService(venue, PaymentGateway())


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/sections", response_model=list[SectionSummary])
async def list_sections() -> list[dict]:
    return await venue.summary()


@app.get("/sections/{section}/recommendations", response_model=list[SeatBlock])
async def recommend_seats(
    section: str, party_size: int = Query(default=2, ge=1, le=8)
) -> list[SeatBlock]:
    if not venue.has_section(section):
        raise HTTPException(status_code=404, detail=f"Unknown section {section}")
    seats = await venue.seats_in_section(section)
    return find_adjacent_blocks(seats, party_size)


@app.post("/checkout", response_model=Order, status_code=201)
async def checkout(req: CheckoutRequest) -> Order:
    try:
        return await service.checkout(req)
    except CheckoutError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@app.get("/orders", response_model=list[Order])
async def orders_for_buyer(email: str = Query(min_length=3)) -> list[Order]:
    return await venue.orders_for(email)
