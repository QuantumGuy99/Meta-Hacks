def min_rooms(meetings: list[list[int]]) -> int:
    best = 0
    for start, _ in meetings:
        busy = sum(1 for s, e in meetings if s <= start < e)
        best = max(best, busy)
    return best
