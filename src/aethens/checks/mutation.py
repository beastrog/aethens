"""Deterministic AST mutations for C004, using only the standard library ``ast`` module.

A *site* is one place where one operator can be applied. Sites are enumerated in ``ast.walk``
order, which is deterministic for a given source, so a site can be re-applied to a fresh parse.
Code inside ``if __name__ == "__main__":`` blocks is never mutated.
"""

from __future__ import annotations

import ast
import random
from dataclasses import dataclass

_BOUNDARY: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
}
_NEGATE: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Lt: ast.GtE,
    ast.LtE: ast.Gt,
    ast.Gt: ast.LtE,
    ast.GtE: ast.Lt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
}
_BINOP: dict[type[ast.operator], type[ast.operator]] = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.Div,
    ast.Div: ast.Mult,
    ast.FloorDiv: ast.Mult,
    ast.Mod: ast.FloorDiv,
    ast.Pow: ast.Mult,
}
_SYMBOL: dict[type[ast.AST], str] = {
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.In: "in",
    ast.NotIn: "not in",
    ast.Is: "is",
    ast.IsNot: "is not",
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.FloorDiv: "//",
    ast.Mod: "%",
    ast.Pow: "**",
    ast.And: "and",
    ast.Or: "or",
}


@dataclass(frozen=True)
class Site:
    index: int  # position in ast.walk order
    operator: str
    sub: int  # comparator position for Compare nodes, else 0
    line: int
    description: str


@dataclass(frozen=True)
class Mutant:
    file: str
    site: Site
    source: str

    @property
    def key(self) -> str:
        return f"{self.file}:{self.site.index}:{self.site.operator}:{self.site.sub}"


def _is_main_guard(node: ast.AST) -> bool:
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    t = node.test
    return (
        isinstance(t.left, ast.Name)
        and t.left.id == "__name__"
        and len(t.comparators) == 1
        and isinstance(t.comparators[0], ast.Constant)
        and t.comparators[0].value == "__main__"
    )


def _skipped(tree: ast.AST) -> set[int]:
    skip: set[int] = set()
    for node in ast.walk(tree):
        if _is_main_guard(node):
            skip.update(id(n) for n in ast.walk(node))
    return skip


def _sites_for(index: int, node: ast.AST) -> list[Site]:
    line = getattr(node, "lineno", 0)
    out: list[Site] = []
    if isinstance(node, ast.Compare):
        for j, op in enumerate(node.ops):
            sym = _SYMBOL[type(op)]
            if type(op) in _BOUNDARY:
                new = _SYMBOL[_BOUNDARY[type(op)]]
                out.append(Site(index, "compare-boundary", j, line, f"'{sym}' -> '{new}'"))
            if type(op) in _NEGATE:
                new = _SYMBOL[_NEGATE[type(op)]]
                out.append(Site(index, "compare-negate", j, line, f"'{sym}' -> '{new}'"))
    elif isinstance(node, ast.BinOp) and type(node.op) in _BINOP:
        a, b = _SYMBOL[type(node.op)], _SYMBOL[_BINOP[type(node.op)]]
        out.append(Site(index, "binop-swap", 0, line, f"'{a}' -> '{b}'"))
    elif isinstance(node, ast.AugAssign) and type(node.op) in _BINOP:
        a, b = _SYMBOL[type(node.op)], _SYMBOL[_BINOP[type(node.op)]]
        out.append(Site(index, "augassign-swap", 0, line, f"'{a}=' -> '{b}='"))
    elif (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
    ):
        v = node.value
        out.append(Site(index, "constant-plus-one", 0, line, f"constant {v} -> {v + 1}"))
    elif isinstance(node, ast.If | ast.While | ast.IfExp):
        out.append(Site(index, "negate-condition", 0, line, "condition negated"))
    elif isinstance(node, ast.Return) and node.value is not None:
        if not (isinstance(node.value, ast.Constant) and node.value.value is None):
            out.append(Site(index, "return-none", 0, line, "return value replaced by None"))
    elif isinstance(node, ast.BoolOp):
        a = _SYMBOL[type(node.op)]
        b = "or" if a == "and" else "and"
        out.append(Site(index, "boolop-swap", 0, line, f"'{a}' -> '{b}'"))
    return out


def enumerate_sites(source: str) -> list[Site]:
    """All mutation sites in ``source``. Raises SyntaxError for unparsable code."""
    tree = ast.parse(source)
    skip = _skipped(tree)
    sites: list[Site] = []
    for i, node in enumerate(ast.walk(tree)):
        if id(node) not in skip:
            sites.extend(_sites_for(i, node))
    return sites


def make_mutant(source: str, site: Site, file: str = "") -> Mutant:
    tree = ast.parse(source)
    node = list(ast.walk(tree))[site.index]
    if site.operator == "compare-boundary":
        assert isinstance(node, ast.Compare)
        node.ops[site.sub] = _BOUNDARY[type(node.ops[site.sub])]()
    elif site.operator == "compare-negate":
        assert isinstance(node, ast.Compare)
        node.ops[site.sub] = _NEGATE[type(node.ops[site.sub])]()
    elif site.operator in ("binop-swap", "augassign-swap"):
        assert isinstance(node, ast.BinOp | ast.AugAssign)
        node.op = _BINOP[type(node.op)]()
    elif site.operator == "constant-plus-one":
        assert isinstance(node, ast.Constant) and isinstance(node.value, int)
        node.value = node.value + 1
    elif site.operator == "negate-condition":
        assert isinstance(node, ast.If | ast.While | ast.IfExp)
        node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
    elif site.operator == "return-none":
        assert isinstance(node, ast.Return)
        node.value = ast.Constant(value=None)
    elif site.operator == "boolop-swap":
        assert isinstance(node, ast.BoolOp)
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    else:  # pragma: no cover - sites only carry known operators
        raise ValueError(site.operator)
    ast.fix_missing_locations(tree)
    return Mutant(file=file, site=site, source=ast.unparse(tree))


def select_mutants(files: dict[str, str], *, seed: int, salt: str, cap: int) -> list[Mutant]:
    """Seeded, capped selection of mutants over several files. Unparsable files are skipped."""
    pool: list[tuple[str, Site]] = []
    for name in sorted(files):
        try:
            pool.extend((name, s) for s in enumerate_sites(files[name]))
        except SyntaxError:
            continue
    rng = random.Random(f"{seed}|{salt}|C004")  # noqa: S311 - selection, not security
    rng.shuffle(pool)
    chosen: list[Mutant] = []
    seen: set[str] = set()
    for name, site in pool:
        if len(chosen) >= cap:
            break
        m = make_mutant(files[name], site, name)
        if m.source in seen:
            continue
        seen.add(m.source)
        chosen.append(m)
    return chosen
