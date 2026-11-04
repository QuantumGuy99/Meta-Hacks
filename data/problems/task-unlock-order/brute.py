from itertools import permutations


def build_order(n: int, deps: list[list[int]]) -> list[int]:
    # permutations() yields orders smallest-first, so the first valid one is the answer.
    for order in permutations(range(n)):
        position = {task: i for i, task in enumerate(order)}
        if all(position[a] < position[b] for a, b in deps):
            return list(order)
    return []
