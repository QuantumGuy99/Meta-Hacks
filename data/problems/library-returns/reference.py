def first_repeat(ids: list[int]) -> int:
    seen = set()
    for book_id in ids:
        if book_id in seen:
            return book_id
        seen.add(book_id)
    return -1
