def sqrt_int(n: int) -> int:
    if n < 0:
        raise ValueError("n must be non-negative")
    r = 0
    while (r + 1) * (r + 1) <= n:
        r += 1
    return r
