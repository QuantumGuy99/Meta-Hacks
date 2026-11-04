from collections import deque


def window_peaks(readings: list[int], k: int) -> list[int]:
    peaks = []
    window = deque()  # indexes, readings decreasing from front to back
    for i, value in enumerate(readings):
        while window and readings[window[-1]] <= value:
            window.pop()
        window.append(i)
        if window[0] <= i - k:
            window.popleft()
        if i >= k - 1:
            peaks.append(readings[window[0]])
    return peaks
