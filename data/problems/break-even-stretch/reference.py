def longest_zero_net(changes: list[int]) -> int:
    first_seen = {0: -1}
    running = 0
    best = 0
    for i, change in enumerate(changes):
        running += change
        if running in first_seen:
            best = max(best, i - first_seen[running])
        else:
            first_seen[running] = i
    return best
