import random


def generate(rng: random.Random) -> list:
    commands = []
    for _ in range(rng.randint(0, 10)):
        if rng.random() < 0.4:
            commands.append("undo")
        else:
            word = "".join(rng.choice("ab ") for _ in range(rng.randint(1, 3)))
            commands.append("type " + word)
    return [commands]
