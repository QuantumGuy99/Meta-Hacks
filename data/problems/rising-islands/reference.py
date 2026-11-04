def islands_after_each(rows: int, cols: int, adds: list[list[int]]) -> list[int]:
    parent: dict[tuple[int, int], tuple[int, int]] = {}

    def find(cell):
        while parent[cell] != cell:
            parent[cell] = parent[parent[cell]]
            cell = parent[cell]
        return cell

    islands = 0
    result = []
    for r, c in adds:
        cell = (r, c)
        if cell not in parent:
            parent[cell] = cell
            islands += 1
            for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if (nr, nc) in parent:
                    a, b = find(cell), find((nr, nc))
                    if a != b:
                        parent[a] = b
                        islands -= 1
        result.append(islands)
    return result
