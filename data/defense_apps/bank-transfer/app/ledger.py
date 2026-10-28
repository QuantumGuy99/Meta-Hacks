"""Moves money between accounts."""

from app import fraud, store


class TransferError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


async def transfer(src: str, dst: str, amount: int) -> dict:
    if not store.exists(src) or not store.exists(dst) or src == dst:
        raise TransferError(400, "unknown or identical accounts")
    if amount <= 0:
        raise TransferError(400, "amount must be positive")
    src_balance = store.get_balance(src)
    dst_balance = store.get_balance(dst)
    if src_balance < amount:
        raise TransferError(409, "insufficient funds")
    if await fraud.is_suspicious(src, dst, amount):
        raise TransferError(403, "blocked by fraud check")
    store.set_balance(src, src_balance - amount)
    store.set_balance(dst, dst_balance + amount)
    return {"src": src, "dst": dst, "amount": amount}
