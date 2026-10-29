def next_taller_distance(heights: list[int]) -> list[int]:
    answer = [0] * len(heights)
    waiting = []  # indexes still looking for a taller building, heights not increasing
    for i, height in enumerate(heights):
        while waiting and heights[waiting[-1]] < height:
            j = waiting.pop()
            answer[j] = i - j
        waiting.append(i)
    return answer
