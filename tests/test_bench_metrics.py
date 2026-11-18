"""Pure bench metric and regression-gate functions (B6)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_bench", REPO / "bench" / "run_bench.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_bench"] = mod
    spec.loader.exec_module(mod)
    return mod


rb = _load()


def F(task: str, check: str, sev: str) -> dict[str, object]:
    return {"task_id": task, "check_id": check, "severity": sev, "id": f"{check}-{task}-x"}


MANIFEST = [
    {"id": "d1", "kind": "defective", "defects": [{"class": "flaky", "check": "C002"}]},
    {"id": "d2", "kind": "defective", "defects": [{"class": "weak-tests", "check": "C003"}]},
    {
        "id": "d3",
        "kind": "defective",
        "defects": [{"class": "weak-tests", "check": "C004", "min_severity": "info"}],
    },
    {"id": "c1", "kind": "control", "defects": []},
]


def test_metrics_basic() -> None:
    findings = [
        F("d1", "C002", "error"),
        F("d1", "C001", "error"),  # unexpected on a defective task
        F("d3", "C004", "info"),
        F("c1", "C004", "info"),  # info on a control is not a false positive
    ]
    m = rb.compute_metrics(MANIFEST, findings)
    assert m["planted"] == 3 and m["found"] == 2
    assert m["recall"] == round(2 / 3, 4)
    assert m["true_findings"] == 1 and m["false_positives"] == 0
    assert m["precision"] == 1.0
    assert m["unexpected_findings"] == 1
    assert m["info_on_controls"] == 1
    assert m["known_misses"] == [{"task": "d2", "class": "weak-tests", "check": "C003"}]
    assert m["per_class"]["weak-tests"] == {"planted": 2, "found": 1}
    assert m["per_check"]["C002"]["found"] == 1


def test_false_positive_on_control() -> None:
    m = rb.compute_metrics(MANIFEST, [F("c1", "C002", "warning"), F("d1", "C002", "error")])
    assert m["false_positives"] == 1
    assert m["precision"] == 0.5
    assert m["per_check"]["C002"]["false_positives"] == 1


def test_severity_threshold() -> None:
    # A C003 info finding does not count for a defect whose min severity defaults to warning.
    m = rb.compute_metrics(MANIFEST, [F("d2", "C003", "info")])
    assert m["found"] == 0


def test_gate() -> None:
    base = {"precision": 1.0, "recall": 0.9, "false_positives": 0}
    ok = {"precision": 1.0, "recall": 0.95, "false_positives": 0}
    assert rb.regressions(base, ok) == []
    worse = {"precision": 0.9, "recall": 0.8, "false_positives": 2}
    problems = rb.regressions(base, worse)
    assert len(problems) == 3
