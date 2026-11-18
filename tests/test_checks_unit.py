"""C001 and C002 logic with a fake runner (B4). No Docker."""

from __future__ import annotations

from pathlib import Path

from aethens.adapters import load_task
from aethens.checks import C001GoldSanity, C002Flakiness, CheckContext, hash_seed
from aethens.models import Budget, Confidence, Severity
from aethens.runner import RunResult, RunSpec
from fakes import FakeRunner, overlay_name, result

REPO = Path(__file__).resolve().parent.parent
TASK = load_task(REPO / "examples" / "add-two")


def ctx(runner: FakeRunner, seed: int = 7, budget: Budget = Budget.STANDARD) -> CheckContext:
    return CheckContext(runner=runner, seed=seed, budget=budget)


def by_overlay(starter_ok: bool, gold_ok: bool) -> FakeRunner:
    def decide(spec: RunSpec, _i: int) -> RunResult:
        ok = starter_ok if overlay_name(spec) == "starter" else gold_ok
        return result(0 if ok else 1, err="" if ok else "FAILED (failures=1)")

    return FakeRunner(decide)


def test_check_metadata() -> None:
    for check in (C001GoldSanity(), C002Flakiness()):
        assert check.id in ("C001", "C002")
        assert check.tier and check.cost_class and check.title


def test_c001_clean() -> None:
    assert C001GoldSanity().run(TASK, ctx(by_overlay(False, True))) == []


def test_c001_starter_passes_is_error() -> None:
    findings = C001GoldSanity().run(TASK, ctx(by_overlay(True, True)))
    assert len(findings) == 1
    f = findings[0]
    assert f.check_id == "C001" and f.severity is Severity.ERROR
    assert f.evidence.subject == "starter"
    assert f.confidence is Confidence.CONFIRMED
    assert f.task_id == "add-two"
    assert f.repro == "aethens audit examples/add-two --check C001 --seed 7 --budget standard"
    assert f.limits


def test_c001_gold_fails_is_error_with_evidence() -> None:
    findings = C001GoldSanity().run(TASK, ctx(by_overlay(False, False)))
    assert [f.evidence.subject for f in findings] == ["gold"]
    f = findings[0]
    assert f.severity is Severity.ERROR
    assert f.evidence.exit_codes == (1,)
    assert "FAILED" in f.evidence.stderr_tail
    assert f.evidence.command == TASK.verifier
    assert f.evidence.extra["PYTHONHASHSEED"] == str(hash_seed(7, "add-two", "C001", "gold"))


def test_c001_gold_timeout_is_reported() -> None:
    def decide(spec: RunSpec, _i: int) -> RunResult:
        return result(1) if overlay_name(spec) == "starter" else result(timed_out=True)

    f = C001GoldSanity().run(TASK, ctx(FakeRunner(decide)))[0]
    assert f.evidence.timed_out and "timed out" in f.evidence.observed


def test_c001_layers_and_env() -> None:
    runner = by_overlay(False, True)
    C001GoldSanity().run(TASK, ctx(runner))
    starter, gold = runner.specs
    assert [p.name for p, _ in starter.layers] == ["starter", "tests"]
    assert [p.name for p, _ in gold.layers] == ["starter", "gold", "tests"]
    assert gold.layers[-1][1] == Path("tests")
    assert gold.command == TASK.verifier and gold.image == TASK.image
    assert gold.timeout_s == TASK.timeout_s
    assert "PYTHONHASHSEED" in gold.env


def test_c002_stable_is_silent() -> None:
    runner = FakeRunner(lambda s, i: result(0))
    assert C002Flakiness().run(TASK, ctx(runner)) == []
    assert len(runner.specs) == 11  # standard budget: enough agreeing runs for p < 0.25 (D4)


def test_c002_runs_per_budget() -> None:
    # D4: adaptive; with every run agreeing C002 runs until the budget's target bound holds
    for budget, n in ((Budget.SMOKE, 6), (Budget.STANDARD, 11), (Budget.DEEP, 59)):
        runner = FakeRunner(lambda s, i: result(0))
        C002Flakiness().run(TASK, ctx(runner, budget=budget))
        assert len(runner.specs) == n


def test_c002_flip_is_error_with_counts() -> None:
    runner = FakeRunner(lambda s, i: result(0 if i % 2 == 0 else 1))
    findings = C002Flakiness().run(TASK, ctx(runner))
    assert len(findings) == 1
    f = findings[0]
    assert f.severity is Severity.ERROR
    assert f.evidence.extra["pass_count"] == "3"
    assert f.evidence.extra["fail_count"] == "2"
    assert f.evidence.exit_codes == (0, 1, 0, 1, 0)
    assert f.repro.endswith("--check C002 --seed 7 --budget standard")


def test_c002_timing_only_is_warning() -> None:
    runner = FakeRunner(lambda s, i: result(timed_out=(i == 2)))
    f = C002Flakiness().run(TASK, ctx(runner))[0]
    assert f.severity is Severity.WARNING
    assert f.evidence.extra["timeout_count"] == "1"


def test_c002_hash_seeds_vary_and_are_deterministic() -> None:
    r1 = FakeRunner(lambda s, i: result(0))
    r2 = FakeRunner(lambda s, i: result(0))
    C002Flakiness().run(TASK, ctx(r1, seed=11))
    C002Flakiness().run(TASK, ctx(r2, seed=11))
    seeds1 = [s.env["PYTHONHASHSEED"] for s in r1.specs]
    seeds2 = [s.env["PYTHONHASHSEED"] for s in r2.specs]
    assert seeds1 == seeds2 and len(set(seeds1)) == 11
    r3 = FakeRunner(lambda s, i: result(0))
    C002Flakiness().run(TASK, ctx(r3, seed=12))
    assert [s.env["PYTHONHASHSEED"] for s in r3.specs] != seeds1


def test_finding_ids_are_deterministic() -> None:
    a = C001GoldSanity().run(TASK, ctx(by_overlay(True, False)))
    b = C001GoldSanity().run(TASK, ctx(by_overlay(True, False)))
    assert [f.id for f in a] == [f.id for f in b]
    assert len({f.id for f in a}) == 2


def test_hash_seed_range() -> None:
    for i in range(50):
        assert 0 <= hash_seed(i, "t", "C002", i) <= 4294967295


def test_unsafe_local_repro_flag() -> None:
    c = CheckContext(runner=by_overlay(True, True), seed=1, budget=Budget.SMOKE, unsafe_local=True)
    f = C001GoldSanity().run(TASK, c)[0]
    assert f.repro.endswith("--unsafe-local")
