import random


def generate(rng: random.Random) -> list:
    n = rng.randint(1, 6)
    roads = [[rng.randrange(n), rng.randrange(n), rng.randint(0, 9)] for _ in range(rng.randint(0, 10))]
    return [n, roads]
