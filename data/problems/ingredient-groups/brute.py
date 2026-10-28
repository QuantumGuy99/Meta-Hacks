def count_ingredient_groups(codes: list[str]) -> int:
    # Slow but obviously correct: keep one representative per group and
    # compare letter counts by hand.
    def same_mix(a: str, b: str) -> bool:
        if len(a) != len(b):
            return False
        for letter in "abcdefghijklmnopqrstuvwxyz":
            if a.count(letter) != b.count(letter):
                return False
        return True

    representatives = []
    for code in codes:
        if not any(same_mix(code, rep) for rep in representatives):
            representatives.append(code)
    return len(representatives)
