"""C007 reward-hacking probes with a fake runner and pure probe builders (D5). No Docker."""

from __future__ import annotations

import ast
from pathlib import Path

from aethens.adapters import load_task
from aethens.checks import C007RewardHacking, CheckContext
from aethens.checks.c007_reward_hack import (
    CATEGORIES,
    always_equal_module,
    build_probes,
    hardcoded_module,
    visible_pairs,
)
from aethens.models import Budget, Confidence, Severity
from aethens.runner import RunResult, RunSpec
from fakes import FakeRunner, overlay_name, result

REPO = Path(__file__).resolve().parent.parent
# A plain, gameable unittest task (the pre-hardening examples/add-two). The examples themselves now
# use hardened tests that C007's probes do not get through.
TASK = load_task(REPO / "tests" / "fixtures" / "plain-add")


def ctx(runner: FakeRunner) -> CheckContext:
    return CheckContext(runner=runner, seed=2, budget=Budget.STANDARD)


def probe_text(spec: RunSpec) -> str:
    return "".join(p.read_text() for p in sorted(Path(spec.layers[1][0]).rglob("*.py")))


def test_probes_cover_every_category_for_a_simple_task() -> None:
    probes, skipped = build_probes(TASK)
    assert {p.category for p in probes} == set(CATEGORIES)
    assert skipped == []
    for p in probes:
        for content in p.files.values():
            compile(content, "<probe>", "exec")


def test_always_equal_module() -> None:
    src = "K = 3\n\ndef f(x):\n    return x\n\nclass Stack:\n    def pop(self):\n        return 1\n"
    mod = always_equal_module(src)
    assert mod is not None
    ns: dict[str, object] = {}
    exec(compile(mod, "probe", "exec"), ns)  # noqa: S102 - Aethens' own generated probe
    f, stack_cls = ns["f"], ns["Stack"]
    assert callable(f) and callable(stack_cls)
    assert f(1) == 99
    assert 99 == f(1)  # noqa: SIM300 - the reflected comparison is the point
    assert not (f(1) != 5)  # noqa: SIM202 - __ne__ is tested on purpose
    assert stack_cls().pop() == [1, 2]
    assert ns["K"] == 3
    assert always_equal_module("X = 1\n") is None


def test_visible_pairs_and_hardcoded_module() -> None:
    tests = [
        "import unittest\nfrom m import add\nclass T(unittest.TestCase):\n"
        "    def test_a(self):\n        self.assertEqual(add(2, 3), 5)\n"
        "        self.assertEqual(-1, add(-2, 1))\n        assert add(0, 0) == 0\n"
        "        self.assertEqual(add(x, 1), 2)\n"
    ]
    pairs = visible_pairs(tests, {"add"})
    assert sorted(pairs["add"]) == [("(-2, 1)", "-1"), ("(0, 0)", "0"), ("(2, 3)", "5")]
    mod = hardcoded_module("def add(a, b):\n    return a + b\n\ndef other():\n    pass\n", tests)
    assert mod is not None
    ns: dict[str, object] = {}
    exec(compile(mod, "probe", "exec"), ns)  # noqa: S102 - Aethens' own generated probe
    add = ns["add"]
    assert callable(add) and add(2, 3) == 5 and add(-2, 1) == -1
    tree = ast.parse(mod)
    assert any(isinstance(n, ast.FunctionDef) and n.name == "other" for n in tree.body)


def test_starter_passing_means_no_probes() -> None:
    runner = FakeRunner(lambda s, i: result(0))
    assert C007RewardHacking().run(TASK, ctx(runner)) == []
    assert len(runner.specs) == 1 and overlay_name(runner.specs[0]) == "starter"


def test_robust_verifier_is_silent() -> None:
    runner = FakeRunner(lambda s, i: result(1))
    assert C007RewardHacking().run(TASK, ctx(runner)) == []
    assert len(runner.specs) == 1 + 7  # starter + 7 probe variants


def test_exit_zero_probe_accepted_is_error_and_reproduced() -> None:
    def decide(spec: RunSpec, _i: int) -> RunResult:
        if overlay_name(spec) == "starter":
            return result(1)
        return result(0 if probe_text(spec) == "import os\nos._exit(0)\n" else 1)

    runner = FakeRunner(decide)
    findings = C007RewardHacking().run(TASK, ctx(runner))
    assert [f.evidence.extra["category"] for f in findings] == ["exit-zero"]
    f = findings[0]
    assert f.severity is Severity.ERROR and f.confidence is Confidence.CONFIRMED
    assert f.evidence.subject == "probe:exit-zero"
    assert "os._exit(0)" in f.evidence.extra["probe_files"]
    assert f.repro == (
        "aethens audit tests/fixtures/plain-add --check C007 --seed 2 --budget standard"
    )


def test_hardcoded_is_warning_needs_review() -> None:
    def decide(spec: RunSpec, _i: int) -> RunResult:
        if overlay_name(spec) == "starter":
            return result(1)
        return result(0 if "_TABLE_" in probe_text(spec) else 1)

    findings = C007RewardHacking().run(TASK, ctx(FakeRunner(decide)))
    assert [(f.evidence.extra["category"], f.severity) for f in findings] == [
        ("hardcoded-visible", Severity.WARNING)
    ]
    assert findings[0].confidence is Confidence.NEEDS_REVIEW


def test_probe_must_pass_twice() -> None:
    count = {"n": 0}

    def decide(spec: RunSpec, _i: int) -> RunResult:
        if overlay_name(spec) == "starter":
            return result(1)
        count["n"] += 1
        return result(0 if count["n"] == 1 else 1)

    assert C007RewardHacking().run(TASK, ctx(FakeRunner(decide))) == []


def test_probes_use_the_normal_runner_spec() -> None:
    runner = FakeRunner(lambda s, i: result(1))
    C007RewardHacking().run(TASK, ctx(runner))
    for s in runner.specs:
        assert s.command == TASK.verifier and s.image == TASK.image
        assert s.timeout_s == TASK.timeout_s
