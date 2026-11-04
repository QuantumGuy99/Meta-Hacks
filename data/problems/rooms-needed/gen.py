import random


def generate(rng: random.Random) -> list:
    meetings = []
    for _ in range(rng.randint(0, 8)):
        start = rng.randint(0, 12)
        meetings.append([start, start + rng.randint(1, 5)])
    return [meetings]
