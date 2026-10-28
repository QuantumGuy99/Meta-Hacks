import random


def generate(rng: random.Random) -> list:
    bookings = []
    for _ in range(rng.randint(0, 7)):
        start = rng.randint(0, 20)
        bookings.append([start, start + rng.randint(1, 5)])
    return [bookings]
