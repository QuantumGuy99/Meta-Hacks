def islands_after_each(rows: int, cols: int, adds: list[list[int]]) -> list[int]:
    land = set()
    result = []
    for r, c in adds:
        land.add((r, c))
        seen = set()
        count = 0
        for start in land:
            if start in seen:
                continue
            count += 1
            stack = [start]
            seen.add(start)
            while stack:
                cr, cc = stack.pop()
                for nxt in ((cr + 1, cc), (cr - 1, cc), (cr, cc + 1), (cr, cc - 1)):
                    if nxt in land and nxt not in seen:
                        seen.add(nxt)
                        stack.append(nxt)
        result.append(count)
    return result
