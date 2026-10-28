import random


def generate(rng: random.Random) -> list:
    genres = ["pop", "rock", "jazz", "rap", "soul"]
    songs = [rng.choice(genres) for _ in range(rng.randint(0, 15))]
    required = [rng.choice(genres) for _ in range(rng.randint(0, 4))]
    return [songs, required]
