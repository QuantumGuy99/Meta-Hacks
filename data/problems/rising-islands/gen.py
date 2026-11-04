import random


def generate(rng: random.Random) -> list:
    rows, cols = rng.randint(1, 4), rng.randint(1, 4)
    adds = [[rng.randrange(rows), rng.randrange(cols)] for _ in range(rng.randint(0, 10))]
    return [rows, cols, adds]
