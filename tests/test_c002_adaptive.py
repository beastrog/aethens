"""Adaptive C002 (D4): runs until a flake-rate bound holds or flakiness shows, within a budget;
coverage statements in the report (aethens-report/v2). Fake runner, no Docker."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from aethens.adapters import load_task
from aethens.audit import run_audit
from aethens.checks import C001GoldSanity, C002Flakiness, CheckContext
from aethens.checks.c002_flakiness import MIN_RUNS, TARGET_P, TIME_BUDGET_S, max_runs
from aethens.errors import SchemaError
from aethens.models import Budget, Coverage, Report, Severity
from aethens.report import render_json, render_markdown
from fakes import FakeRunner, result

REPO = Path(__file__).resolve().parent.parent
TASK = load_task(REPO / "examples" / "add-two")
SCHEMA = json.loads((REPO / "docs" / "report-schema.json").read_text())


def ctx(runner: FakeRunner, budget: Budget = Budget.STANDARD, seed: int = 7) -> CheckContext:
    return CheckContext(runner=runner, seed=seed, budget=budget)


def test_budget_table() -> None:
    assert MIN_RUNS == {Budget.SMOKE: 3, Budget.STANDARD: 5, Budget.DEEP: 10}
    assert TARGET_P == {Budget.SMOKE: 0.5, Budget.STANDARD: 0.25, Budget.DEEP: 0.05}
    assert [max_runs(b) for b in Budget] == [6, 11, 59]
    assert TIME_BUDGET_S[Budget.STANDARD] == 300.0


def test_stable_gold_gives_coverage_statement_with_bound() -> None:
    runner = FakeRunner(lambda s, i: result(0))
    findings, coverage = C002Flakiness().run_with_coverage(TASK, ctx(runner))
    assert findings == [] and len(coverage) == 1
    c = coverage[0]
    assert (c.check_id, c.task_id) == ("C002", "add-two")
    assert "flake rate below 0.25 at 95% confidence" in c.statement
    assert c.stats["runs"] == "11" and c.stats["target_reached"] == "yes"
    assert c.stats["stopped_by"] == "target" and c.stats["verdict"] == "pass"
    assert 0.2 < float(c.stats["flake_rate_upper_bound"]) < 0.25
    assert len(c.stats["PYTHONHASHSEED_values"].split(",")) == 11


def test_consistently_failing_gold_also_gets_a_bound() -> None:
    runner = FakeRunner(lambda s, i: result(1))
    findings, coverage = C002Flakiness().run_with_coverage(TASK, ctx(runner))
    assert findings == [] and coverage[0].stats["verdict"] == "fail"


def test_late_flip_is_caught_by_the_extra_runs() -> None:
    # Agrees for the first 8 runs, then flips: the old fixed 5 runs would have missed it.
    runner = FakeRunner(lambda s, i: result(1 if i == 8 else 0))
    findings, coverage = C002Flakiness().run_with_coverage(TASK, ctx(runner))
    assert coverage == [] and len(findings) == 1
    f = findings[0]
    assert f.severity is Severity.ERROR
    assert f.evidence.extra["runs"] == "9" and f.evidence.extra["minority_count"] == "1"
    assert len(runner.specs) == 9  # stops at the first disagreement after the minimum
    lo, hi = (float(x) for x in f.evidence.extra["flake_rate_ci95"].split("-"))
    assert lo < 1 / 9 < hi
    assert "Clopper-Pearson" in f.evidence.observed


def test_disagreement_in_base_phase_finishes_base_phase_only() -> None:
    runner = FakeRunner(lambda s, i: result(i % 2))
    findings = C002Flakiness().run(TASK, ctx(runner))
    assert len(findings) == 1 and len(runner.specs) == 5


def test_time_budget_stops_early_and_says_so() -> None:
    runner = FakeRunner(lambda s, i: result(0, duration_s=70.0))
    findings, coverage = C002Flakiness().run_with_coverage(TASK, ctx(runner))
    assert findings == [] and len(runner.specs) == 5  # 5 x 70 s >= 300 s after the minimum
    c = coverage[0]
    assert c.stats["stopped_by"] == "time" and c.stats["target_reached"] == "no"
    assert "too few runs" in c.statement


def test_time_budget_partial_bound() -> None:
    runner = FakeRunner(lambda s, i: result(0, duration_s=40.0))
    _, coverage = C002Flakiness().run_with_coverage(TASK, ctx(runner, Budget.DEEP))
    c = coverage[0]
    assert c.stats["stopped_by"] == "time" and c.stats["runs"] == str(
        len(c.stats["PYTHONHASHSEED_values"].split(","))
    )
    n = int(c.stats["runs"])
    assert n == 45  # 45 x 40 s = 1800 s
    assert "target was not reached" in c.statement and "flake rate below 0.0" in c.statement


def test_run_matches_run_with_coverage_findings() -> None:
    a = C002Flakiness().run(TASK, ctx(FakeRunner(lambda s, i: result(1 if i == 6 else 0))))
    b, _ = C002Flakiness().run_with_coverage(
        TASK, ctx(FakeRunner(lambda s, i: result(1 if i == 6 else 0)))
    )
    assert a == b


def test_other_checks_report_no_coverage() -> None:
    _, coverage = C001GoldSanity().run_with_coverage(TASK, ctx(FakeRunner(lambda s, i: result(0))))
    assert coverage == []


def test_report_carries_coverage_and_validates() -> None:
    runner = FakeRunner(lambda s, i: result(0))
    report = run_audit([TASK], [C002Flakiness()], ctx(runner))
    assert len(report.coverage) == 1
    data = json.loads(render_json(report))
    assert data["schema"] == "aethens-report/v2"
    jsonschema.validate(data, SCHEMA)
    assert Report.from_dict(data) == report
    md = render_markdown(report)
    assert "Coverage" in md and "flake rate below 0.25" in md


def test_report_reads_v1_without_coverage() -> None:
    report = run_audit([TASK], [C002Flakiness()], ctx(FakeRunner(lambda s, i: result(0))))
    data = report.to_dict()
    data["schema"] = "aethens-report/v1"
    del data["coverage"]
    old = Report.from_dict(data)
    assert old.coverage == () and old.schema == "aethens-report/v1"
    data["schema"] = "aethens-report/v3"
    with pytest.raises(SchemaError):
        Report.from_dict(data)


def test_coverage_round_trip() -> None:
    c = Coverage(check_id="C002", task_id="t", statement="s", stats={"runs": "11"})
    assert Coverage.from_dict(json.loads(json.dumps(c.to_dict()))) == c
