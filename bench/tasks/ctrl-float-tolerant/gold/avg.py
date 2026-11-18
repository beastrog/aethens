def average(xs: list[float]) -> float:
    total = 0.0
    for x in xs:
        total += x
    return total / len(xs)
