"""Schemas for the Seatly ticketing API."""

from datetime import datetime

from pydantic import BaseModel, Field


class Seat(BaseModel):
    id: str  # e.g. "S001-R01-07"
    section: str
    row: int
    number: int
    price_cents: int
    status: str = "available"  # "available", "held" or "sold"


class CheckoutRequest(BaseModel):
    section: str
    buyer_email: str = Field(min_length=3, max_length=254)


class Order(BaseModel):
    id: str
    seat_id: str
    section: str
    buyer_email: str
    price_cents: int
    payment_id: str
    created_at: datetime


class SectionSummary(BaseModel):
    section: str
    capacity: int
    seats_sold: int
    orders: int


class SeatBlock(BaseModel):
    row: int
    seat_ids: list[str]
    total_cents: int
