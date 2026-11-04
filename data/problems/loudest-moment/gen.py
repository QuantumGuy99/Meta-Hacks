import random


def generate(rng: random.Random) -> list:
    readings = [rng.randint(0, 9) for _ in range(rng.randint(0, 12))]
    return [readings, rng.randint(1, 5)]
