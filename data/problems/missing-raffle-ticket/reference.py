def missing_ticket(tickets: list[int], n: int) -> int:
    return n * (n + 1) // 2 - sum(tickets)
