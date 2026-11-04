def count_pairs(values: list[int], price: int) -> int:
    pairs = 0
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            if values[i] + values[j] == price:
                pairs += 1
    return pairs
