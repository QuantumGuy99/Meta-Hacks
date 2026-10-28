"""Ledgerly: a small money-transfer API."""

from fastapi import FastAPI, HTTPException, Query

from .fraud import FraudScreen
from .models import Account, AccountOut, Transfer, TransferRequest
from .services import TransferError, TransferService
from .store import AccountNotFound, AccountStore

app = FastAPI(title="Ledgerly Transfers", version="1.2.0")

store = AccountStore()
store.seed()
service = TransferService(store, FraudScreen())


def to_out(account: Account) -> AccountOut:
    return AccountOut(
        id=account.id,
        owner=account.owner,
        balance_cents=account.balance_cents,
        balance=f"${account.balance_cents / 100:,.2f}",
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/accounts", response_model=list[AccountOut])
async def list_accounts() -> list[AccountOut]:
    accounts = await store.list_accounts()
    return [to_out(a) for a in accounts]


@app.get("/accounts/{account_id}", response_model=AccountOut)
async def get_account(account_id: str) -> AccountOut:
    try:
        account = await store.get(account_id)
    except AccountNotFound:
        raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
    return to_out(account)


@app.post("/transfer", response_model=Transfer, status_code=201)
async def create_transfer(req: TransferRequest) -> Transfer:
    try:
        return await service.transfer(req)
    except AccountNotFound as exc:
        raise HTTPException(status_code=404, detail=f"Account {exc} not found")
    except TransferError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@app.get("/transfers", response_model=list[Transfer])
async def list_transfers(limit: int = Query(default=50, ge=1, le=500)) -> list[Transfer]:
    return await store.list_transfers(limit)


@app.get("/transfers/{transfer_id}", response_model=Transfer)
async def get_transfer(transfer_id: str) -> Transfer:
    transfer = await store.get_transfer(transfer_id)
    if transfer is None:
        raise HTTPException(status_code=404, detail=f"Transfer {transfer_id} not found")
    return transfer
