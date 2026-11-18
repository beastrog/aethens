import math
import warnings


def checked_sqrt(x: float) -> float:
    # Negative input: warn and fall back to zero, as the statement asks.
    if x < 0:
        warnings.warn("negative input", RuntimeWarning, stacklevel=1)
        return 0.0
    return math.sqrt(x)
