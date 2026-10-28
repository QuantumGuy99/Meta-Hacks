import random


def generate(rng: random.Random) -> list:
    letters = "abc"  # a small alphabet so groups actually collide
    n = rng.randint(0, 12)
    codes = ["".join(rng.choice(letters) for _ in range(rng.randint(0, 4))) for _ in range(n)]
    return [codes]
