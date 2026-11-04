import random


def generate(rng: random.Random) -> list:
    n = rng.randint(1, 6)
    deps = [[rng.randrange(n), rng.randrange(n)] for _ in range(rng.randint(0, 7))]
    return [n, [d for d in deps if d[0] != d[1]]]
