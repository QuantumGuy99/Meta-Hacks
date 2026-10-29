import random


def generate(rng: random.Random) -> list:
    return [[rng.randint(1, 6) for _ in range(rng.randint(0, 12))]]
