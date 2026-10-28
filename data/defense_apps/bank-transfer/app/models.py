"""Request and response schemas for the Ledgerly transfer API."""

from datetime import datetime

from pydantic import BaseModel, Field


class Account(BaseModel):
    id: str
    owner: str
    balance_cents: int = Field(ge=0)


class AccountOut(BaseModel):
    id: str
    owner: str
    balance_cents: int
    balance: str  # human-readable, e.g. "$1,000.00"


class TransferRequest(BaseModel):
    from_account: str
    to_account: str
    amount_cents: int = Field(gt=0, le=1_000_000)
    memo: str | None = Field(default=None, max_length=140)


class Transfer(BaseModel):
    id: str
    from_account: str
    to_account: str
    amount_cents: int
    memo: str | None = None
    status: str  # "completed" or "blocked"
    risk_score: float
    created_at: datetime
