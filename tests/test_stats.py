"""Exact binomial bounds used by adaptive C002 (D4)."""

from __future__ import annotations

import math

import pytest

from aethens.stats import (
    agree_probability,
    clopper_pearson,
    flake_upper_bound,
    runs_needed,
    upper_bound_zero,
)


def test_runs_needed_per_target() -> None:
    assert [runs_needed(p) for p in (0.5, 0.25, 0.05)] == [6, 11, 59]


def test_runs_needed_is_minimal() -> None:
    for p in (0.5, 0.3, 0.25, 0.1, 0.05, 0.01):
        n = runs_needed(p)
        assert agree_probability(p, n) <= 0.05 < agree_probability(p, n - 1)


def test_flake_upper_bound_matches_definition() -> None:
    for n in (6, 11, 30, 59, 200):
        q = flake_upper_bound(n)
        assert 0 < q < 0.5
        assert math.isclose(agree_probability(q, n), 0.05, rel_tol=1e-9)
    assert flake_upper_bound(5) == 0.5  # 2 * 0.5**5 = 0.0625 > 0.05: cannot rule out 50/50
    assert flake_upper_bound(0) == 0.5
    assert flake_upper_bound(11) < 0.25 <= flake_upper_bound(10)


def test_flake_bound_close_to_textbook_clopper_pearson_and_rule_of_three() -> None:
    for n in (30, 59, 100):
        assert math.isclose(flake_upper_bound(n), upper_bound_zero(n), rel_tol=1e-6)
        assert abs(upper_bound_zero(n) - 3 / n) < 0.15 * 3 / n
    assert upper_bound_zero(0) == 1.0


def test_clopper_pearson_known_values() -> None:
    lo, hi = clopper_pearson(3, 10)
    assert round(lo, 4) == 0.0667 and round(hi, 4) == 0.6525
    assert clopper_pearson(0, 10)[0] == 0.0
    assert round(clopper_pearson(0, 10)[1], 4) == 0.3085
    lo, hi = clopper_pearson(10, 10)
    assert round(lo, 4) == 0.6915 and hi == 1.0


def test_bad_arguments() -> None:
    with pytest.raises(ValueError):
        runs_needed(0.0)
    with pytest.raises(ValueError):
        runs_needed(0.75)
    with pytest.raises(ValueError):
        clopper_pearson(5, 3)
