import heapq


def fastest_delivery(n: int, roads: list[list[int]]) -> int:
    graph = [[] for _ in range(n)]
    for start, end, minutes in roads:
        graph[start].append((end, minutes))
    best = [None] * n
    best[0] = 0
    heap = [(0, 0)]
    while heap:
        time, stop = heapq.heappop(heap)
        if time > best[stop]:
            continue  # an outdated entry; a faster route was already found
        if stop == n - 1:
            return time
        for nxt, minutes in graph[stop]:
            candidate = time + minutes
            if best[nxt] is None or candidate < best[nxt]:
                best[nxt] = candidate
                heapq.heappush(heap, (candidate, nxt))
    return -1
