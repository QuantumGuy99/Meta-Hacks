import random


def generate(rng: random.Random) -> list:
    usage = [rng.randint(0, 9) for _ in range(rng.randint(0, 12))]
    return [usage, rng.randint(0, 20)]
