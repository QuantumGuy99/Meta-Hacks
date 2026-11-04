def min_print_speed(pages: list[int], h: int) -> int:
    def hours_needed(speed: int) -> int:
        return sum((p + speed - 1) // speed for p in pages)

    lo, hi = 1, max(pages)
    while lo < hi:
        mid = (lo + hi) // 2
        if hours_needed(mid) <= h:
            hi = mid
        else:
            lo = mid + 1
    return lo
