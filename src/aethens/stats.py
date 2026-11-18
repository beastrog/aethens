"""Exact binomial confidence bounds (Clopper-Pearson), standard library only.

Used by C002 to state how flaky a verifier can still be after N runs that all agreed, and to put
a confidence interval on an observed flake rate.
"""

from __future__ import annotations

import math
from collections.abc import Callable


def agree_probability(q: float, n: int) -> float:
    """P(all n runs give the same verdict) when each run independently gives the less likely
    verdict with probability q: either all give the likely one or all give the unlikely one."""
    return float((1 - q) ** n + q**n)


def flake_upper_bound(n: int, confidence: float = 0.95) -> float:
    """Exact one-sided upper confidence bound on the flake rate after n runs that all agreed.

    The flake rate q (0 <= q <= 0.5) is the per-run probability of the less likely verdict. The
    bound is the largest q that is still compatible with "all n agreed" at this confidence, i.e.
    the root of ``agree_probability(q, n) = 1 - confidence`` on [0, 0.5] (the test inversion
    behind Clopper-Pearson). Returns 0.5 when even q = 0.5 cannot be ruled out.

    When the normal verdict is known in advance this reduces to the textbook Clopper-Pearson
    bound for 0 events, ``1 - (1 - confidence) ** (1 / n)`` (about 3/n, the rule of three); the
    extra ``q**n`` term makes it slightly more conservative because C002 does not know in advance
    which verdict is the normal one.
    """
    alpha = 1 - confidence
    if n <= 0 or agree_probability(0.5, n) > alpha:
        return 0.5
    lo, hi = 0.0, 0.5  # agree_probability decreases on [0, 0.5]
    for _ in range(200):
        mid = (lo + hi) / 2
        if agree_probability(mid, n) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def runs_needed(p: float, confidence: float = 0.95) -> int:
    """Smallest n such that n agreeing runs show "flake rate below p" at this confidence."""
    if not 0 < p < 0.5 + 1e-12:
        raise ValueError("p must be in (0, 0.5]")
    alpha = 1 - confidence
    n = 1
    while agree_probability(p, n) > alpha:
        n += 1
    return n


def upper_bound_zero(n: int, confidence: float = 0.95) -> float:
    """Textbook one-sided Clopper-Pearson upper bound after 0 events in n trials."""
    if n <= 0:
        return 1.0
    return float(1 - (1 - confidence) ** (1 / n))


def _binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return float(sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1)))


def _solve(f: Callable[[float], float], target: float) -> float:
    """Root of a decreasing function f(p) = target on [0, 1], by bisection."""
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(mid) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Exact two-sided Clopper-Pearson interval for k events in n trials."""
    if not 0 <= k <= n or n <= 0:
        raise ValueError("need 0 <= k <= n and n > 0")
    alpha = 1 - confidence
    # lower: P(X >= k | p) = alpha/2, i.e. P(X <= k-1 | p) = 1 - alpha/2 (cdf decreases in p)
    lower = 0.0 if k == 0 else _solve(lambda p: _binom_cdf(k - 1, n, p), 1 - alpha / 2)
    # upper: P(X <= k | p) = alpha/2
    upper = 1.0 if k == n else _solve(lambda p: _binom_cdf(k, n, p), alpha / 2)
    return lower, upper
