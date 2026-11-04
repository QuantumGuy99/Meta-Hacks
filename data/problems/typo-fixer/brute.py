def min_edits(a: str, b: str) -> int:
    # Plain recursion over the three edits (exponential, fine for short words).
    if not a:
        return len(b)
    if not b:
        return len(a)
    if a[0] == b[0]:
        return min_edits(a[1:], b[1:])
    return 1 + min(min_edits(a[1:], b), min_edits(a, b[1:]), min_edits(a[1:], b[1:]))
