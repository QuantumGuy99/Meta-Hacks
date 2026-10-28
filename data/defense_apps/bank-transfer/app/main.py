"""Wallet API: transfers between accounts, balances and an audit total."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app import ledger, store

app = FastAPI(title="Wallet")


class TransferRequest(BaseModel):
    src: str
    dst: str
    amount: int


@app.post("/transfer")
async def create_transfer(body: TransferRequest):
    try:
        return await ledger.transfer(body.src, body.dst, body.amount)
    except ledger.TransferError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@app.get("/accounts")
async def list_accounts():
    return store.accounts


@app.get("/accounts/{account_id}")
async def get_account(account_id: str):
    if not store.exists(account_id):
        raise HTTPException(404, "no such account")
    return {"id": account_id, "balance": store.get_balance(account_id)}


@app.get("/total")
async def total():
    return {"total": store.total()}


@app.post("/reset")
async def reset():
    store.seed()
    return {"ok": True}
