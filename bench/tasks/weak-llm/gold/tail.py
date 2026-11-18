def last_n(xs: list[int], n: int) -> list[int]:
    if n <= 0:
        return []
    return xs[-n:]
