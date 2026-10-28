"""Schemas for the Tallyboard reporting API."""

from datetime import datetime

from pydantic import BaseModel


class Transaction(BaseModel):
    id: str
    month: str  # "2026-09"
    category: str
    amount_cents: int


class CategoryTotal(BaseModel):
    category: str
    count: int
    total_cents: int


class MonthlyReport(BaseModel):
    month: str
    transactions: int
    total_cents: int
    by_category: list[CategoryTotal]
    largest_cents: int
    generated_at: datetime


class MonthComparison(BaseModel):
    month: str
    previous: str
    total_cents: int
    previous_total_cents: int
    change_pct: float | None
    categories_up: list[str]
    categories_down: list[str]
