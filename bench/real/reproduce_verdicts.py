"""Reproduce the manual verdicts of a real-benchmark audit in the Docker sandbox.

Usage: python bench/real/reproduce_verdicts.py OUT_DIR TASKS_DIR [VERDICTS_JSON]

For every finding judged a true positive in VERDICTS_JSON (default:
audits/private/mbppplus/verdicts.json, gitignored because third-party findings stay private,
see docs/DISCLOSURE.md) this:
  1. rebuilds the surviving mutant from the finding's subject (C004's own mutation key);
  2. runs the task's full verifier on the mutant (must still pass: the tests accept it);
  3. runs gold and mutant on the verdict's input (they must differ: the mutant is wrong there).
For every C001 finding it reruns the gold with 4 GiB instead of 1 GiB (is it only the limit?).
Writes OUT_DIR/verification.json. Every run uses the normal sandbox (no network, non-root).
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from aethens.adapters import load_task
from aethens.checks.base import run_spec
from aethens.checks.mutation import enumerate_sites, make_mutant
from aethens.runner import DockerRunner
from aethens.runner.base import Limits, RunSpec

HERE = Path(__file__).resolve().parent
VERDICTS = HERE.parent.parent / "audits" / "private" / "mbppplus" / "verdicts.json"

CALL = """
import json, signal, sys
sys.setrecursionlimit(10000)
import importlib.util
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
def handler(s, f):
    raise TimeoutError("no result within 10 s")
signal.signal(signal.SIGALRM, handler)
out = {}
for who in ("gold", "mutant"):
    fn = getattr(load(who, who + ".py"), sys.argv[1])
    signal.alarm(10)
    try:
        out[who] = repr(fn(*eval(sys.argv[2])))
    except BaseException as e:
        out[who] = "raised " + type(e).__name__ + ": " + str(e)[:80]
    finally:
        signal.alarm(0)
print(json.dumps(out))
"""


def mutant_source(gold: str, subject: str) -> str:
    _, _f, index, operator, sub = subject.split(":")
    for site in enumerate_sites(gold):
        if (site.index, site.operator, site.sub) == (int(index), operator, int(sub)):
            return make_mutant(gold, site).source
    raise ValueError(subject)


def main(argv: list[str]) -> int:
    out_dir, tasks = Path(argv[0]), Path(argv[1])
    verdicts = json.loads((Path(argv[2]) if len(argv) > 2 else VERDICTS).read_text())
    runner = DockerRunner()
    results: dict[str, Any] = {}
    for rep in sorted((out_dir / "reports").glob("*.json")):
        for f in json.loads(rep.read_text())["findings"]:
            key = f["id"] if f["check_id"] == "C004" else f"C001-{f['task_id']}"
            v = verdicts.get(key, {})
            task = load_task(tasks / f["task_id"])
            if f["check_id"] == "C001":
                big = run_spec(task, task.gold, {"PYTHONHASHSEED": "0"})
                spec = RunSpec(
                    image=big.image,
                    command=big.command,
                    layers=big.layers,
                    timeout_s=600.0,
                    limits=Limits(memory_mb=4096),
                )
                r = runner.run(spec)
                results[key] = {
                    "gold_4GiB": {
                        "exit": r.exit_code,
                        "oom": r.oom_killed,
                        "timed_out": r.timed_out,
                        "seconds": round(r.duration_s, 1),
                        "stderr_tail": r.stderr_tail[-300:],
                    }
                }
                continue
            if v.get("verdict") != "tp":
                continue
            gold = (task.root / "gold" / "solution.py").read_text()
            mutant = mutant_source(gold, f["evidence"]["subject"])
            entry = json.loads((task.root / "PROVENANCE.json").read_text())["entry_point"]
            with tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp)
                (d / "overlay").mkdir()
                (d / "overlay" / "solution.py").write_text(mutant)
                base = run_spec(task, d / "overlay", {"PYTHONHASHSEED": "0"})
                verdict_run = runner.run(base)
                (d / "call").mkdir()
                (d / "call" / "gold.py").write_text(gold)
                (d / "call" / "mutant.py").write_text(mutant)
                (d / "call" / "call.py").write_text(CALL)
                call = runner.run(
                    RunSpec(
                        image=task.image,
                        command=("python", "call.py", entry, v["input"]),
                        layers=((d / "call", Path(".")),),
                        timeout_s=60.0,
                    )
                )
            outs = (
                json.loads(call.stdout_tail.strip().splitlines()[-1]) if call.exit_code == 0 else {}
            )
            results[key] = {
                "verifier_accepts_mutant": verdict_run.passed,
                "input": v["input"],
                "gold_output": outs.get("gold"),
                "mutant_output": outs.get("mutant"),
                "differs": bool(outs) and outs.get("gold") != outs.get("mutant"),
            }
    (out_dir / "verification.json").write_text(json.dumps(results, indent=1) + "\n")
    ok = sum(1 for r in results.values() if r.get("verifier_accepts_mutant") and r.get("differs"))
    print(f"reproduce: {ok} of {sum(1 for r in results.values() if 'input' in r)} tp reproduced")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
