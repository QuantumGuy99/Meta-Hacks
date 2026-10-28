"""In-memory storage for accounts and transfers.

Keeps the service dependency-free for local development. The interface is
async so it can be swapped for a real database later without touching the
routes or the service layer.
"""

from .models import Account, Transfer

STARTING_BALANCE_CENTS = 10_000_000  # $100,000.00

SEED_ACCOUNTS = [
    ("acc_001", "Amara Okafor"),
    ("acc_002", "Bruno Silva"),
    ("acc_003", "Chen Wei"),
    ("acc_004", "Dana Kowalski"),
    ("acc_005", "Elif Yilmaz"),
    ("acc_006", "Farah Haddad"),
    ("acc_007", "Gabriel Moreau"),
    ("acc_008", "Hana Sato"),
    ("acc_009", "Ivan Petrov"),
    ("acc_010", "Jasmine Reyes"),
]


class AccountNotFound(Exception):
    """Raised when an account id doesn't exist."""


class AccountStore:
    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._transfers: list[Transfer] = []

    def seed(self) -> None:
        """Load the demo accounts, each starting with $100,000."""
        for account_id, owner in SEED_ACCOUNTS:
            self._accounts[account_id] = Account(
                id=account_id, owner=owner, balance_cents=STARTING_BALANCE_CENTS
            )

    async def get(self, account_id: str) -> Account:
        account = self._accounts.get(account_id)
        if account is None:
            raise AccountNotFound(account_id)
        # Return a copy so callers can't mutate storage by accident.
        return account.model_copy()

    async def save(self, account: Account) -> None:
        self._accounts[account.id] = account.model_copy()

    async def list_accounts(self) -> list[Account]:
        return [a.model_copy() for a in self._accounts.values()]

    async def record_transfer(self, transfer: Transfer) -> None:
        self._transfers.append(transfer)

    async def list_transfers(self, limit: int = 50) -> list[Transfer]:
        return list(reversed(self._transfers[-limit:]))

    async def get_transfer(self, transfer_id: str) -> Transfer | None:
        for transfer in self._transfers:
            if transfer.id == transfer_id:
                return transfer
        return None
