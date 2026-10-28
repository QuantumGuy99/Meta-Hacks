def next_taller_distance(heights: list[int]) -> list[int]:
    answer = []
    for i in range(len(heights)):
        distance = 0
        for j in range(i + 1, len(heights)):
            if heights[j] > heights[i]:
                distance = j - i
                break
        answer.append(distance)
    return answer
