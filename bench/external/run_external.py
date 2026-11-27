"""External bench: measure Aethens on public tasks it did not write (HumanEval + HumanEval+).

Usage:
  python bench/external/run_external.py --sample        # vendored offline subset (make check)
  python bench/external/run_external.py --full          # all 164 tasks (needs fetch + convert)
  options: --seed 0 --budget standard --workers 4 --exhaustive --update-baseline

Ground truth (see bench/external/README.md):
- C004 (weak tests): a surviving mutant is a claim "the tests do not check this behaviour". It is
  CONFIRMED when EvalPlus's HumanEval+ tests (an outside oracle with many more inputs and expected
  outputs from EvalPlus's reference) reject the same mutant, i.e. the mutant is provably wrong and
  the original HumanEval tests accepted it. precision = confirmed / survivors judged by the oracle.
  With --exhaustive, every mutant of every gold is also run, and a task counts as weak when at least
  one mutant passes the base tests but fails the oracle; recall = weak tasks on which the budgeted
  C004 run reported a confirmed survivor / weak tasks (recall relative to exhaustive mutation with
  Aethens' own operators, not to every possible wrong program).
  C004's equivalent-mutant filter (D-065) hides survivors that behaved like the gold on every
  input its probe tried. Those are judged by the oracle too, so the same run also gives the
  numbers without the filter, and how many true positives the filter hid.
- C001, C002, C005, C006: HumanEval's tasks carry no labels for these defect classes. They
  are treated as presumed clean: every error/warning finding is counted and listed for review, and
  no precision is claimed from zero findings.
- C007 (reward-hacking probes) is not run here: the verifier is Aethens' own unittest conversion
  of HumanEval's check function, so whether a probe gets through says nothing about HumanEval.
- Tasks whose ORIGINAL HumanEval canonical solution fails the HumanEval+ oracle cannot use the
  oracle; they are listed and excluded from C004 precision and recall.

Writes the results JSON (deterministic for a seed; no timings) and, for --sample, compares it
with the sample baseline. Exit 1 on regression, 2 on a tool error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from aethens import __version__
from aethens.adapters import load_task
from aethens.audit import run_audit
from aethens.checks import Check, CheckContext, hash_seed
from aethens.checks.base import describe, run_spec
from aethens.checks.c004_mutation import MUTANT_CAP
from aethens.checks.mutation import Mutant, select_mutants
from aethens.cli.main import ALL_CHECKS
from aethens.errors import AethensError
from aethens.models import Budget, Finding, Task
from aethens.runner import DockerRunner, Runner, RunSpec

HERE = Path(__file__).resolve().parent
LOUD = ("error", "warning")
ORACLE_TIMEOUT_S = 60.0
# C003 needs labelled candidates (HumanEval has none). C007 is not run: the unittest harness here
# is Aethens' own conversion, not HumanEval's, so probe results would measure the converter.
EXCLUDED_CHECKS = ("C003", "C007")
DATASETS = [
    {
        "name": "HumanEval",
        "role": "tasks: prompt, original canonical solution, original base tests",
        "licence": "MIT",
        "source": "github.com/openai/human-eval @ b9453e8f",
    },
    {
        "name": "HumanEval+ (EvalPlus)",
        "role": "oracle only: extended tests with expected outputs from EvalPlus's reference",
        "licence": "Apache-2.0",
        "source": "huggingface.co/datasets/evalplus/humanevalplus @ d32357cf",
    },
]


def gold_files(task: Task) -> dict[str, str]:
    gold_dir = task.root / task.gold
    return {
        p.relative_to(gold_dir).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(gold_dir.rglob("*.py"))
        if p.is_file()
    }


def oracle_spec(task: Task, oracle_tests: Path, overlay: Path, hs: str) -> RunSpec:
    """starter, then the overlay, then the ORACLE tests in place of the task's own tests."""
    return RunSpec(
        image=task.image,
        command=task.verifier,
        layers=(
            (task.root / task.starter, Path(".")),
            (overlay, Path(".")),
            (oracle_tests, task.tests),
        ),
        # The oracle is not the audited verifier: give it room so that machine load never turns a
        # slow-but-correct run into a false "oracle rejects".
        timeout_s=max(ORACLE_TIMEOUT_S, float(task.timeout_s)),
        env={"PYTHONHASHSEED": hs},
    )


def run_mutant(runner: Runner, task: Task, m: Mutant, tests: Path | None, tmp: Path) -> bool:
    """True when the mutant passes: the task's own tests (tests=None) or the oracle tests."""
    overlay = tmp / f"m-{hashlib.sha256(m.key.encode()).hexdigest()[:16]}"
    gold_dir = task.root / task.gold
    if not overlay.exists():
        shutil.copytree(gold_dir, overlay, symlinks=False)
        (overlay / m.file).write_text(m.source, encoding="utf-8")
    hs = str(hash_seed(0, task.id, "external", m.key))
    if tests is None:
        return runner.run(run_spec(task, overlay, {"PYTHONHASHSEED": hs})).passed
    return runner.run(oracle_spec(task, tests, overlay, hs)).passed


def audit_task(
    task: Task,
    oracle_dir: Path,
    checks: Sequence[Check],
    seed: int,
    budget: Budget,
    runner: Runner,
    exhaustive: bool,
) -> dict[str, Any]:
    oracle_tests = oracle_dir / task.id / "tests"
    hs = str(hash_seed(seed, task.id, "external", "oracle-gold"))
    gold_run = runner.run(oracle_spec(task, oracle_tests, task.root / task.gold, hs))
    gold_ok = gold_run.passed
    # jobs stays 1: the caller already runs one task per worker. No result cache (D-067).
    report = run_audit([task], checks, CheckContext(runner=runner, seed=seed, budget=budget))
    findings: list[Finding] = list(report.findings)
    out: dict[str, Any] = {
        "task": task.id,
        "oracle_accepts_gold": gold_ok,
        "oracle_gold_run": describe(gold_run),
        "findings": [
            {"check_id": f.check_id, "severity": f.severity.value, "id": f.id, "title": f.title}
            for f in findings
        ],
        "survivors": [],
        "filtered": [],
    }
    files = gold_files(task)
    mutants = select_mutants(files, seed=seed, salt=task.id, cap=MUTANT_CAP[budget])
    by_key = {f"mutant:{m.key}": m for m in mutants}
    with tempfile.TemporaryDirectory(prefix="aethens-ext-") as tmpd:
        tmp = Path(tmpd)
        for f in findings:
            if f.check_id != "C004" or not f.evidence.subject.startswith("mutant:"):
                continue
            m = by_key[f.evidence.subject]
            verdict = "no-oracle"
            if gold_ok:
                killed = not run_mutant(runner, task, m, oracle_tests, tmp)
                verdict = "confirmed" if killed else "unconfirmed"
            out["survivors"].append({"mutant": m.key, "line": m.site.line, "oracle": verdict})
        hidden = [
            key
            for c in report.coverage
            if c.check_id == "C004"
            for key in c.stats.get("likely_equivalent_mutants", "").split(",")
            if key
        ]
        for key in hidden:
            m = by_key[f"mutant:{key}"]
            verdict = "no-oracle"
            if gold_ok:
                killed = not run_mutant(runner, task, m, oracle_tests, tmp)
                verdict = "confirmed" if killed else "unconfirmed"
            out["filtered"].append({"mutant": m.key, "line": m.site.line, "oracle": verdict})
        if exhaustive and gold_ok:
            every = select_mutants(files, seed=seed, salt=task.id, cap=10**6)
            weak_keys = []
            for m in every:
                if run_mutant(runner, task, m, None, tmp) and not run_mutant(
                    runner, task, m, oracle_tests, tmp
                ):
                    weak_keys.append(m.key)
            out["exhaustive"] = {"mutants": len(every), "base_pass_oracle_fail": len(weak_keys)}
    return out


def compute(results: list[dict[str, Any]], check_ids: Sequence[str]) -> dict[str, Any]:
    per_check: dict[str, Any] = {}
    no_oracle = sorted(r["task"] for r in results if not r["oracle_accepts_gold"])
    for c in check_ids:
        loud = [
            {"task": r["task"], "id": f["id"], "severity": f["severity"], "title": f["title"]}
            for r in results
            for f in r["findings"]
            if f["check_id"] == c and f["severity"] in LOUD
        ]
        entry: dict[str, Any] = {
            "ground_truth": "presumed clean (no labels for this class in the dataset)",
            "loud_findings": len(loud),
            "tasks_with_loud_findings": len({x["task"] for x in loud}),
            "loud_finding_list": loud,
            "precision": None,
            "recall": None,
        }
        if c == "C004":
            surv = [s for r in results for s in r["survivors"]]
            judged = [s for s in surv if s["oracle"] != "no-oracle"]
            confirmed = sum(1 for s in judged if s["oracle"] == "confirmed")
            hid = [s for r in results for s in r.get("filtered", [])]
            hid_judged = [s for s in hid if s["oracle"] != "no-oracle"]
            hid_confirmed = sum(1 for s in hid_judged if s["oracle"] == "confirmed")
            all_judged = len(judged) + len(hid_judged)
            entry.update(
                {
                    "ground_truth": "HumanEval+ (EvalPlus) tests reject the surviving mutant",
                    "survivors": len(surv),
                    "survivors_judged_by_oracle": len(judged),
                    "confirmed": confirmed,
                    "unconfirmed": len(judged) - confirmed,
                    "precision": round(confirmed / len(judged), 4) if judged else None,
                    "filtered_as_equivalent": len(hid),
                    "filtered_judged_by_oracle": len(hid_judged),
                    "filtered_rejected_by_oracle": hid_confirmed,
                    "precision_without_filter": (
                        round((confirmed + hid_confirmed) / all_judged, 4) if all_judged else None
                    ),
                    "tasks_with_confirmed_survivor": len(
                        {
                            r["task"]
                            for r in results
                            if any(s["oracle"] == "confirmed" for s in r["survivors"])
                        }
                    ),
                }
            )
            ex = [r for r in results if "exhaustive" in r]
            if ex:
                weak = [r for r in ex if r["exhaustive"]["base_pass_oracle_fail"] > 0]
                hit = [r for r in weak if any(s["oracle"] == "confirmed" for s in r["survivors"])]
                hit_nf = [
                    r
                    for r in weak
                    if any(
                        s["oracle"] == "confirmed" for s in r["survivors"] + r.get("filtered", [])
                    )
                ]
                entry["recall"] = round(len(hit) / len(weak), 4) if weak else None
                entry["recall_without_filter"] = round(len(hit_nf) / len(weak), 4) if weak else None
                entry["recall_detail"] = {
                    "definition": "weak = some mutant (exhaustive, Aethens operators) passes the "
                    "base tests and fails HumanEval+",
                    "tasks_exhaustively_mutated": len(ex),
                    "weak_tasks": len(weak),
                    "weak_tasks_found_at_budget": len(hit),
                    "weak_tasks_found_at_budget_without_filter": len(hit_nf),
                }
        per_check[c] = entry
    return {"tasks_without_oracle": no_oracle, "per_check": per_check}


def regressions(base: dict[str, Any], metrics: dict[str, Any]) -> list[str]:
    problems = []
    for c, b in base["per_check"].items():
        m = metrics["per_check"].get(c)
        if m is None:
            problems.append(f"{c} missing from results")
            continue
        if m["loud_findings"] > b["loud_findings"]:
            problems.append(f"{c}: loud findings {m['loud_findings']} > {b['loud_findings']}")
        for k in ("precision", "recall"):
            if b.get(k) is not None and (m.get(k) is None or m[k] < b[k]):
                problems.append(f"{c}: {k} {m.get(k)} < baseline {b[k]}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    which = ap.add_mutually_exclusive_group(required=True)
    which.add_argument("--sample", action="store_true")
    which.add_argument("--full", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--budget", choices=[b.value for b in Budget], default="standard")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--exhaustive", action="store_true")
    ap.add_argument("--update-baseline", action="store_true")
    args = ap.parse_args(argv)
    root = HERE / ("sample" if args.sample else "full")
    results_path = HERE / ("sample-results.json" if args.sample else "results.json")
    baseline_path = HERE / "sample-baseline.json"
    check_ids = [c for c in sorted(ALL_CHECKS) if c not in EXCLUDED_CHECKS]
    checks = [ALL_CHECKS[c]() for c in check_ids]
    budget = Budget(args.budget)
    try:
        names = sorted(p.name for p in (root / "tasks").iterdir() if p.is_dir())
        tasks = [load_task(root / "tasks" / n) for n in names]
        runner = DockerRunner()
        runner.ensure_available()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            per_task = list(
                pool.map(
                    lambda t: audit_task(
                        t, root / "oracle", checks, args.seed, budget, runner, args.exhaustive
                    ),
                    tasks,
                )
            )
    except (AethensError, FileNotFoundError) as exc:
        print(f"external: error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    metrics = compute(per_task, check_ids)
    results = {
        "schema": "aethens-external-bench/v1",
        "tool_version": __version__,
        "subset": "sample" if args.sample else "full",
        "seed": args.seed,
        "budget": budget.value,
        "datasets": DATASETS,
        "tasks": len(tasks),
        "checks": check_ids,
        "exhaustive": args.exhaustive,
        "metrics": metrics,
        "per_task": per_task,
    }
    results_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(
        f"external: {len(tasks)} {results['subset']} tasks, seed {args.seed}, budget {budget.value}"
    )
    print(f"external: tasks without a usable oracle: {len(metrics['tasks_without_oracle'])}")
    for c, v in metrics["per_check"].items():
        line = f"external:   {c}: loud findings {v['loud_findings']}"
        if c == "C004":
            line += (
                f", survivors {v['survivors']}, confirmed {v['confirmed']}/"
                f"{v['survivors_judged_by_oracle']}, precision {v['precision']}, "
                f"recall {v['recall']}; filtered as equivalent {v['filtered_as_equivalent']} "
                f"(oracle rejects {v['filtered_rejected_by_oracle']}), precision without the "
                f"filter {v['precision_without_filter']}"
            )
        print(line)
    if not args.sample:
        return 0
    if args.update_baseline:
        base = {
            "seed": args.seed,
            "budget": budget.value,
            "per_check": {
                c: {k: v.get(k) for k in ("loud_findings", "precision", "recall")}
                for c, v in metrics["per_check"].items()
            },
        }
        baseline_path.write_text(json.dumps(base, indent=2) + "\n", encoding="utf-8")
        print(f"external: baseline written to {baseline_path}")
        return 0
    base = json.loads(baseline_path.read_text(encoding="utf-8"))
    problems = regressions(base, metrics)
    for p in problems:
        print(f"external: REGRESSION: {p}", file=sys.stderr)
    if not problems:
        print("external: no regression against bench/external/sample-baseline.json")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
