def shortest_sampler(songs: list[str], required: list[str]) -> int:
    needed = set(required)
    if not needed:
        return 0

    counts = {genre: 0 for genre in needed}
    covered = 0
    best = -1
    left = 0

    for right, genre in enumerate(songs):
        if genre in counts:
            counts[genre] += 1
            if counts[genre] == 1:
                covered += 1

        while covered == len(needed):
            length = right - left + 1
            if best == -1 or length < best:
                best = length
            leaving = songs[left]
            if leaving in counts:
                counts[leaving] -= 1
                if counts[leaving] == 0:
                    covered -= 1
            left += 1

    return best
