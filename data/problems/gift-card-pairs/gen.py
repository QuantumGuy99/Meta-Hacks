import random


def generate(rng: random.Random) -> list:
    return [[rng.randint(-5, 10) for _ in range(rng.randint(0, 12))], rng.randint(-5, 15)]
