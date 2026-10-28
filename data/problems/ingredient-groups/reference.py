def count_ingredient_groups(codes: list[str]) -> int:
    signatures = set()
    for code in codes:
        signatures.add("".join(sorted(code)))
    return len(signatures)
