"""In-memory account store. Balances are whole dollars."""

START_BALANCE = 100_000
ACCOUNT_COUNT = 10

accounts: dict[str, int] = {}


def seed() -> None:
    accounts.clear()
    accounts.update({f"acct-{i}": START_BALANCE for i in range(ACCOUNT_COUNT)})


def get_balance(account_id: str) -> int:
    return accounts[account_id]


def set_balance(account_id: str, amount: int) -> None:
    accounts[account_id] = amount


def exists(account_id: str) -> bool:
    return account_id in accounts


def total() -> int:
    return sum(accounts.values())


seed()
