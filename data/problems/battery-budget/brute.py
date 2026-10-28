def longest_within_budget(usage: list[int], budget: int) -> int:
    best = 0
    for start in range(len(usage)):
        for end in range(start, len(usage)):
            if sum(usage[start:end + 1]) <= budget:
                best = max(best, end - start + 1)
    return best
