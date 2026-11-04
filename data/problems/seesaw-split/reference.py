def balance_point(weights: list[int]) -> int:
    total = sum(weights)
    left = 0
    for i, weight in enumerate(weights):
        if left == total - left - weight:
            return i
        left += weight
    return -1
