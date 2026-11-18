MILES_PER_KM = 0.621371


def km_to_miles(km: float) -> float:
    return round(km * MILES_PER_KM, 3)
