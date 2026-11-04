import random


def generate(rng: random.Random) -> list:
    pages = [rng.randint(1, 30) for _ in range(rng.randint(1, 6))]
    return [pages, rng.randint(len(pages), len(pages) + 15)]
