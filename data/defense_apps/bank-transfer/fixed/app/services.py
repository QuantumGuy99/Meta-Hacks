"""Business logic for moving money between accounts."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from .fraud import FraudScreen
from .models import Transfer, TransferRequest
from .store import AccountStore

logger = logging.getLogger(__name__)


class TransferError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class TransferService:
    def __init__(self, store: AccountStore, fraud: FraudScreen) -> None:
        self.store = store
        self.fraud = fraud
        # Guards every read-modify-write of balances. Nothing inside it may
        # await anything that yields (no network calls, no sleeps).
        self._balance_lock = asyncio.Lock()

    async def transfer(self, req: TransferRequest) -> Transfer:
        if req.from_account == req.to_account:
            raise TransferError("Cannot transfer to the same account")

        # Fail fast on unknown accounts before calling the risk service.
        await self.store.get(req.from_account)
        await self.store.get(req.to_account)

        # Screen first. Balances are only read after this await, so the
        # update below never works from a stale copy.
        risk = await self.fraud.screen(req.from_account, req.to_account, req.amount_cents)
        if risk.blocked:
            blocked = self._build_transfer(req, status="blocked", risk_score=risk.score)
            await self.store.record_transfer(blocked)
            raise TransferError(risk.reason or "Transfer blocked", status_code=403)

        # Read, check and write both balances as one atomic step.
        async with self._balance_lock:
            sender = await self.store.get(req.from_account)
            receiver = await self.store.get(req.to_account)
            if sender.balance_cents < req.amount_cents:
                raise TransferError("Insufficient funds", status_code=409)
            sender.balance_cents -= req.amount_cents
            receiver.balance_cents += req.amount_cents
            await self.store.save(sender)
            await self.store.save(receiver)

        transfer = self._build_transfer(req, status="completed", risk_score=risk.score)
        await self.store.record_transfer(transfer)
        logger.info(
            "transfer %s: %s -> %s (%d cents)",
            transfer.id, req.from_account, req.to_account, req.amount_cents,
        )
        return transfer

    @staticmethod
    def _build_transfer(req: TransferRequest, status: str, risk_score: float) -> Transfer:
        return Transfer(
            id=f"txn_{uuid.uuid4().hex[:12]}",
            from_account=req.from_account,
            to_account=req.to_account,
            amount_cents=req.amount_cents,
            memo=req.memo,
            status=status,
            risk_score=risk_score,
            created_at=datetime.now(timezone.utc),
        )
