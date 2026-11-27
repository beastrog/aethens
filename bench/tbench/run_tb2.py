"""Audit converted Terminal-Bench 2 tasks with the public CLI, one `aethens audit` call per task.

Usage: python bench/tbench/run_tb2.py TASKS_DIR OUT_DIR [--budget smoke] [--seed 0] [--only a,b]

Writes OUT_DIR/reports/<task>.json and OUT_DIR/run.json (exit code, wall time, finding counts and
the exact command per task). Same shape as bench/real/run_real.py on the feat/adapters branch
(PR #3); once that merges this script can be replaced by it.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--budget", default="smoke")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--only", default="")
    a = ap.parse_args(argv)
    only = {n for n in a.only.split(",") if n}
    (a.out / "reports").mkdir(parents=True, exist_ok=True)
    run_path = a.out / "run.json"
    run: dict[str, Any] = json.loads(run_path.read_text()) if run_path.exists() else {}
    for task in sorted(p for p in a.tasks.iterdir() if (p / "task.yaml").is_file()):
        if only and task.name not in only:
            continue
        report = a.out / "reports" / f"{task.name}.json"
        cmd = [
            "aethens",
            "audit",
            str(task),
            "--seed",
            str(a.seed),
            "--budget",
            a.budget,
            "--output",
            str(report),
        ]
        t0 = time.monotonic()
        proc = subprocess.run(  # noqa: S603 - this repo's own CLI
            [sys.executable, "-m", "aethens", *cmd[1:]], capture_output=True, text=True, check=False
        )
        counts: dict[str, int] = {}
        if report.exists():
            for f in json.loads(report.read_text(encoding="utf-8")).get("findings", []):
                k = f"{f['check_id']}:{f['severity']}"
                counts[k] = counts.get(k, 0) + 1
        run[task.name] = {
            "command": " ".join(cmd),
            "exit_code": proc.returncode,
            "wall_s": round(time.monotonic() - t0, 1),
            "findings": counts,
            "stderr_tail": proc.stderr[-800:] if proc.returncode == 2 else "",
        }
        print(task.name, run[task.name]["exit_code"], counts, flush=True)
        run_path.write_text(json.dumps(run, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
