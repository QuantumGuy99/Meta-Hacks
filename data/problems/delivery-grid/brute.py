def shortest_route(grid: list[str]) -> int:
    # Relax distances until nothing changes (slow but simple).
    rows, cols = len(grid), len(grid[0])
    if grid[0][0] == "#":
        return -1
    inf = float("inf")
    dist = [[inf] * cols for _ in range(rows)]
    dist[0][0] = 0
    changed = True
    while changed:
        changed = False
        for r in range(rows):
            for c in range(cols):
                if grid[r][c] == "#" or dist[r][c] == inf:
                    continue
                for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                    if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == ".":
                        if dist[r][c] + 1 < dist[nr][nc]:
                            dist[nr][nc] = dist[r][c] + 1
                            changed = True
    d = dist[rows - 1][cols - 1]
    return -1 if d == inf else d
