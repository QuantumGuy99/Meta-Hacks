def fastest_delivery(n: int, roads: list[list[int]]) -> int:
    # Bellman-Ford: relax every road n times.
    inf = float("inf")
    dist = [inf] * n
    dist[0] = 0
    for _ in range(n):
        for start, end, minutes in roads:
            if dist[start] + minutes < dist[end]:
                dist[end] = dist[start] + minutes
    return -1 if dist[n - 1] == inf else dist[n - 1]
