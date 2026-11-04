import heapq


def build_order(n: int, deps: list[list[int]]) -> list[int]:
    unlocks = [[] for _ in range(n)]
    waiting_on = [0] * n
    for before, after in deps:
        unlocks[before].append(after)
        waiting_on[after] += 1
    ready = [task for task in range(n) if waiting_on[task] == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        task = heapq.heappop(ready)
        order.append(task)
        for nxt in unlocks[task]:
            waiting_on[nxt] -= 1
            if waiting_on[nxt] == 0:
                heapq.heappush(ready, nxt)
    return order if len(order) == n else []
