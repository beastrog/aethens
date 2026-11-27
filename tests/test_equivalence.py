"""C004 equivalent-mutant probe (D-065): verdict logic and driver helpers in-process (no task code
runs here), the whole probe end to end in Docker."""

from __future__ import annotations

import random
import re
from pathlib import Path

import pytest

from aethens.adapters import load_task
from aethens.checks import C004MutationProbes, CheckContext
from aethens.checks.equivalence import MIN_VALID, judge, parse
from aethens.models import Budget, Severity
from aethens.runner import DockerRunner
from aethens.sandbox import equiv_driver as drv

BENCH = Path(__file__).resolve().parent.parent / "bench" / "tasks"


def test_parse_marker_line() -> None:
    out = 'noise\nAETHENS-EQUIV-RESULT {"v": 1, "valid": 3}\n'
    assert parse(out) == {"v": 1, "valid": 3}
    assert parse("no marker") is None
    assert parse("AETHENS-EQUIV-RESULT {broken") is None


def test_judge_outcomes() -> None:
    assert judge(None).status == "inconclusive"
    assert judge({"error": "ImportError: x"}).status == "inconclusive"
    diff = {"function": "f", "args": "(1,)", "gold": "1", "mutant": "2", "from_tests": True}
    d = judge({"functions": ["f"], "valid": 1, "difference": diff})
    assert d.status == "distinguished" and d.counterexample["mutant"] == "2"
    assert d.counterexample["from_tests"] == "True"
    assert judge({"functions": [], "valid": 0, "difference": None}).status == "inconclusive"
    few = judge({"functions": ["f"], "valid": MIN_VALID - 1, "difference": None})
    assert few.status == "inconclusive"
    eq = judge({"functions": ["f"], "valid": MIN_VALID, "difference": None})
    assert eq.status == "equivalent" and eq.valid_inputs == MIN_VALID


def test_driver_comparison_rules() -> None:
    assert drv.same(1, 1.0) and drv.same(0.1 + 0.2, 0.3)
    assert drv.same(float("nan"), float("nan"))
    assert not drv.same(None, False) and not drv.same(False, None)
    assert not drv.same([1, 2], (1, 2)) and drv.same({"a": [1]}, {"a": [1.0]})
    assert not drv.same([1, 2], [2, 1])


def test_driver_compares_objects_without_value_equality_by_repr() -> None:
    # re.Match has identity equality: two equal matches must still compare equal (D-087).
    assert drv.same(re.search("a", "abc"), re.search("a", "abc"))
    assert not drv.same(re.search("a", "abc"), re.search("b", "abc"))
    assert not drv.same(re.search("a", "abc"), None) and not drv.same(None, re.search("a", "a"))


def test_judge_unstable_gold_is_inconclusive() -> None:
    base = {"functions": ["f"], "difference": None}
    shaky = judge({**base, "valid": 50, "unstable": 6})
    assert shaky.status == "inconclusive" and "differ between two calls" in shaky.reason
    assert judge({**base, "valid": 100, "unstable": 1}).status == "equivalent"
    assert judge({**base, "valid": MIN_VALID}).status == "equivalent"  # older drivers


def test_driver_edits_keep_types_and_signs() -> None:
    rng = random.Random(0)  # noqa: S311 - test inputs
    for _ in range(500):
        assert drv.edit(5, rng) >= 0
        assert isinstance(drv.edit("abc", rng), str)
        assert isinstance(drv.edit([1, 2, 3], rng), list)
        assert isinstance(drv.edit((1, "a"), rng), tuple)
        assert isinstance(drv.edit(True, rng), bool)


def test_driver_pools_harvest_boundaries_from_source() -> None:
    pools = drv.Pools("def f(x):\n    return x > 10 and x != 'six'\n")
    assert {9, 10, 11} <= set(pools.ints)
    assert "six" in pools.words


def test_driver_derive_is_seeded_and_starts_with_seeds() -> None:
    seeds: list[object] = [((3, [1, 2]), {}), ((0, []), {})]
    a = drv.derive(seeds, random.Random(7), 50)  # noqa: S311
    b = drv.derive(seeds, random.Random(7), 50)  # noqa: S311
    assert a == b and a[:2] == seeds and len(a) == 50


def _ctx() -> CheckContext:
    return CheckContext(runner=DockerRunner(), seed=0, budget=Budget.STANDARD)


@pytest.mark.docker
def test_equivalent_survivors_of_a_clean_control_are_filtered() -> None:
    # ctrl-clamp's two survivors at seed 0 (B5) are equivalent mutants ('x < lo' -> 'x <= lo').
    task = load_task(BENCH / "ctrl-clamp")
    before = C004MutationProbes(filter_equivalent=False).run(task, _ctx())
    findings, coverage = C004MutationProbes().run_with_coverage(task, _ctx())
    assert len(before) >= 1
    assert len(findings) < len(before)
    assert len(coverage) == 1 and coverage[0].check_id == "C004"
    keys = coverage[0].stats["likely_equivalent_mutants"].split(",")
    assert len(keys) == len(before) - len(findings)
    assert "probably an equivalent mutant" in coverage[0].statement


@pytest.mark.docker
def test_real_survivors_keep_a_counterexample() -> None:
    task = load_task(BENCH / "weak-leap")
    findings = C004MutationProbes().run(task, _ctx())
    assert findings and all(f.severity is Severity.INFO for f in findings)
    shown = [f for f in findings if f.evidence.extra.get("equivalence_probe") == "distinguished"]
    assert shown, [f.evidence.extra for f in findings]
    f = shown[0]
    assert f.evidence.extra["counterexample_function"] == "is_leap"
    assert (
        f.evidence.extra["counterexample_gold_result"]
        != (f.evidence.extra["counterexample_mutant_result"])
    )
    assert "It is not equivalent" in f.detail


@pytest.mark.docker
def test_match_returning_gold_does_not_hide_a_return_none_mutant(tmp_path: Path) -> None:
    # Pattern seen in a real-benchmark audit: the gold returns re.Match objects, the weak test
    # never checks the result. Before D-087 the probe saw the gold "disagree with itself" on every
    # match, kept only the non-matching inputs and called "return None" equivalent.
    for d in ("gold", "starter", "tests"):
        (tmp_path / d).mkdir()
    (tmp_path / "statement.md").write_text("Return a match if the word starts with a vowel.\n")
    (tmp_path / "gold" / "vowel.py").write_text(
        "import re\n\n\ndef starts_with_vowel(word):\n    return re.search('^[aeiou]', word)\n"
    )
    (tmp_path / "starter" / "vowel.py").write_text(
        "def starts_with_vowel(word):\n    raise NotImplementedError\n"
    )
    (tmp_path / "tests" / "test_vowel.py").write_text(
        "import unittest\n\nfrom vowel import starts_with_vowel\n\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_runs(self):\n"
        "        for w in ['apple', 'banana', 'orange', 'kiwi', 'umbrella', 'grape']:\n"
        "            starts_with_vowel(w)  # weak: the result is never checked\n"
    )
    (tmp_path / "task.yaml").write_text(
        "schema: aethens-task/v1\nid: weak-vowel-match\nlanguage: python\n"
        "image: python:3.12-slim\nstatement: statement.md\nstarter: starter\ntests: tests\n"
        'verifier: ["python", "-m", "unittest", "discover", "-s", "tests"]\n'
        "timeout_s: 20\ngold: gold\n"
    )
    findings = C004MutationProbes().run(load_task(tmp_path), _ctx())
    none_mutants = [f for f in findings if "replaced by None" in f.title]
    assert none_mutants, [f.title for f in findings]
    assert none_mutants[0].evidence.extra["equivalence_probe"] == "distinguished"
