import random


def generate(rng: random.Random) -> list:
    pool = ["#run", "#eat", "#code", "#art", "#jazz"]
    return [[rng.choice(pool) for _ in range(rng.randint(0, 14))], rng.randint(1, 6)]
