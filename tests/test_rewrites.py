"""Behaviour-preserving rewrites for C006 (D3).

These tests execute small programs written for this test file (never task or candidate code) to
check that every rewrite keeps behaviour identical, and that unsafe sites are skipped.
"""

from __future__ import annotations

import ast
from typing import Any

import pytest

from aethens.checks import rewrites

PROGRAMS = [
    """
def f(xs, k=2):
    # a comment
    total = 0
    out = []
    for x in xs:
        if x > k:
            out.append(x * 2)
    a = 1
    b = -2
    if not out:
        return None
    else:
        total = sum(out) + a + b
    return total
""",
    """
def f(xs, k=0):
    pairs = []
    for i, x in enumerate(xs):
        pairs.append((i, x - k))
    if pairs:
        first = pairs[0]
    elif k:
        first = None
    else:
        first = ()
    return pairs, first
""",
    """
def f(xs, k=1):
    acc = []
    for x in xs:
        acc.append(10 // (x - k))   # raises ZeroDivisionError for x == k
    return acc
""",
    """
def f(xs, k=3):
    seen = set()
    for x in xs:
        seen.add(x % k)
    n = len(seen)
    m = n * 2
    return sorted(seen), m
""",
]

INPUTS: list[tuple[Any, ...]] = [([],), ([1, 2, 3, 4],), ([5, 1, 9],), ([0, -1, 7],), ([1],)]


def _run(src: str, args: tuple[Any, ...]) -> tuple[str, Any]:
    ns: dict[str, Any] = {}
    exec(compile(src, "<test-program>", "exec"), ns)  # noqa: S102 - this file's own programs
    try:
        return "ok", ns["f"](*args)
    except Exception as exc:
        return "raise", type(exc).__name__


@pytest.mark.parametrize("name", list(rewrites.REWRITES))
@pytest.mark.parametrize("prog", PROGRAMS)
def test_rewrite_preserves_behaviour(name: str, prog: str) -> None:
    rw = rewrites.apply(name, prog)
    if rw is None:
        return
    for args in INPUTS:
        assert _run(prog, args) == _run(rw.source, args), (name, args, rw.source)


def test_each_rewrite_applies_somewhere() -> None:
    for name in rewrites.REWRITES:
        assert any(rewrites.apply(name, p) is not None for p in PROGRAMS), name


def test_reformat_drops_comments_and_moves_lines() -> None:
    rw = rewrites.apply("reformat", PROGRAMS[0])
    assert rw is not None and "# a comment" not in rw.source
    assert ast.dump(ast.parse(rw.source)) == ast.dump(ast.parse(PROGRAMS[0]))


def test_rename_never_touches_params_globals_or_attributes() -> None:
    src = """
G = 1
def f(a, *args, b=2, **kw):
    t = a + G
    t2 = kw.get("x")
    return t, t2, args, b
"""
    rw = rewrites.apply("rename-locals", src)
    assert rw is not None
    tree = ast.parse(rw.source)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef))
    assert [a.arg for a in fn.args.args] == ["a"]
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    assert {"a", "G", "kw", "args", "b"} <= names and "t" not in names and "t2" not in names
    assert ".get(" in rw.source


@pytest.mark.parametrize(
    "src",
    [
        "def f():\n    x = 1\n    return locals()\n",
        "def f():\n    x = 1\n    return eval('x')\n",
        "def f():\n    global y\n    y = 1\n    return y\n",
        "import inspect\ndef f():\n    x = 1\n    return inspect.currentframe()\n",
    ],
)
def test_rename_skips_introspective_functions(src: str) -> None:
    assert rewrites.apply("rename-locals", src) is None


def test_rename_skips_names_seen_by_nested_scopes() -> None:
    src = (
        "def f(xs):\n    k = 2\n    n = len(xs)\n    h = lambda v: v * k\n"
        "    return [h(x) for x in xs], n\n"
    )
    rw = rewrites.apply("rename-locals", src)
    assert rw is not None  # n can be renamed ...
    assert "n = len" not in rw.source
    # ... k (read by the lambda) and h (read by the comprehension) are seen by nested scopes
    assert "k = 2" in rw.source and "* k" in rw.source and "h = lambda" in rw.source
    only_nested = (
        "def f(xs):\n    k = 2\n    g = lambda v: v * k\n    return [g(x) + k for x in xs]\n"
    )
    assert rewrites.apply("rename-locals", only_nested) is None


def test_no_rewrite_when_output_is_identical() -> None:
    assert rewrites.apply("reformat", "def add(a: int, b: int) -> int:\n    return a + b\n") is None


def test_rename_skips_names_from_defaults_scope() -> None:
    src = "y = 5\ndef f(x=y):\n    y = x + 1\n    return y\n"
    rw = rewrites.apply("rename-locals", src)
    assert rw is not None and "def f(x=y)" in rw.source


@pytest.mark.parametrize(
    "src",
    [
        # loop variable used after the loop
        "def f(xs):\n    out = []\n    for x in xs:\n        out.append(x)\n    return out, x\n",
        # element expression reads the list being built
        "def f(xs):\n    out = []\n"
        "    for x in xs:\n        out.append(len(out) + x)\n    return out\n",
        # a try block could observe the partial list
        "def f(xs):\n    out = []\n    try:\n        pass\n    finally:\n        pass\n"
        "    for x in xs:\n        out.append(x)\n    return out\n",
        # attribute store target
        "def f(xs, o):\n    out = []\n"
        "    for o.x in xs:\n        out.append(o.x)\n    return out\n",
        # loop with else
        "def f(xs):\n    out = []\n"
        "    for x in xs:\n        out.append(x)\n    else:\n        pass\n"
        "    return out\n",
        # walrus in the element
        "def f(xs):\n    out = []\n"
        "    for x in xs:\n        out.append((y := x))\n    return out\n",
        # module level, not a function
        "out = []\nfor x in range(3):\n    out.append(x)\n",
    ],
)
def test_loop_to_comprehension_skips_unsafe_sites(src: str) -> None:
    assert rewrites.apply("loop-to-comprehension", src) is None


def test_swap_skips_non_constants_and_module_level() -> None:
    assert rewrites.apply("swap-constant-assignments", "a = 1\nb = 2\n") is None
    src = "def f(g):\n    a = g()\n    b = 2\n    return a, b\n"
    assert rewrites.apply("swap-constant-assignments", src) is None
    src = "def f():\n    a = 1\n    a = 2\n    return a\n"
    assert rewrites.apply("swap-constant-assignments", src) is None


def test_invert_if_skips_main_guard_and_plain_if() -> None:
    assert (
        rewrites.apply("invert-if", "if __name__ == '__main__':\n    pass\nelse:\n    pass\n")
        is None
    )
    assert (
        rewrites.apply("invert-if", "def f(x):\n    if x:\n        return 1\n    return 2\n")
        is None
    )
    rw = rewrites.apply(
        "invert-if", "def f(x):\n    if not x:\n        return 1\n    else:\n        return 2\n"
    )
    assert rw is not None and "if x:" in rw.source


def test_rewritten_source_always_compiles() -> None:
    for prog in PROGRAMS:
        for name in rewrites.REWRITES:
            rw = rewrites.apply(name, prog)
            if rw is not None:
                compile(rw.source, "<rw>", "exec")
