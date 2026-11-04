import random


def generate(rng: random.Random) -> list:
    return [[rng.randint(-3, 3) for _ in range(rng.randint(0, 12))]]
