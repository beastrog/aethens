"""C006 logic with a fake runner (D3). No Docker."""

from __future__ import annotations

from pathlib import Path

from aethens.adapters import load_task
from aethens.checks import C006OverSpecified, CheckContext
from aethens.models import Budget, Confidence, Severity
from aethens.runner import RunResult, RunSpec
from fakes import FakeRunner, overlay_name, result

REPO = Path(__file__).resolve().parent.parent
TASK = load_task(REPO / "bench" / "tasks" / "overspec-source")
PLAIN = load_task(REPO / "examples" / "add-two")  # nothing to rewrite


def ctx(runner: FakeRunner, budget: Budget = Budget.STANDARD) -> CheckContext:
    return CheckContext(runner=runner, seed=4, budget=budget)


def overlay_source(spec: RunSpec) -> str:
    return "".join(p.read_text() for p in sorted(Path(spec.layers[1][0]).rglob("*.py")))


def test_all_rewrites_accepted_is_silent() -> None:
    runner = FakeRunner(lambda s, i: result(0))
    assert C006OverSpecified().run(TASK, ctx(runner)) == []
    assert overlay_name(runner.specs[0]) == "gold"
    assert len(runner.specs) >= 2


def test_rejected_rewrite_is_warning_with_diff_and_repro() -> None:
    def decide(spec: RunSpec, _i: int) -> RunResult:
        if overlay_name(spec) == "gold":
            return result(0)
        return result(1, err="FAILED (failures=1)")  # every rewrite rejected

    findings = C006OverSpecified().run(TASK, ctx(FakeRunner(decide)))
    assert findings and all(f.severity is Severity.WARNING for f in findings)
    f = next(x for x in findings if x.evidence.extra["rewrite"] == "rename-locals")
    assert f.check_id == "C006" and f.confidence is Confidence.NEEDS_REVIEW
    assert f.evidence.subject == "rewrite:rename-locals"
    assert "---" in f.evidence.extra["diff"]
    want = "aethens audit bench/tasks/overspec-source --check C006 --seed 4 --budget standard"
    assert f.repro == want
    assert "FAILED" in f.evidence.stderr_tail


def test_non_reproducible_rejection_is_ignored() -> None:
    seen: dict[str, int] = {}

    def decide(spec: RunSpec, _i: int) -> RunResult:
        if overlay_name(spec) == "gold":
            return result(0)
        key = overlay_source(spec)
        seen[key] = seen.get(key, 0) + 1
        return result(1 if seen[key] == 1 else 0)  # rejected once, then accepted

    assert C006OverSpecified().run(TASK, ctx(FakeRunner(decide))) == []


def test_failing_gold_means_nothing_to_compare() -> None:
    runner = FakeRunner(lambda s, i: result(1))
    assert C006OverSpecified().run(TASK, ctx(runner)) == []
    assert len(runner.specs) == 1


def test_smoke_budget_runs_fewer_rewrites() -> None:
    a, b = FakeRunner(lambda s, i: result(0)), FakeRunner(lambda s, i: result(0))
    C006OverSpecified().run(TASK, ctx(a, Budget.SMOKE))
    C006OverSpecified().run(TASK, ctx(b, Budget.STANDARD))
    assert len(a.specs) < len(b.specs)
    assert len(a.specs) <= 3


def test_no_rewrite_site_is_one_info_and_runs_nothing() -> None:
    runner = FakeRunner(lambda s, i: result(0))
    findings = C006OverSpecified().run(PLAIN, ctx(runner))
    assert [f.severity for f in findings] == [Severity.INFO]
    assert "checked nothing" in findings[0].title
    assert runner.specs == []
