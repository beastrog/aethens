"""Convert HumanEval (base tests) and HumanEval+ (oracle tests) into aethens-task/v1 tasks.

Usage: python bench/external/convert.py [--out DIR] [--only he-000,he-002,...]

For each of the 164 problems this writes:
  DIR/tasks/he-NNN/   an aethens-task/v1 task: statement = the HumanEval prompt, starter = the
                      prompt with `raise NotImplementedError` as the body, gold = prompt + ORIGINAL
                      HumanEval canonical solution, tests = HumanEval's ORIGINAL base `check`
                      (one unittest method per assert when the check body is only asserts)
  DIR/oracle/he-NNN/tests/test_plus.py
                      EvalPlus's HumanEval+ `check` (many more inputs, expected outputs from
                      EvalPlus's reference), used only as an outside oracle, never as the verifier

Only change made to EvalPlus's tests: their `is_floats`/`assertion` helpers use numpy, which the
sandbox image does not have (and runs have no network), so they are replaced with a stdlib
re-implementation of the same comparison (exact match, else |out - exp| <= atol + 1e-7 * |exp|
element-wise, NaN equal to NaN, atol defaulting to 1e-6 for float outputs). This mirrors
numpy.testing.assert_allclose's defaults for scalars and flat sequences; it was not verified
against numpy for every corner case (stated in bench/external/README.md).
"""

from __future__ import annotations

import argparse
import ast
import gzip
import json
import shutil
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

TASK_YAML = """schema: aethens-task/v1
id: {id}
language: python
image: python:3.12-slim
statement: statement.md
starter: starter
tests: tests
verifier: ["python", "-m", "unittest", "discover", "-s", "tests"]
timeout_s: 20
gold: gold
"""

HELPERS = """
import math


def is_floats(x) -> bool:
    # stdlib replacement for EvalPlus's numpy-based helper (see bench/external/convert.py)
    if isinstance(x, float):
        return True
    if isinstance(x, (list, tuple)):
        return all(isinstance(i, float) for i in x)
    return False


def _allclose(out, exp, atol):
    if isinstance(exp, (list, tuple)):
        assert isinstance(out, (list, tuple)) and len(out) == len(exp)
        for o, e in zip(out, exp):
            _allclose(o, e, atol)
        return
    o, e = float(out), float(exp)
    if math.isnan(o) or math.isnan(e):
        assert math.isnan(o) and math.isnan(e)
        return
    if math.isinf(o) or math.isinf(e):
        assert o == e
        return
    assert abs(o - e) <= atol + 1e-07 * abs(e)


def assertion(out, exp, atol):
    exact_match = out == exp

    if atol == 0 and is_floats(exp):
        atol = 1e-6
    if not exact_match and atol != 0:
        _allclose(out, exp, atol)
    else:
        assert exact_match
"""

# HumanEval's harness executes prompt + solution + test in ONE namespace, so tests may use helpers
# defined in the prompt (e.g. `poly` in HumanEval/32). Reproduce that namespace explicitly.
NAMESPACE = """import solution as _solution

globals().update({{k: v for k, v in vars(_solution).items() if not k.startswith("__")}})
candidate = _solution.{entry}
"""

ATTRIBUTION = (
    "# Converted by bench/external/convert.py from {what} ({lic}). {src}\n"
    "# Task {task_id}. Do not edit by hand; re-run the converter.\n"
)
HE_SRC = "HumanEval: github.com/openai/human-eval, Copyright (c) OpenAI."
HP_SRC = "HumanEval+: EvalPlus, huggingface.co/datasets/evalplus/humanevalplus."


def task_name(task_id: str) -> str:
    return f"he-{int(task_id.split('/')[1]):03d}"


def strip_numpy(test_src: str) -> str:
    """Remove `import numpy` and EvalPlus's numpy helpers; prepend the stdlib helpers."""
    tree = ast.parse(test_src)
    body = []
    replaced = False
    for node in tree.body:
        if isinstance(node, ast.Import) and any(a.name == "numpy" for a in node.names):
            continue
        if isinstance(node, ast.FunctionDef) and node.name in ("is_floats", "assertion"):
            replaced = True
            continue
        body.append(node)
    tree.body = body
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    if names & {"np", "numpy"}:
        raise SystemExit("convert: numpy still referenced after stripping helpers")
    src = ast.unparse(tree)
    return (HELPERS if replaced else "") + "\n\n" + src + "\n"


def base_test_module(test_src: str, entry: str, task_id: str) -> str:
    """HumanEval's base check(), as unittest methods (one per assert when possible)."""
    tree = ast.parse(test_src)
    check = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "check")
    others = [n for n in tree.body if n is not check]
    stmts = [
        s for s in check.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
    ]
    head = ATTRIBUTION.format(what="HumanEval base tests", lic="MIT", src=HE_SRC, task_id=task_id)
    lines = [head, "import unittest", "", NAMESPACE.format(entry=entry), ""]
    if others:
        lines += [ast.unparse(ast.Module(body=others, type_ignores=[])), ""]
    lines += ["", "class TestBase(unittest.TestCase):"]
    if stmts and all(isinstance(s, ast.Assert) for s in stmts):
        for i, s in enumerate(stmts):
            lines.append(f"    def test_{i:03d}(self):")
            for ln in ast.unparse(s).splitlines():
                lines.append(f"        {ln}")
            lines.append("")
    else:
        lines.append("    def test_check(self):")
        lines.append("        check(candidate)")
        lines.append("")
        lines.insert(lines.index("class TestBase(unittest.TestCase):") - 1, ast.unparse(check))
        lines.insert(lines.index("class TestBase(unittest.TestCase):") - 1, "")
    return "\n".join(lines) + "\n"


def plus_test_module(plus_src: str, entry: str, task_id: str) -> str:
    head = ATTRIBUTION.format(
        what="HumanEval+ tests", lic="Apache-2.0", src=HP_SRC, task_id=task_id
    )
    return (
        head
        + "import unittest\n\n"
        + NAMESPACE.format(entry=entry)
        + strip_numpy(plus_src)
        + "\n\nclass TestPlus(unittest.TestCase):\n"
        + "    def test_plus(self):\n"
        + "        check(candidate)\n"
    )


def write_task(he: dict[str, Any], plus: dict[str, Any], out: Path) -> str:
    name = task_name(he["task_id"])
    if plus["task_id"] != he["task_id"] or plus["entry_point"] != he["entry_point"]:
        raise SystemExit(f"convert: {he['task_id']}: HumanEval and HumanEval+ rows do not match")
    entry = he["entry_point"]
    prompt = he["prompt"]
    tdir = out / "tasks" / name
    for sub in ("gold", "starter", "tests"):
        (tdir / sub).mkdir(parents=True, exist_ok=True)
    (tdir / "task.yaml").write_text(TASK_YAML.format(id=name), encoding="utf-8")
    statement = (
        f"Complete `{entry}` in `solution.py`. Source: {he['task_id']} from OpenAI HumanEval "
        f"(MIT).\n\n```python\n{prompt}```\n"
    )
    (tdir / "statement.md").write_text(statement, encoding="utf-8")
    head = ATTRIBUTION.format(what="HumanEval", lic="MIT", src=HE_SRC, task_id=he["task_id"])
    (tdir / "starter" / "solution.py").write_text(
        head + prompt + "    raise NotImplementedError\n", encoding="utf-8"
    )
    (tdir / "gold" / "solution.py").write_text(
        head + prompt + he["canonical_solution"], encoding="utf-8"
    )
    (tdir / "tests" / "test_base.py").write_text(
        base_test_module(he["test"], entry, he["task_id"]), encoding="utf-8"
    )
    odir = out / "oracle" / name / "tests"
    odir.mkdir(parents=True, exist_ok=True)
    (odir / "test_plus.py").write_text(
        plus_test_module(plus["test"], entry, he["task_id"]), encoding="utf-8"
    )
    return name


def load_rows() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    he_path, hp_path = DATA / "HumanEval.jsonl.gz", DATA / "HumanEvalPlus.jsonl"
    if not he_path.exists() or not hp_path.exists():
        raise SystemExit("convert: data missing; run python bench/external/fetch.py first")
    with gzip.open(he_path, "rt", encoding="utf-8") as fh:
        he = [json.loads(line) for line in fh]
    with hp_path.open(encoding="utf-8") as fh:
        plus = {r["task_id"]: r for r in (json.loads(line) for line in fh)}
    return he, plus


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(HERE / "full"))
    ap.add_argument("--only", default="", help="comma-separated task names, e.g. he-000,he-002")
    args = ap.parse_args(argv)
    out = Path(args.out)
    only = {s for s in args.only.split(",") if s}
    he, plus = load_rows()
    if not only and out.exists():
        shutil.rmtree(out)
    names = []
    for row in he:
        if only and task_name(row["task_id"]) not in only:
            continue
        names.append(write_task(row, plus[row["task_id"]], out))
    print(f"convert: wrote {len(names)} tasks to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
