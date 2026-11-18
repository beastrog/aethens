"""C003 and C004 logic with a fake runner (B5). No Docker."""

from __future__ import annotations

from pathlib import Path

from aethens.adapters import load_task
from aethens.checks import C003LabeledCandidates, C004MutationProbes, CheckContext
from aethens.models import Budget, Confidence, LabelSource, Severity
from aethens.runner import RunResult, RunSpec
from fakes import FakeRunner, result

REPO = Path(__file__).resolve().parent.parent
BENCH = REPO / "bench" / "tasks"


def ctx(runner: FakeRunner, budget: Budget = Budget.STANDARD) -> CheckContext:
    return CheckContext(runner=runner, seed=3, budget=budget)


def overlay(spec: RunSpec) -> str:
    return Path(spec.layers[1][0]).name


def test_c003_correct_verdicts_are_silent() -> None:
    task = load_task(REPO / "examples" / "add-two")

    def decide(spec: RunSpec, _i: int) -> RunResult:
        return result(0 if overlay(spec) == "reversed-operands" else 1)

    assert C003LabeledCandidates().run(task, ctx(FakeRunner(decide))) == []


def test_c003_false_reject_and_false_accept_human() -> None:
    task = load_task(REPO / "examples" / "add-two")

    def decide(spec: RunSpec, _i: int) -> RunResult:
        return result(1 if overlay(spec) == "reversed-operands" else 0)

    findings = C003LabeledCandidates().run(task, ctx(FakeRunner(decide)))
    by_subject = {f.evidence.subject: f for f in findings}
    rej = by_subject["candidate:reversed-operands"]
    acc = by_subject["candidate:always-five"]
    assert rej.severity is Severity.ERROR and rej.confidence is Confidence.CONFIRMED
    assert "rejects" in rej.title.lower()
    assert acc.severity is Severity.ERROR and "accepts" in acc.title.lower()
    for f in findings:
        assert "relies on" in f.detail and "label" in f.detail
        assert f.evidence.extra["label_source"] == LabelSource.HUMAN.value


def test_c003_llm_unreviewed_is_warning_needs_review() -> None:
    task = load_task(BENCH / "weak-llm")
    findings = C003LabeledCandidates().run(task, ctx(FakeRunner(lambda s, i: result(0))))
    assert len(findings) == 1
    f = findings[0]
    assert f.severity is Severity.WARNING
    assert f.confidence is Confidence.NEEDS_REVIEW


def test_c003_timeout_of_valid_candidate_is_a_reject() -> None:
    task = load_task(REPO / "examples" / "add-two")

    def decide(spec: RunSpec, _i: int) -> RunResult:
        if overlay(spec) == "reversed-operands":
            return result(timed_out=True)
        return result(1)

    (f,) = C003LabeledCandidates().run(task, ctx(FakeRunner(decide)))
    assert f.evidence.timed_out


def test_c004_survivors_are_info_only_and_capped() -> None:
    task = load_task(BENCH / "weak-leap")
    runner = FakeRunner(lambda s, i: result(0))  # every mutant "survives"
    findings = C004MutationProbes().run(task, ctx(runner, Budget.SMOKE))
    assert len(runner.specs) == 5 and len(findings) == 5
    for f in findings:
        assert f.severity is Severity.INFO
        assert f.confidence is Confidence.NEEDS_REVIEW
        assert "may be semantically equivalent; review" in f.detail
        assert f.evidence.extra["diff"].startswith("---")
    assert len({f.id for f in findings}) == 5


def test_c004_killed_mutants_are_silent() -> None:
    task = load_task(BENCH / "weak-leap")
    assert C004MutationProbes().run(task, ctx(FakeRunner(lambda s, i: result(1)))) == []


def test_c004_mutant_overlay_contains_mutated_gold(tmp_path: Path) -> None:
    task = load_task(BENCH / "weak-leap")
    seen: list[str] = []

    def decide(spec: RunSpec, _i: int) -> RunResult:
        seen.append((Path(spec.layers[1][0]) / "leap.py").read_text())
        return result(1)

    C004MutationProbes().run(task, ctx(FakeRunner(decide), Budget.SMOKE))
    gold = (task.root / "gold" / "leap.py").read_text()
    assert len(seen) == 5 and all(s != gold for s in seen)


def test_c004_budget_caps() -> None:
    task = load_task(BENCH / "weak-leap")
    for budget, cap in ((Budget.SMOKE, 5), (Budget.STANDARD, 10)):
        runner = FakeRunner(lambda s, i: result(1))
        C004MutationProbes().run(task, ctx(runner, budget))
        assert len(runner.specs) == cap


def test_c004_no_python_in_gold_gives_info(tmp_path: Path) -> None:
    import shutil

    root = tmp_path / "t"
    shutil.copytree(BENCH / "weak-leap", root)
    (root / "gold" / "leap.py").unlink()
    (root / "gold" / "notes.txt").write_text("no code")
    task = load_task(root)
    runner = FakeRunner(lambda s, i: result(1))
    findings = C004MutationProbes().run(task, ctx(runner))
    assert len(findings) == 1 and findings[0].severity is Severity.INFO
    assert "no mutants" in findings[0].title.lower()
    assert runner.specs == []
