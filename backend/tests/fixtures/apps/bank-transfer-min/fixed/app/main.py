"""Tiny wallet API (test fixture for the Defense pipeline; the real demo app is data/defense_apps/bank-transfer)."""

import asyncio
import random

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Wallet")

START_BALANCE = 100_000
accounts: dict[str, int] = {}
ledger_lock = asyncio.Lock()


def _seed() -> None:
    accounts.clear()
    accounts.update({f"acct-{i}": START_BALANCE for i in range(10)})


_seed()


class Transfer(BaseModel):
    src: str
    dst: str
    amount: int


async def fraud_check(t: Transfer) -> None:
    # Pretend to call a fraud-scoring service.
    await asyncio.sleep(random.uniform(0.01, 0.03))


@app.post("/transfer")
async def transfer(t: Transfer):
    if t.src not in accounts or t.dst not in accounts or t.src == t.dst:
        raise HTTPException(400, "bad accounts")
    if t.amount <= 0:
        raise HTTPException(400, "bad amount")
    await fraud_check(t)
    async with ledger_lock:
        if accounts[t.src] < t.amount:
            raise HTTPException(409, "insufficient funds")
        accounts[t.src] -= t.amount
        accounts[t.dst] += t.amount
    return {"ok": True}


@app.get("/accounts")
async def list_accounts():
    return accounts


@app.get("/total")
async def total():
    return {"total": sum(accounts.values())}


@app.post("/reset")
async def reset():
    _seed()
    return {"ok": True}
