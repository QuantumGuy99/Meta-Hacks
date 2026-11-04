from collections import Counter


def top_tags(tags: list[str], k: int) -> list[str]:
    counts = Counter(tags)
    ranked = sorted(counts, key=lambda tag: (-counts[tag], tag))
    return ranked[:k]
