"""External bench (D2): converter, metrics and the vendored sample. No network, no Docker."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
EXT = REPO / "bench" / "external"
sys.path.insert(0, str(EXT))

import convert  # noqa: E402
import render_external  # noqa: E402
import run_external  # noqa: E402

from aethens.adapters import load_task  # noqa: E402

HE_TEST = """

METADATA = {'author': 'jt'}


def check(candidate):
    assert candidate(3.5) == 0.5
    assert abs(candidate(1.33) - 0.33) < 1e-6
"""

HE_TEST_LOOP = """
def check(candidate):
    import math
    for x in range(3):
        assert candidate(x) == x
"""

PLUS_TEST = """
import numpy as np

def is_floats(x) -> bool:
    if isinstance(x, np.ndarray):
        return True
    return False


def assertion(out, exp, atol):
    np.testing.assert_allclose(out, exp, atol=atol)


def check(candidate):
    inputs = [[1.5], ['numpy']]
    results = [0.5, 'numpy']
    for i, (inp, exp) in enumerate(zip(inputs, results)):
        assertion(candidate(*inp), exp, 0)
"""


def test_task_name() -> None:
    assert convert.task_name("HumanEval/7") == "he-007"
    assert convert.task_name("HumanEval/163") == "he-163"


def test_base_tests_split_into_one_method_per_assert() -> None:
    src = convert.base_test_module(HE_TEST, "truncate_number", "HumanEval/2")
    tree = ast.parse(src)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    assert [f.name for f in cls.body if isinstance(f, ast.FunctionDef)] == ["test_000", "test_001"]
    assert "candidate = _solution.truncate_number" in src
    assert "MIT" in src.splitlines()[0]


def test_base_tests_with_other_statements_stay_one_check() -> None:
    src = convert.base_test_module(HE_TEST_LOOP, "f", "HumanEval/9")
    tree = ast.parse(src)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    assert [f.name for f in cls.body if isinstance(f, ast.FunctionDef)] == ["test_check"]
    assert any(isinstance(n, ast.FunctionDef) and n.name == "check" for n in tree.body)


def test_plus_tests_lose_numpy_but_keep_data() -> None:
    src = convert.plus_test_module(PLUS_TEST, "f", "HumanEval/1")
    names = {n.id for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Name)}
    assert not names & {"np", "numpy"}
    assert "'numpy'" in src  # data strings untouched
    assert "Apache-2.0" in src.splitlines()[0]


def test_stdlib_assertion_matches_allclose_rules() -> None:
    ns: dict[str, object] = {}
    exec(compile(convert.HELPERS, "helpers", "exec"), ns)  # noqa: S102 - our own helper code
    assertion = ns["assertion"]
    assert callable(assertion)
    assertion(0.5, 0.5, 0)
    assertion(0.1 + 0.2, 0.3, 0)  # float default atol 1e-6
    assertion([1.0, float("nan")], [1.0, float("nan")], 0)
    with pytest.raises(AssertionError):
        assertion(0.5, 0.6, 0)
    with pytest.raises(AssertionError):
        assertion([1.0], [1.0, 2.0], 0)
    with pytest.raises(AssertionError):
        assertion("a", "b", 0)


def _result(
    task: str, oracle: bool, findings: list[tuple[str, str]], survivors: list[str]
) -> dict[str, Any]:
    return {
        "task": task,
        "oracle_accepts_gold": oracle,
        "findings": [
            {"check_id": c, "severity": s, "id": f"{c}-{task}-{i}", "title": "t"}
            for i, (c, s) in enumerate(findings)
        ],
        "survivors": [{"mutant": f"m{i}", "line": 1, "oracle": v} for i, v in enumerate(survivors)],
    }


def test_compute_c004_precision_and_presumed_clean_counts() -> None:
    results = [
        _result("a", True, [("C004", "info"), ("C004", "info")], ["confirmed", "unconfirmed"]),
        _result("b", True, [("C002", "error"), ("C004", "info")], ["confirmed"]),
        _result("c", False, [("C001", "error")], ["no-oracle"]),
    ]
    m = run_external.compute(results, ["C001", "C002", "C004"])
    assert m["tasks_without_oracle"] == ["c"]
    c004 = m["per_check"]["C004"]
    assert (c004["survivors"], c004["survivors_judged_by_oracle"], c004["confirmed"]) == (4, 3, 2)
    assert c004["precision"] == round(2 / 3, 4)
    assert c004["recall"] is None
    assert m["per_check"]["C002"]["loud_findings"] == 1
    assert m["per_check"]["C001"]["precision"] is None


def test_compute_recall_against_exhaustive() -> None:
    a = _result("a", True, [], ["confirmed"])
    a["exhaustive"] = {"mutants": 5, "base_pass_oracle_fail": 2}
    b = _result("b", True, [], [])
    b["exhaustive"] = {"mutants": 5, "base_pass_oracle_fail": 1}
    c = _result("c", True, [], [])
    c["exhaustive"] = {"mutants": 5, "base_pass_oracle_fail": 0}
    m = run_external.compute([a, b, c], ["C004"])
    assert m["per_check"]["C004"]["recall"] == 0.5
    assert m["per_check"]["C004"]["recall_detail"]["weak_tasks"] == 2


def test_regressions() -> None:
    base = {"per_check": {"C004": {"loud_findings": 0, "precision": 0.8, "recall": None}}}
    ok = {"per_check": {"C004": {"loud_findings": 0, "precision": 0.8, "recall": 0.5}}}
    bad = {"per_check": {"C004": {"loud_findings": 1, "precision": 0.7, "recall": None}}}
    assert run_external.regressions(base, ok) == []
    assert len(run_external.regressions(base, bad)) == 2


def test_sample_is_vendored_with_attribution_and_loads() -> None:
    tasks = sorted((EXT / "sample" / "tasks").iterdir())
    assert len(tasks) >= 4
    for t in tasks:
        task = load_task(t)
        assert task.id == t.name
        for f in (t / "gold" / "solution.py", t / "tests" / "test_base.py"):
            assert "(MIT)" in f.read_text(encoding="utf-8").splitlines()[0]
        plus = EXT / "sample" / "oracle" / t.name / "tests" / "test_plus.py"
        assert "(Apache-2.0)" in plus.read_text(encoding="utf-8").splitlines()[0]


def test_licences_recorded() -> None:
    text = (REPO / "bench" / "LICENSES.md").read_text(encoding="utf-8")
    for needle in ("HumanEval", "MIT", "EvalPlus", "Apache-2.0", "ImpossibleBench"):
        assert needle in text


def test_generated_doc_is_in_sync_with_results() -> None:
    full = json.loads((EXT / "results.json").read_text(encoding="utf-8"))
    sample = json.loads((EXT / "sample-results.json").read_text(encoding="utf-8"))
    doc = (REPO / "docs" / "EXTERNAL_BENCH.md").read_text(encoding="utf-8")
    assert doc == render_external.render(full, sample)


def test_readme_external_block_is_in_sync() -> None:
    full = json.loads((EXT / "results.json").read_text(encoding="utf-8"))
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert render_external.readme_block(full) in readme
