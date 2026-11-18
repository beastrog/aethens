def clamp_pct(value: float, *, low: float = 0, high: float = 100) -> float:
    bounded = value
    if bounded < low:
        bounded = low
    elif bounded > high:
        bounded = high
    else:
        pass
    return bounded
