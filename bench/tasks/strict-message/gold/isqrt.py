import math


def sqrt_int(n: int) -> int:
    if n < 0:
        raise ValueError(f"negative value: {n}")
    return math.isqrt(n)
