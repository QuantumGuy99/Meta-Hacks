def shortest_sampler(songs: list[str], required: list[str]) -> int:
    # Slow but obviously correct: check every stretch.
    needed = set(required)
    if not needed:
        return 0
    best = -1
    for start in range(len(songs)):
        for end in range(start, len(songs)):
            if needed <= set(songs[start:end + 1]):
                length = end - start + 1
                if best == -1 or length < best:
                    best = length
                break
    return best
