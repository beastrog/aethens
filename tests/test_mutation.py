"""Pure tests of the AST mutation generator used by C004 (B5)."""

from __future__ import annotations

import ast

from aethens.checks.mutation import Mutant, enumerate_sites, make_mutant, select_mutants

SRC = '''\
"""Module docstring."""


def f(a, b):
    """Docstring is never mutated."""
    if a < b and b != 0:
        return a + b * 2
    while a > 3:
        a -= 1
    return a


if __name__ == "__main__":
    print(f(1, 2))
'''


def test_sites_cover_each_operator_family() -> None:
    ops = {s.operator for s in enumerate_sites(SRC)}
    assert {
        "compare-boundary",
        "compare-negate",
        "binop-swap",
        "augassign-swap",
        "constant-plus-one",
        "negate-condition",
        "return-none",
        "boolop-swap",
    } <= ops


def test_main_guard_and_docstrings_are_skipped() -> None:
    for site in enumerate_sites(SRC):
        assert site.line < 13, site  # nothing inside the __main__ block


def test_each_mutant_parses_and_differs() -> None:
    sites = enumerate_sites(SRC)
    original = ast.unparse(ast.parse(SRC))
    seen = set()
    for site in sites:
        m = make_mutant(SRC, site)
        ast.parse(m.source)
        assert m.source != original
        seen.add(m.source)
    assert len(seen) == len(sites)


def test_specific_mutations() -> None:
    sites = enumerate_sites("def g(x):\n    return x < 3\n")
    sources = {s.operator: make_mutant("def g(x):\n    return x < 3\n", s).source for s in sites}
    assert "x <= 3" in sources["compare-boundary"]
    assert "x >= 3" in sources["compare-negate"]
    assert "x < 4" in sources["constant-plus-one"]
    assert "return None" in sources["return-none"]


def test_bool_constants_not_mutated() -> None:
    sites = enumerate_sites("def g():\n    return True\n")
    assert all(s.operator != "constant-plus-one" for s in sites)


def test_selection_is_seeded_and_capped() -> None:
    files = {"a.py": SRC}
    a = select_mutants(files, seed=1, salt="t", cap=4)
    b = select_mutants(files, seed=1, salt="t", cap=4)
    c = select_mutants(files, seed=2, salt="t", cap=4)
    assert [m.key for m in a] == [m.key for m in b]
    assert len(a) == 4
    assert [m.key for m in a] != [m.key for m in c]
    assert all(isinstance(m, Mutant) for m in a)
    everything = select_mutants(files, seed=1, salt="t", cap=10_000)
    assert len(everything) == len(enumerate_sites(SRC))


def test_syntax_error_file_is_skipped() -> None:
    assert select_mutants({"bad.py": "def (:\n"}, seed=0, salt="t", cap=5) == []
