def evens_doubled(xs: list[int]) -> list[int]:
    result = []
    for x in xs:
        if x % 2 == 0:
            result.append(x * 2)
    return result
