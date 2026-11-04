def window_peaks(readings: list[int], k: int) -> list[int]:
    return [max(readings[i:i + k]) for i in range(len(readings) - k + 1)]
