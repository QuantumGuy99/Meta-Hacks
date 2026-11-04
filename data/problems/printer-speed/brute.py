def min_print_speed(pages: list[int], h: int) -> int:
    speed = 1
    while sum(-(-p // speed) for p in pages) > h:
        speed += 1
    return speed
