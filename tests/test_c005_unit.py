"""C005 test-order and isolation logic with a fake runner (D1). No Docker."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from aethens.adapters import load_task
from aethens.checks import C005OrderDependence, CheckContext
from aethens.checks.c005_order import parse_driver_output, unittest_args
from aethens.models import Budget, Confidence, Severity, Task
from aethens.runner import RunResult, RunSpec
from fakes import FakeRunner, result

REPO = Path(__file__).resolve().parent.parent
TASK = load_task(REPO / "examples" / "add-two")
MARKER = "AETHENS-ORDER-RESULT "
IDS = ["test_m.T.test_a", "test_m.T.test_b", "test_m.T.test_c"]


def ctx(runner: FakeRunner, budget: Budget = Budget.STANDARD) -> CheckContext:
    return CheckContext(runner=runner, seed=3, budget=budget)


def mode_of(spec: RunSpec) -> str:
    cmd = list(spec.command)
    assert cmd[1] == ".aethens/order_driver.py"
    return cmd[2]


def order_for(mode: str, n: int) -> list[int]:
    if mode == "default":
        return list(range(n))
    if mode == "reverse":
        return list(reversed(range(n)))
    if mode.startswith("only:"):
        return [int(mode.split(":", 1)[1])]
    assert mode.startswith("shuffle:")
    return [n - 1, *range(n - 1)]  # deterministic stand-in for a shuffle


def driver(verdict: Callable[[int, list[int]], str]) -> FakeRunner:
    """verdict(test index, order of this run) -> outcome code."""

    def decide(spec: RunSpec, _i: int) -> RunResult:
        mode = mode_of(spec)
        order = order_for(mode, len(IDS))
        run = [[i, verdict(i, order)] for i in order]
        payload = {"v": 1, "mode": mode, "tests": IDS, "run": run}
        ok = all(str(code) in "PSX" for _, code in run)
        return result(0 if ok else 1, out="noise\n" + MARKER + json.dumps(payload) + "\n")

    return FakeRunner(decide)


def b_needs_a(i: int, order: list[int]) -> str:
    if i != 1:
        return "P"
    return "P" if 0 in order and order.index(0) < order.index(1) else "E"


def test_unittest_args() -> None:
    assert unittest_args(("python", "-m", "unittest", "discover", "-s", "tests")) == (
        "discover",
        "-s",
        "tests",
    )
    assert unittest_args(("python3", "-m", "unittest")) == ()
    assert unittest_args(("python3.12", "-m", "unittest", "-v")) == ("-v",)
    assert unittest_args(("pytest", "-q")) is None
    assert unittest_args(("python", "-m", "pytest")) is None
    assert unittest_args(("bash", "-c", "python -m unittest")) is None


def test_parse_driver_output_takes_last_marker() -> None:
    out = f'{MARKER}{{"v": 1, "run": []}}\nmore\n{MARKER}' + json.dumps(
        {"v": 1, "mode": "default", "tests": IDS, "run": [[0, "P"]]}
    )
    parsed = parse_driver_output(out)
    assert parsed is not None and parsed.outcomes == {0: "P"} and parsed.tests == tuple(IDS)
    assert parse_driver_output("no marker here") is None
    assert parse_driver_output(MARKER + "{not json") is None


def test_order_dependent_test_is_reported_once_with_evidence() -> None:
    runner = driver(b_needs_a)
    findings = C005OrderDependence().run(TASK, ctx(runner))
    assert len(findings) == 1
    f = findings[0]
    assert f.check_id == "C005" and f.severity is Severity.ERROR
    assert f.confidence is Confidence.CONFIRMED
    assert f.evidence.subject == "test:test_m.T.test_b"
    assert "test_m.T.test_b" in f.title
    assert f.evidence.extra["default_outcome"] == "pass"
    changed = f.evidence.extra["changed_in"]
    assert "reverse" in changed and "alone" in changed
    assert f.evidence.command[1] == ".aethens/order_driver.py"
    assert f.repro == "aethens audit examples/add-two --check C005 --seed 3 --budget standard"
    assert f.limits


def test_independent_tests_are_silent() -> None:
    runner = driver(lambda i, order: "P")
    assert C005OrderDependence().run(TASK, ctx(runner)) == []
    modes = [mode_of(s) for s in runner.specs]
    assert modes[0] == "default" and "reverse" in modes
    assert sum(m.startswith("shuffle:") for m in modes) == 2  # standard budget
    assert sorted(m for m in modes if m.startswith("only:")) == ["only:0", "only:1", "only:2"]


def test_same_hash_seed_for_every_run_and_driver_layer() -> None:
    runner = driver(lambda i, order: "P")
    C005OrderDependence().run(TASK, ctx(runner))
    seeds = {s.env["PYTHONHASHSEED"] for s in runner.specs}
    assert len(seeds) == 1
    for s in runner.specs:
        assert s.layers[-1][1] == Path(".aethens")
        assert (s.layers[-1][0] / "order_driver.py").name == "order_driver.py"
        assert s.command[0] == TASK.verifier[0]
        assert list(s.command[3:]) == ["--", *TASK.verifier[3:]]


def test_non_reproducing_change_is_info_only() -> None:
    calls = {"reverse": 0}

    def decide(spec: RunSpec, _i: int) -> RunResult:
        mode = mode_of(spec)
        order = order_for(mode, len(IDS))
        flip = False
        if mode == "reverse":
            calls["reverse"] += 1
            flip = calls["reverse"] == 1  # only the first reversed run differs
        run = [[i, "F" if (flip and i == 2) else "P"] for i in order]
        payload = {"v": 1, "mode": mode, "tests": IDS, "run": run}
        return result(1 if flip else 0, out=MARKER + json.dumps(payload))

    findings = C005OrderDependence().run(TASK, ctx(FakeRunner(decide)))
    assert [f.severity for f in findings] == [Severity.INFO]
    assert "did not reproduce" in findings[0].title


def test_unsupported_verifier_gives_one_info_finding() -> None:
    task = Task(**{**TASK.__dict__, "verifier": ("pytest", "-q")})
    runner = FakeRunner(lambda s, i: result(0))
    findings = C005OrderDependence().run(task, ctx(runner))
    assert runner.specs == []
    assert [f.severity for f in findings] == [Severity.INFO]
    assert "checked nothing" in findings[0].title


def test_unparsable_baseline_gives_info_finding() -> None:
    runner = FakeRunner(lambda s, i: result(1, out="Traceback: boom"))
    findings = C005OrderDependence().run(TASK, ctx(runner))
    assert len(runner.specs) == 1
    assert [f.severity for f in findings] == [Severity.INFO]
    assert "Traceback: boom" in findings[0].evidence.stdout_tail


def test_isolation_cap_per_budget() -> None:
    many = [f"test_m.T.test_{i:03d}" for i in range(40)]

    def decide(spec: RunSpec, _i: int) -> RunResult:
        mode = mode_of(spec)
        order = order_for(mode, len(many))
        payload = {"v": 1, "mode": mode, "tests": many, "run": [[i, "P"] for i in order]}
        return result(0, out=MARKER + json.dumps(payload))

    for budget, cap in ((Budget.SMOKE, 10), (Budget.STANDARD, 30), (Budget.DEEP, 40)):
        runner = FakeRunner(decide)
        C005OrderDependence().run(TASK, ctx(runner, budget))
        alone = [s for s in runner.specs if mode_of(s).startswith("only:")]
        assert len(alone) == cap


def test_deterministic_plan() -> None:
    a, b = driver(b_needs_a), driver(b_needs_a)
    fa = C005OrderDependence().run(TASK, ctx(a))
    fb = C005OrderDependence().run(TASK, ctx(b))
    assert [s.command for s in a.specs] == [s.command for s in b.specs]
    assert [f.id for f in fa] == [f.id for f in fb]
