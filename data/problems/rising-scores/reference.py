from bisect import bisect_left


def longest_rise(scores: list[int]) -> int:
    tails: list[int] = []  # tails[i] = smallest last score of a rise of length i + 1
    for score in scores:
        i = bisect_left(tails, score)
        if i == len(tails):
            tails.append(score)
        else:
            tails[i] = score
    return len(tails)
