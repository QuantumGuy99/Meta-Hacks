import random


def generate(rng: random.Random) -> list:
    rows, cols = rng.randint(1, 5), rng.randint(1, 5)
    grid = ["".join("#" if rng.random() < 0.3 else "." for _ in range(cols)) for _ in range(rows)]
    return [grid]
