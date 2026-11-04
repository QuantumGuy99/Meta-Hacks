def count_pairs(values: list[int], price: int) -> int:
    seen: dict[int, int] = {}
    pairs = 0
    for value in values:
        pairs += seen.get(price - value, 0)
        seen[value] = seen.get(value, 0) + 1
    return pairs
