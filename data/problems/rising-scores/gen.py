import random


def generate(rng: random.Random) -> list:
    return [[rng.randint(0, 9) for _ in range(rng.randint(0, 12))]]
