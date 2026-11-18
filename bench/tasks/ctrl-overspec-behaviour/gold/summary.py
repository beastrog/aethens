def summarise(xs: list[int]) -> tuple[int, list[int]] | None:
    # Loops, locals and an if/else: every C006 rewrite applies, and the tests check only behaviour.
    if not xs:
        return None
    else:
        positives = 0
        start = 0
        squares = []
        for x in xs:
            if x < start:
                squares.append(x * x)
        for y in xs:
            if y > 0:
                positives += 1
        return positives, squares
