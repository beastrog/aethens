"""The in-sandbox order driver (D1): pure ordering logic in-process, end to end in Docker."""

from __future__ import annotations

import unittest
from pathlib import Path

import pytest

from aethens.adapters import load_task
from aethens.checks import C005OrderDependence, CheckContext
from aethens.models import Budget, Severity
from aethens.runner import DockerRunner
from aethens.sandbox import order_driver

BENCH = Path(__file__).resolve().parent.parent / "bench" / "tasks"


class _A(unittest.TestCase):
    def test_1(self) -> None: ...
    def test_2(self) -> None: ...
    def test_3(self) -> None: ...


class _B(unittest.TestCase):
    def test_1(self) -> None: ...
    def test_2(self) -> None: ...


def _tests() -> list[unittest.TestCase]:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([loader.loadTestsFromTestCase(_A), loader.loadTestsFromTestCase(_B)])
    return order_driver.flatten(suite)


def test_flatten_and_default_order() -> None:
    tests = _tests()
    assert [t.id().rsplit(".", 2)[-2:] for t in tests][:2] == [["_A", "test_1"], ["_A", "test_2"]]
    assert order_driver.order_tests(tests, "default") == tests


def test_reverse_and_only() -> None:
    tests = _tests()
    assert order_driver.order_tests(tests, "reverse") == tests[::-1]
    assert order_driver.order_tests(tests, "only:3") == [tests[3]]
    with pytest.raises(ValueError, match="unknown mode"):
        order_driver.order_tests(tests, "sideways")
    with pytest.raises(ValueError, match="out of range"):
        order_driver.order_tests(tests, "only:99")


def test_shuffle_is_seeded_permutation_keeping_classes_grouped() -> None:
    tests = _tests()
    a = order_driver.order_tests(tests, "shuffle:5")
    assert a == order_driver.order_tests(tests, "shuffle:5")
    assert sorted(map(id, a)) == sorted(map(id, tests))
    classes = [type(t).__name__ for t in a]
    # each class appears as one contiguous block
    blocks = [c for i, c in enumerate(classes) if i == 0 or classes[i - 1] != c]
    assert sorted(blocks) == ["_A", "_B"]
    seen = {tuple(map(id, order_driver.order_tests(tests, f"shuffle:{s}"))) for s in range(20)}
    assert len(seen) > 1


def test_outcome_codes() -> None:
    assert set(order_driver.CODES.values()) == {"P", "F", "E", "S", "X", "U"}


def _ctx() -> CheckContext:
    return CheckContext(runner=DockerRunner(), seed=0, budget=Budget.STANDARD)


@pytest.mark.docker
@pytest.mark.parametrize(
    ("task", "test_id"),
    [
        ("order-alphabetical", "test_reg.TestRegistry.test_b_lookup"),
        ("order-crossmodule", "test_a_convert.TestConvert.test_km"),
        ("order-classfixture", "test_inventory.TestInventory.test_b_first_is_smallest"),
    ],
)
def test_c005_finds_planted_order_dependence(task: str, test_id: str) -> None:
    findings = C005OrderDependence().run(load_task(BENCH / task), _ctx())
    loud = [f for f in findings if f.severity is Severity.ERROR]
    assert [f.evidence.subject for f in loud] == [f"test:{test_id}"]


@pytest.mark.docker
def test_c005_finds_order_generated() -> None:
    findings = C005OrderDependence().run(load_task(BENCH / "order-generated"), _ctx())
    assert any(f.severity is Severity.ERROR for f in findings)


@pytest.mark.docker
@pytest.mark.parametrize(
    "task",
    ["ctrl-isolated-state", "ctrl-order-cache", "ctrl-order-shared-readonly", "ctrl-clamp"],
)
def test_c005_controls_are_silent(task: str) -> None:
    assert C005OrderDependence().run(load_task(BENCH / task), _ctx()) == []
