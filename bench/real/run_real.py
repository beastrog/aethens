"""Run `aethens audit` over a directory of imported real-benchmark tasks, one CLI call per task.

Usage:
  python bench/real/run_real.py TASKS_DIR OUT_DIR [--check C001 ...] [--workers 6] [--seed 0]
                               [--budget standard] [--only id1,id2] [--limit N]

Writes OUT_DIR/reports/<task>.json (the normal aethens report) and OUT_DIR/run.json (exit code, wall
time and finding counts per task, plus the exact command). Each task is audited by the public CLI,
so every finding's repro command is the one a user would run. Needs Docker and the task images.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any


def audit_one(task: Path, out: Path, checks: list[str], seed: int, budget: str) -> dict[str, Any]:
    report = out / "reports" / f"{task.name}.json"
    cmd = [
        sys.executable,
        "-m",
        "aethens",
        "audit",
        str(task),
        "--seed",
        str(seed),
        "--budget",
        budget,
        "--output",
        str(report),
    ]
    for c in checks:
        cmd += ["--check", c]
    t0 = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    wall = round(time.monotonic() - t0, 2)
    counts: dict[str, int] = {}
    if report.exists():
        data = json.loads(report.read_text(encoding="utf-8"))
        for f in data.get("findings", []):
            key = f"{f['check_id']}:{f['severity']}"
            counts[key] = counts.get(key, 0) + 1
    return {
        "task": task.name,
        "exit_code": proc.returncode,
        "wall_s": wall,
        "findings": counts,
        "stderr_tail": proc.stderr[-800:] if proc.returncode == 2 else "",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks")
    ap.add_argument("out")
    ap.add_argument("--check", action="append", dest="checks", default=[])
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--budget", default="standard")
    ap.add_argument("--only", default="")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)
    tasks = sorted(p for p in Path(args.tasks).iterdir() if (p / "task.yaml").exists())
    if args.only:
        keep = set(args.only.split(","))
        tasks = [t for t in tasks if t.name in keep]
    if args.limit:
        tasks = tasks[: args.limit]
    out = Path(args.out)
    (out / "reports").mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(
            pool.map(lambda t: audit_one(t, out, args.checks, args.seed, args.budget), tasks)
        )
    from aethens import __version__

    run = {
        "aethens_version": __version__,
        "checks": args.checks or "all",
        "seed": args.seed,
        "budget": args.budget,
        "workers": args.workers,
        "tasks": len(rows),
        "wall_s_total": round(time.monotonic() - t0, 1),
        "results": sorted(rows, key=lambda r: r["task"]),
    }
    (out / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    errors = sum(1 for r in rows if r["exit_code"] == 2)
    print(f"run_real: {len(rows)} tasks, {errors} tool errors, {run['wall_s_total']} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
