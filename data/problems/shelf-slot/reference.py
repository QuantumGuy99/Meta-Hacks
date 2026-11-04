def shelf_slot(ids: list[int], new_id: int) -> int:
    lo, hi = 0, len(ids)
    while lo < hi:
        mid = (lo + hi) // 2
        if ids[mid] < new_id:
            lo = mid + 1
        else:
            hi = mid
    return lo
