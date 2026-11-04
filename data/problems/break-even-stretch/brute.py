def longest_zero_net(changes: list[int]) -> int:
    best = 0
    for start in range(len(changes)):
        for end in range(start, len(changes)):
            if sum(changes[start:end + 1]) == 0:
                best = max(best, end - start + 1)
    return best
