import random


def generate(rng: random.Random) -> list:
    word = lambda: "".join(rng.choice("abc") for _ in range(rng.randint(0, 5)))
    return [word(), word()]
