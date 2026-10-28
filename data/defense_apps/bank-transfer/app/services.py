"""Business logic for moving money between accounts."""

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

    async def transfer(self, req: TransferRequest) -> Transfer:
        if req.from_account == req.to_account:
            raise TransferError("Cannot transfer to the same account")

        sender = await self.store.get(req.from_account)
        receiver = await self.store.get(req.to_account)

        if sender.balance_cents < req.amount_cents:
            raise TransferError("Insufficient funds", status_code=409)

        # Reserve the funds first so the sender can't double-spend while
        # the transfer is being screened.
        sender.balance_cents -= req.amount_cents
        await self.store.save(sender)

        risk = await self.fraud.screen(req.from_account, req.to_account, req.amount_cents)
        if risk.blocked:
            # Release the reservation and record the blocked attempt.
            sender.balance_cents += req.amount_cents
            await self.store.save(sender)
            blocked = self._build_transfer(req, status="blocked", risk_score=risk.score)
            await self.store.record_transfer(blocked)
            raise TransferError(risk.reason or "Transfer blocked", status_code=403)

        # Settle into the receiving account.
        receiver.balance_cents += req.amount_cents
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
