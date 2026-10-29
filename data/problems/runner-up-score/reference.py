def runner_up(scores: list[int]) -> int:
    best = -1
    second = -1
    for score in scores:
        if score > best:
            second = best
            best = score
        elif best > score > second:
            second = score
    return second
