def merge_bookings(bookings: list[list[int]]) -> list[list[int]]:
    # Mark every covered half-hour slot, treating touching bookings as joined.
    if not bookings:
        return []
    points = set()
    for start, end in bookings:
        for t in range(2 * start, 2 * end + 1):
            points.add(t)
    result = []
    for t in sorted(points):
        if result and t == result[-1][1] + 1:
            result[-1][1] = t
        else:
            result.append([t, t])
    return [[lo // 2, hi // 2] for lo, hi in result]
