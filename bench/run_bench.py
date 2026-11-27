"""Run Aethens over the bench and compute precision, recall and false positives.

Usage: python bench/run_bench.py [--seed 0] [--budget standard] [--update-baseline]

Definitions (docs/AETHENS_PLAN.md section 6):
- A planted defect is found when a finding from the defect's expected check, with at least the
  defect's min_severity (default warning), exists on that task.
- precision = true findings / (true findings + false positives), counting only error and warning
  findings. A true finding is an error/warning on a defective task from one of its expected
  checks; a false positive is any error/warning on a control task.
- recall = planted defects found / planted defects.
- Error/warning findings on defective tasks from checks that were not expected are reported as
  "unexpected" (not counted in precision); info findings on controls are reported too.
- Reward hacking (C007, D5) is scored separately, because a verifier that a probe can game is a
  property of the harness, not one of the defect classes above, and nearly every plain unittest
  task is gameable. Every manifest entry lists, in ``reward_hack``, the probe categories that
  should get through its verifier (labels written before running C007). Per category: recall =
  labelled tasks with a C007 error/warning of that category / labelled tasks; a C007 error/warning
  of a category on a task not labelled with it is a false positive. C007 findings are left out
  of the core metrics.

Writes bench/results.json (deterministic for a seed: no timings) and compares the headline metrics
with bench/baseline.json. Exit 1 on regression, 2 on a tool error.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml

from aethens import __version__
from aethens.adapters import load_task
from aethens.audit import run_audit
from aethens.checks import (
    C001GoldSanity,
    C002Flakiness,
    C003LabeledCandidates,
    C004MutationProbes,
    C005OrderDependence,
    C006OverSpecified,
    C007RewardHacking,
    CheckContext,
)
from aethens.checks.c007_reward_hack import CATEGORIES
from aethens.errors import AethensError
from aethens.models import Budget, Task
from aethens.runner import DockerRunner

HERE = Path(__file__).resolve().parent
CLASSES = (
    "weak-tests",
    "over-strict",
    "flaky",
    "no-assertions",
    "broken-gold",
    "order-dependence",
)
CHECKS = ("C001", "C002", "C003", "C004", "C005", "C006")
RANK = {"info": 1, "warning": 2, "error": 3}


def load_manifest(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != "aethens-bench/v1":
        raise SystemExit(f"{path}: not an aethens-bench/v1 manifest")
    entries = []
    for e in data["tasks"]:
        kind = e["kind"]
        if kind not in ("control", "defective"):
            raise SystemExit(f"{e['path']}: bad kind {kind!r}")
        defects = e.get("defects", [])
        if (kind == "control") != (not defects):
            raise SystemExit(f"{e['path']}: controls have no defects, defective tasks need some")
        for d in defects:
            if d["class"] not in CLASSES or d["check"] not in CHECKS:
                raise SystemExit(f"{e['path']}: bad defect {d}")
        hack = e.get("reward_hack")
        if not isinstance(hack, list) or any(c not in CATEGORIES for c in hack):
            raise SystemExit(f"{e['path']}: reward_hack must list categories from {CATEGORIES}")
        entries.append({"path": e["path"], "kind": kind, "defects": defects, "reward_hack": hack})
    return entries


def compute_metrics(
    manifest: list[dict[str, Any]], findings: list[dict[str, Any]]
) -> dict[str, Any]:
    by_task: dict[str, list[dict[str, Any]]] = {}
    for f in findings:
        if f["check_id"] in CHECKS:  # C007 is scored by compute_reward_hack
            by_task.setdefault(str(f["task_id"]), []).append(f)
    planted = found = true_findings = false_positives = unexpected = info_on_controls = 0
    per_check = {c: {"planted": 0, "found": 0, "false_positives": 0} for c in CHECKS}
    per_class = {c: {"planted": 0, "found": 0} for c in CLASSES}
    misses: list[dict[str, str]] = []
    for entry in manifest:
        tid = entry["id"]
        fs = by_task.get(tid, [])
        loud = [f for f in fs if RANK[str(f["severity"])] >= RANK["warning"]]
        if entry["kind"] == "control":
            false_positives += len(loud)
            info_on_controls += len(fs) - len(loud)
            for f in loud:
                per_check[str(f["check_id"])]["false_positives"] += 1
            continue
        expected = {d["check"] for d in entry["defects"]}
        for f in loud:
            if f["check_id"] in expected:
                true_findings += 1
            else:
                unexpected += 1
        for d in entry["defects"]:
            need = RANK[d.get("min_severity", "warning")]
            hit = any(f["check_id"] == d["check"] and RANK[str(f["severity"])] >= need for f in fs)
            planted += 1
            per_check[d["check"]]["planted"] += 1
            per_class[d["class"]]["planted"] += 1
            if hit:
                found += 1
                per_check[d["check"]]["found"] += 1
                per_class[d["class"]]["found"] += 1
            else:
                misses.append({"task": tid, "class": d["class"], "check": d["check"]})
    denom = true_findings + false_positives
    return {
        "planted": planted,
        "found": found,
        "recall": round(found / planted, 4) if planted else 0.0,
        "true_findings": true_findings,
        "false_positives": false_positives,
        "precision": round(true_findings / denom, 4) if denom else 0.0,
        "unexpected_findings": unexpected,
        "info_on_controls": info_on_controls,
        "known_misses": misses,
        "per_check": per_check,
        "per_class": per_class,
    }


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 4) if b else None


def compute_reward_hack(
    manifest: list[dict[str, Any]], findings: list[dict[str, Any]]
) -> dict[str, Any]:
    hits: set[tuple[str, str]] = {
        (str(f["task_id"]), str(f.get("category")))
        for f in findings
        if f["check_id"] == "C007" and RANK[str(f["severity"])] >= RANK["warning"]
    }
    per: dict[str, dict[str, Any]] = {}
    misses: list[dict[str, str]] = []
    fps: list[dict[str, str]] = []
    for cat in CATEGORIES:
        labelled = found = false_pos = 0
        for e in manifest:
            tid = e["id"]
            if cat in e["reward_hack"]:
                labelled += 1
                if (tid, cat) in hits:
                    found += 1
                else:
                    misses.append({"task": tid, "category": cat})
            elif (tid, cat) in hits:
                false_pos += 1
                fps.append({"task": tid, "category": cat})
        per[cat] = {
            "labelled": labelled,
            "found": found,
            "false_positives": false_pos,
            "recall": _ratio(found, labelled),
            "precision": _ratio(found, found + false_pos),
        }
    labelled = sum(v["labelled"] for v in per.values())
    found = sum(v["found"] for v in per.values())
    false_pos = sum(v["false_positives"] for v in per.values())
    return {
        "labelled": labelled,
        "found": found,
        "false_positives": false_pos,
        "recall": _ratio(found, labelled) or 0.0,
        "precision": _ratio(found, found + false_pos) or 0.0,
        "per_category": per,
        "misses": misses,
        "false_positive_list": fps,
    }


def regressions(
    baseline: dict[str, Any],
    metrics: dict[str, Any],
    reward_hack: dict[str, Any] | None = None,
) -> list[str]:
    problems = []
    rb, rh = baseline.get("reward_hack"), reward_hack
    if rb is not None and rh is not None:
        if rh["recall"] < rb["recall"]:
            problems.append(f"reward-hack recall {rh['recall']} < baseline {rb['recall']}")
        if rh["precision"] < rb["precision"]:
            problems.append(f"reward-hack precision {rh['precision']} < baseline {rb['precision']}")
        if rh["false_positives"] > rb["false_positives"]:
            problems.append(
                f"reward-hack false positives {rh['false_positives']} > baseline "
                f"{rb['false_positives']}"
            )
    if metrics["precision"] < baseline["precision"]:
        problems.append(f"precision {metrics['precision']} < baseline {baseline['precision']}")
    if metrics["recall"] < baseline["recall"]:
        problems.append(f"recall {metrics['recall']} < baseline {baseline['recall']}")
    if metrics["false_positives"] > baseline["false_positives"]:
        problems.append(
            f"false positives {metrics['false_positives']} > baseline {baseline['false_positives']}"
        )
    return problems


def _audit_one(task: Task, seed: int, budget: Budget, runner: DockerRunner) -> list[dict[str, Any]]:
    checks = [
        C001GoldSanity(),
        C002Flakiness(),
        C003LabeledCandidates(),
        C004MutationProbes(),
        C005OrderDependence(),
        C006OverSpecified(),
        C007RewardHacking(),
    ]
    # jobs stays 1: this file already runs one task per worker. The result cache stays off
    # so the regression gate always re-executes (D-067).
    report = run_audit([task], checks, CheckContext(runner=runner, seed=seed, budget=budget))
    out: list[dict[str, Any]] = []
    for f in report.findings:
        row: dict[str, Any] = {
            "task_id": f.task_id,
            "check_id": f.check_id,
            "severity": f.severity.value,
            "id": f.id,
        }
        if f.check_id == "C007":
            row["category"] = f.evidence.extra.get("category", "")
        out.append(row)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--budget", choices=[b.value for b in Budget], default="standard")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--manifest", default=str(HERE / "manifest.yaml"))
    ap.add_argument("--results", default=str(HERE / "results.json"))
    ap.add_argument("--baseline", default=str(HERE / "baseline.json"))
    ap.add_argument("--update-baseline", action="store_true")
    args = ap.parse_args(argv)
    manifest = load_manifest(Path(args.manifest))
    try:
        tasks = [load_task(HERE / e["path"]) for e in manifest]
        runner = DockerRunner()
        runner.ensure_available()
    except AethensError as exc:
        print(f"bench: error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    for e, t in zip(manifest, tasks, strict=True):
        e["id"] = t.id
    budget = Budget(args.budget)
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            parts = list(pool.map(lambda t: _audit_one(t, args.seed, budget, runner), tasks))
    except AethensError as exc:
        print(f"bench: error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    findings = sorted((f for p in parts for f in p), key=lambda f: (f["task_id"], f["id"]))
    metrics = compute_metrics(manifest, findings)
    hack = compute_reward_hack(manifest, findings)
    results = {
        "schema": "aethens-bench-results/v1",
        "tool_version": __version__,
        "seed": args.seed,
        "budget": budget.value,
        "tasks": len(tasks),
        "controls": sum(1 for e in manifest if e["kind"] == "control"),
        "defective": sum(1 for e in manifest if e["kind"] == "defective"),
        "metrics": metrics,
        "reward_hack": hack,
        "findings": findings,
    }
    Path(args.results).write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(
        f"bench: {results['tasks']} tasks ({results['controls']} controls, "
        f"{results['defective']} defective), seed {args.seed}, budget {budget.value}"
    )
    print(
        f"bench: precision {metrics['precision']}  recall {metrics['recall']} "
        f"({metrics['found']}/{metrics['planted']})  "
        f"false positives {metrics['false_positives']}  "
        f"unexpected {metrics['unexpected_findings']}  "
        f"info on controls {metrics['info_on_controls']}"
    )
    for c, v in metrics["per_check"].items():
        fp = v["false_positives"]
        print(f"bench:   {c}: found {v['found']}/{v['planted']}, false positives {fp}")
    for m in metrics["known_misses"]:
        print(f"bench:   miss: {m['task']} ({m['class']}, expected {m['check']})")
    print(
        f"bench: reward hacking (C007): recall {hack['recall']} ({hack['found']}/"
        f"{hack['labelled']})  precision {hack['precision']}  "
        f"false positives {hack['false_positives']}"
    )
    for cat, v in hack["per_category"].items():
        print(
            f"bench:   {cat}: found {v['found']}/{v['labelled']}, "
            f"false positives {v['false_positives']}"
        )
    for m in hack["misses"]:
        print(f"bench:   reward-hack miss: {m['task']} ({m['category']})")
    for m in hack["false_positive_list"]:
        print(f"bench:   reward-hack false positive: {m['task']} ({m['category']})")
    baseline_path = Path(args.baseline)
    headline = {k: metrics[k] for k in ("precision", "recall", "false_positives")}
    if args.update_baseline:
        rh_head = {k: hack[k] for k in ("recall", "precision", "false_positives")}
        base = {"seed": args.seed, "budget": budget.value, **headline, "reward_hack": rh_head}
        baseline_path.write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8")
        print(f"bench: baseline written to {baseline_path}")
        return 0
    if not baseline_path.exists():
        print(f"bench: error: no baseline at {baseline_path}", file=sys.stderr)
        return 2
    base = json.loads(baseline_path.read_text(encoding="utf-8"))
    if (base["seed"], base["budget"]) != (args.seed, budget.value):
        print("bench: error: baseline was recorded with another seed or budget", file=sys.stderr)
        return 2
    problems = regressions(base, metrics, hack)
    for p in problems:
        print(f"bench: REGRESSION: {p}", file=sys.stderr)
    if not problems:
        print("bench: no regression against bench/baseline.json")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
