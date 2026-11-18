"""JSON round-trip and validation tests for the core models (B1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aethens import __version__
from aethens.errors import SchemaError
from aethens.models import (
    REPORT_SCHEMA,
    Budget,
    Candidate,
    Confidence,
    Evidence,
    Finding,
    Label,
    LabelSource,
    Report,
    Severity,
    Task,
)


def _candidate() -> Candidate:
    return Candidate(
        name="sorted-builtin",
        path=Path("candidates/valid/sorted-builtin"),
        label=Label.VALID,
        label_source=LabelSource.HUMAN,
    )


def _task() -> Task:
    return Task(
        id="add-two",
        root=Path("/tmp/tasks/add-two"),
        language="python",
        image="python:3.12-slim",
        statement=Path("statement.md"),
        starter=Path("starter"),
        tests=Path("tests"),
        verifier=("python", "-m", "unittest", "discover", "-s", "tests"),
        timeout_s=30,
        gold=Path("gold"),
        candidates=(_candidate(),),
    )


def _finding() -> Finding:
    return Finding(
        id="C001-add-two-0123abcd",
        check_id="C001",
        severity=Severity.ERROR,
        task_id="add-two",
        title="Gold solution fails the verifier",
        detail="The reference solution should pass but the verifier exited 1.",
        evidence=Evidence(
            subject="gold",
            command=("python", "-m", "unittest"),
            observed="exit code 1",
            exit_codes=(1,),
            timed_out=False,
            stdout_tail="",
            stderr_tail="FAILED (failures=1)",
            extra={"runs": "1"},
        ),
        repro="aethens audit tasks/add-two --check C001 --seed 7",
        seed=7,
        confidence=Confidence.CONFIRMED,
        limits="One run; the verifier may be flaky (see C002).",
    )


def _report() -> Report:
    return Report(
        tool_version=__version__,
        task_ids=("add-two",),
        checks_run=("C001",),
        budget=Budget.STANDARD,
        seed=7,
        findings=(_finding(),),
        started_at="2026-11-18T10:00:00+00:00",
        duration_s=1.25,
    )


def test_candidate_round_trip() -> None:
    c = _candidate()
    assert Candidate.from_dict(json.loads(json.dumps(c.to_dict()))) == c


def test_task_round_trip() -> None:
    t = _task()
    assert Task.from_dict(json.loads(json.dumps(t.to_dict()))) == t


def test_finding_round_trip() -> None:
    f = _finding()
    assert Finding.from_dict(json.loads(json.dumps(f.to_dict()))) == f


def test_report_round_trip_and_schema_constant() -> None:
    r = _report()
    data = json.loads(json.dumps(r.to_dict()))
    assert data["schema"] == REPORT_SCHEMA == "aethens-report/v2"
    assert Report.from_dict(data) == r


def test_report_rejects_wrong_schema() -> None:
    data = _report().to_dict()
    data["schema"] = "aethens-report/v0"
    with pytest.raises(SchemaError):
        Report.from_dict(data)


def test_enums_reject_unknown_values() -> None:
    data = _finding().to_dict()
    data["severity"] = "critical"
    with pytest.raises(SchemaError):
        Finding.from_dict(data)
    cdata = _candidate().to_dict()
    cdata["label_source"] = "gut-feeling"
    with pytest.raises(SchemaError):
        Candidate.from_dict(cdata)


def test_missing_field_raises_schema_error() -> None:
    data = _finding().to_dict()
    del data["repro"]
    with pytest.raises(SchemaError):
        Finding.from_dict(data)


def test_unreviewed_label_cannot_be_confirmed() -> None:
    # AGENTS.md rule 3: an unreviewed label never produces a confirmed finding.
    # The Finding model cannot know the label, so this is enforced by a helper.
    from aethens.models import confidence_for

    assert confidence_for(LabelSource.LLM_UNREVIEWED) is Confidence.NEEDS_REVIEW
    assert confidence_for(LabelSource.HUMAN) is Confidence.CONFIRMED
    assert confidence_for(LabelSource.ORACLE) is Confidence.CONFIRMED


def test_severity_ordering() -> None:
    assert Severity.ERROR.rank > Severity.WARNING.rank > Severity.INFO.rank
