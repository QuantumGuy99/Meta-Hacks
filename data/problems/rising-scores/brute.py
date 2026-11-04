def longest_rise(scores: list[int]) -> int:
    best = [1] * len(scores)
    for i in range(len(scores)):
        for j in range(i):
            if scores[j] < scores[i]:
                best[i] = max(best[i], best[j] + 1)
    return max(best, default=0)
