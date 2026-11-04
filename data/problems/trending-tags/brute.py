def top_tags(tags: list[str], k: int) -> list[str]:
    counts = {}
    for tag in tags:
        counts[tag] = counts.get(tag, 0) + 1
    result = []
    remaining = dict(counts)
    while remaining and len(result) < k:
        best = None
        for tag, count in remaining.items():
            if best is None or count > remaining[best] or (count == remaining[best] and tag < best):
                best = tag
        result.append(best)
        del remaining[best]
    return result
