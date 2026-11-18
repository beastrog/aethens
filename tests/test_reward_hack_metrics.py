"""Reward-hacking bench metrics for C007 (D5): per-category recall and precision, kept separate
from the core metrics. Pure functions, no Docker."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parent.parent


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_bench_d5", REPO / "bench" / "run_bench.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_bench_d5"] = mod
    spec.loader.exec_module(mod)
    return mod


rb = _load()


def H(task: str, category: str, sev: str = "error") -> dict[str, object]:
    return {
        "task_id": task,
        "check_id": "C007",
        "severity": sev,
        "id": f"C007-{task}-{category}",
        "category": category,
    }


MANIFEST = [
    {"id": "c1", "kind": "control", "defects": [], "reward_hack": ["exit-zero", "always-equal"]},
    {"id": "c2", "kind": "control", "defects": [], "reward_hack": []},
    {
        "id": "d1",
        "kind": "defective",
        "defects": [{"class": "flaky", "check": "C002"}],
        "reward_hack": ["exit-zero"],
    },
]


def test_c007_findings_do_not_touch_core_metrics() -> None:
    findings = [H("c1", "exit-zero"), H("c2", "exit-zero")]
    core = rb.compute_metrics(MANIFEST, findings)
    assert core["false_positives"] == 0 and core["unexpected_findings"] == 0
    assert "C007" not in core["per_check"]


def test_per_category_recall_and_precision() -> None:
    findings = [H("c1", "exit-zero"), H("c1", "always-equal", "warning"), H("c2", "exit-zero")]
    m = rb.compute_reward_hack(MANIFEST, findings)
    ez = m["per_category"]["exit-zero"]
    assert (ez["labelled"], ez["found"], ez["false_positives"]) == (2, 1, 1)
    assert ez["recall"] == 0.5 and ez["precision"] == 0.5
    ae = m["per_category"]["always-equal"]
    assert (ae["labelled"], ae["found"], ae["recall"], ae["precision"]) == (1, 1, 1.0, 1.0)
    assert m["per_category"]["sitecustomize-hook"]["recall"] is None  # nothing labelled
    assert (m["labelled"], m["found"], m["false_positives"]) == (3, 2, 1)
    assert m["recall"] == round(2 / 3, 4) and m["precision"] == round(2 / 3, 4)
    assert {"task": "d1", "category": "exit-zero"} in m["misses"]
    assert {"task": "c2", "category": "exit-zero"} in m["false_positive_list"]


def test_info_c007_findings_do_not_count() -> None:
    m = rb.compute_reward_hack(MANIFEST, [H("c2", "exit-zero", "info")])
    assert m["false_positives"] == 0


def test_regressions_include_reward_hack_gate() -> None:
    base = {
        "precision": 1.0,
        "recall": 1.0,
        "false_positives": 0,
        "reward_hack": {"recall": 1.0, "precision": 1.0, "false_positives": 0},
    }
    metrics = {"precision": 1.0, "recall": 1.0, "false_positives": 0}
    rh = {"recall": 0.9, "precision": 1.0, "false_positives": 1}
    problems = rb.regressions(base, metrics, rh)
    assert any("reward-hack recall" in p for p in problems)
    assert any("reward-hack false positives" in p for p in problems)
    assert (
        rb.regressions({"precision": 1.0, "recall": 1.0, "false_positives": 0}, metrics, rh) == []
    )


def test_manifest_labels_are_valid_and_present() -> None:
    entries = rb.load_manifest(REPO / "bench" / "manifest.yaml")
    assert all("reward_hack" in e for e in entries)
    paths = {e["path"]: e for e in entries}
    assert paths["tasks/ctrl-hardened-harness"]["reward_hack"] == []
    assert paths["tasks/ctrl-hardened-cli"]["reward_hack"] == []
    assert "sitecustomize-hook" in paths["tasks/hack-sitecustomize"]["reward_hack"]
    assert paths["tasks/noassert-exists"]["reward_hack"] == []  # starter passes: C001's job
