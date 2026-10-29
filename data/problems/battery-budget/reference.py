def longest_within_budget(usage: list[int], budget: int) -> int:
    best = 0
    total = 0
    left = 0
    for right, amount in enumerate(usage):
        total += amount
        while total > budget:
            total -= usage[left]
            left += 1
        best = max(best, right - left + 1)
    return best
