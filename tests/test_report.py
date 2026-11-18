"""aethens-report/v1 JSON Schema and Markdown rendering (B6)."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from aethens.adapters import load_tasks
from aethens.audit import run_audit
from aethens.checks import (
    C001GoldSanity,
    C002Flakiness,
    C003LabeledCandidates,
    C004MutationProbes,
    CheckContext,
)
from aethens.models import Budget, Report
from aethens.report import render_json, render_markdown
from aethens.runner import RunResult, RunSpec
from fakes import FakeRunner, result

REPO = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((REPO / "docs" / "report-schema.json").read_text())
ALL = [C001GoldSanity(), C002Flakiness(), C003LabeledCandidates(), C004MutationProbes()]


def _report(seed: int = 0) -> Report:
    # Alternate pass/fail so every check produces findings of several kinds; the llm-labelled
    # invalid candidate always passes, which yields a warning (C003, needs-review).
    def decide(spec: RunSpec, i: int) -> RunResult:
        if Path(spec.layers[1][0]).name == "naive-slice":
            return result(0)
        return result(i % 2, out="o" * 50, err="e|rr")

    runner = FakeRunner(decide)
    tasks = load_tasks(REPO / "bench" / "tasks")
    return run_audit(tasks, ALL, CheckContext(runner=runner, seed=seed, budget=Budget.SMOKE))


def test_schema_is_valid_json_schema() -> None:
    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["properties"]["schema"]["const"] == "aethens-report/v1"


def test_report_validates_against_schema() -> None:
    report = _report()
    data = json.loads(render_json(report))
    assert {f["severity"] for f in data["findings"]} == {"error", "warning", "info"}
    jsonschema.validate(data, SCHEMA)
    assert Report.from_dict(data) == report


def test_schema_rejects_bad_severity() -> None:
    data = json.loads(render_json(_report()))
    data["findings"][0]["severity"] = "critical"
    try:
        jsonschema.validate(data, SCHEMA)
    except jsonschema.ValidationError:
        return
    raise AssertionError("schema accepted an unknown severity")


def test_markdown_contents() -> None:
    report = _report()
    md = render_markdown(report)
    assert md.startswith("## Aethens report")
    assert report.tool_version in md
    assert "Budget: `smoke`" in md and "Seed: `0`" in md
    assert "C001, C002, C003, C004" in md
    for f in report.findings[:5]:
        assert f.repro in md
    assert "e\\|rr" in md  # pipes are escaped inside table cells and text


def test_markdown_clean_report_does_not_overclaim() -> None:
    runner = FakeRunner(lambda s, i: result(0))
    tasks = load_tasks(REPO / "examples" / "add-two")
    report = run_audit(tasks, [C002Flakiness()], CheckContext(runner, 0, Budget.SMOKE))
    md = render_markdown(report)
    assert "No findings" in md
    lowered = md.lower()
    for phrase in ("cannot be exploited", "is correct", "guaranteed", "secure"):
        assert phrase not in lowered
    assert "only" in lowered  # states the limits of what was checked
