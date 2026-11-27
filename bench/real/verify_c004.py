"""Verification aid for C004 survivors on EvalPlus-imported tasks: search for a counterexample.

Usage: python bench/real/verify_c004.py OUT_DIR TASKS_DIR [--workers 6]

For every C004 finding in OUT_DIR/reports/*.json this rebuilds the surviving mutant from the
finding's diff, then runs (inside the normal Docker sandbox) the gold and the mutant on perturbed
versions of the task's own test inputs, comparing them with the task's own `assertion` helper.
A counterexample is an input on which the gold runs without error and the verifier's comparison
tells gold and mutant apart; the tests then accept a solution that is wrong on that input.
No counterexample does not prove equivalence. Every counterexample still needs a human check that
the input is valid for the problem statement (results: OUT_DIR/c004_counterexamples.json).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from aethens.checks.mutation import enumerate_sites, make_mutant
from aethens.runner import DockerRunner
from aethens.runner.base import RunSpec

DRIVER = r"""
import ast, copy, importlib.util, json, math, random, signal, sys
from math import inf

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

entry = sys.argv[1]
src = open("check.py").read()
tree = ast.parse(src)
ns = {"inf": inf, "math": math}
assertion = None
for node in tree.body:
    if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef)) or (
        isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "inputs" for t in node.targets)
    ):
        try:
            exec(compile(ast.Module([node], []), "check.py", "exec"), ns)
        except Exception:
            pass
inputs = ns.get("inputs", [])
assertion = ns.get("assertion")
gold = getattr(load("gold_mod", "gold.py"), entry)
mut = getattr(load("mut_mod", "mutant.py"), entry)

class TO(Exception):
    pass

def handler(s, f):
    raise TO()

signal.signal(signal.SIGALRM, handler)

def call(fn, inp):
    signal.alarm(2)
    try:
        return ("ok", fn(*copy.deepcopy(inp)))
    except TO:
        return ("timeout", None)
    except BaseException as e:
        return ("raise", type(e).__name__)
    finally:
        signal.alarm(0)

def variants(x, rnd):
    if isinstance(x, bool):
        return [not x]
    if isinstance(x, int):
        return [x + 1, x - 1, -x, 0, 1, x * 2, x + rnd.randint(2, 50)]
    if isinstance(x, float):
        return [x + 1.0, -x, 0.0, x * 2, x + 0.5]
    if isinstance(x, str):
        out = [x + "a", x[::-1], "", x[1:], x.upper(), x + " " + x]
        return out
    if isinstance(x, (list, tuple)):
        t = type(x)
        out = [t(reversed(x)), t(x[1:]), t(list(x) + list(x[-1:])), t([])]
        if x:
            i = rnd.randrange(len(x))
            for v in variants(x[i], rnd)[:3]:
                y = list(x); y[i] = v; out.append(t(y))
        try:
            out.append(t(sorted(x)))
        except Exception:
            pass
        return out
    if isinstance(x, dict):
        out = [{}]
        if x:
            k = next(iter(x)); y = dict(x); y.pop(k); out.append(y)
        return out
    return []

def differ(g, m):
    if g[0] != m[0]:
        return True
    if g[0] != "ok":
        return False
    try:
        assertion(m[1], g[1], 0)
        return False
    except AssertionError:
        return True
    except Exception:
        return True

rnd = random.Random(0)
tried = 0
found = None
pool = []
for inp in inputs:
    inp = list(inp)
    for j in range(len(inp)):
        for v in variants(inp[j], rnd):
            y = list(inp); y[j] = v; pool.append(y)
rnd.shuffle(pool)
for y in pool[:3000]:
    g = call(gold, y)
    if g[0] != "ok":
        continue
    tried += 1
    m = call(mut, y)
    if differ(g, m):
        found = {"input": repr(y)[:400], "gold": repr(g[1])[:300], "mutant": repr(m)[:300]}
        break
print(json.dumps({"tried": tried, "counterexample": found}))
"""


def rebuild_mutant(gold: str, subject: str) -> str:
    """Regenerate the mutant from its subject ``mutant:FILE:INDEX:OPERATOR:SUB`` (C004's key)."""
    _, _file, index, operator, sub = subject.split(":")
    for site in enumerate_sites(gold):
        if (site.index, site.operator, site.sub) == (int(index), operator, int(sub)):
            return make_mutant(gold, site).source
    raise ValueError(f"no mutation site {subject}")


def image_of(task: Path) -> str:
    m = re.search(r"^image: (\S+)", (task / "task.yaml").read_text(), re.M)
    return m.group(1) if m else "python:3.12-slim"


def verify(f: dict[str, Any], tasks: Path, runner: DockerRunner) -> dict[str, Any]:
    task = tasks / f["task_id"]
    prov = json.loads((task / "PROVENANCE.json").read_text())
    gold = (task / "gold" / "solution.py").read_text()
    base = {"finding": f["id"], "task": f["task_id"], "title": f["title"]}
    try:
        mutant = rebuild_mutant(gold, f["evidence"]["subject"])
    except ValueError as exc:
        return base | {"status": "error", "error": str(exc)}
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "driver.py").write_text(DRIVER)
        (d / "gold.py").write_text(gold)
        (d / "mutant.py").write_text(mutant)
        (d / "check.py").write_text((task / "tests" / "evalplus_check.py").read_text())
        spec = RunSpec(
            image=image_of(task),
            command=("python", "driver.py", prov["entry_point"]),
            layers=((d, Path(".")),),
            timeout_s=300.0,
        )
        r = runner.run(spec)
    if r.exit_code != 0:
        return base | {"status": "error", "error": r.stderr_tail[-400:]}
    out = json.loads(r.stdout_tail.strip().splitlines()[-1])
    status = "distinguished" if out["counterexample"] else "no-counterexample"
    return base | {"status": status, **out}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("tasks")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args(argv)
    out, tasks = Path(args.out), Path(args.tasks)
    findings = []
    for rep in sorted((out / "reports").glob("*.json")):
        findings += [f for f in json.loads(rep.read_text())["findings"] if f["check_id"] == "C004"]
    runner = DockerRunner()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(lambda f: verify(f, tasks, runner), findings))
    (out / "c004_counterexamples.json").write_text(json.dumps(rows, indent=1) + "\n")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"verify_c004: {len(rows)} survivors: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
