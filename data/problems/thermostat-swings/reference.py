def count_big_swings(temps: list[int], k: int) -> int:
    swings = 0
    for i in range(1, len(temps)):
        if abs(temps[i] - temps[i - 1]) > k:
            swings += 1
    return swings
