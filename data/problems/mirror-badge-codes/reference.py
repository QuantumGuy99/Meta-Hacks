def is_mirror_code(code: str) -> bool:
    left, right = 0, len(code) - 1
    while left < right:
        if code[left] == "-":
            left += 1
        elif code[right] == "-":
            right -= 1
        elif code[left].lower() != code[right].lower():
            return False
        else:
            left += 1
            right -= 1
    return True
