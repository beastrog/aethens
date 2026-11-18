"""Behaviour-preserving AST rewrites of a gold solution, for C006 (over-specified tests).

Every rewrite here changes only things a test can observe through introspection: source text,
comments and formatting, line numbers, local variable names (``co_varnames``) and the shape of the
code. For every input, the rewritten program computes the same values, raises the same exception
types, and has the same side effects in the same order. Each rewrite states the conditions under
which that holds and SKIPS any site where it cannot prove them. When in doubt, it skips.

Rewrites (``REWRITES``):
- ``reformat``: ``ast.unparse(ast.parse(src))``: drops comments, normalises formatting, moves lines.
- ``rename-locals``: renames function-local variables (never parameters, globals, nonlocals,
  attributes or names used by nested scopes) to fresh names.
- ``swap-constant-assignments``: swaps two adjacent ``name = <constant>`` statements with distinct
  names inside a function body.
- ``loop-to-comprehension``: ``acc = []; for t in it: acc.append(e)`` (optionally guarded by one
  ``if``) becomes ``acc = [e for t in it (if c)]`` under strict conditions (see the function).
- ``invert-if``: ``if c: A else: B`` becomes ``if not c: B else: A`` and ``if not c: A else: B``
  becomes ``if c: B else: A``. ``if`` evaluates ``bool(c)`` exactly once in both forms.
"""

from __future__ import annotations

import ast
import builtins
import copy
from collections.abc import Callable, Iterator
from dataclasses import dataclass

# Names whose presence in a function means it may inspect its own frame or locals: any rewrite
# that touches that function's locals is skipped.
_INTROSPECTIVE = frozenset(
    {
        "locals",
        "vars",
        "eval",
        "exec",
        "dir",
        "globals",
        "inspect",
        "_getframe",
        "currentframe",
        "sys",
        "super",
        "__class__",
        "breakpoint",
        "pdb",
        "traceback",
        "f_locals",
    }
)
_NESTED = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.ClassDef,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


@dataclass(frozen=True)
class Rewrite:
    name: str
    description: str
    source: str
    sites: int


def _functions(tree: ast.AST) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _own_nodes(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[ast.AST]:
    """Nodes of ``fn``'s body scope: does not descend into nested scopes (but yields them).

    Starts from the body only: defaults, annotations and decorators are evaluated in the
    enclosing scope, so they are not part of the function's local scope.
    """
    stack: list[ast.AST] = list(fn.body)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, _NESTED):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _all_identifiers(node: ast.AST) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.alias):
            out.add(n.asname or n.name.split(".")[0])
    return out


def _introspective(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if _all_identifiers(fn) & _INTROSPECTIVE:
        return True
    if getattr(fn, "type_params", None):
        return True
    return any(isinstance(n, (ast.Match, ast.Global, ast.Nonlocal)) for n in ast.walk(fn))


# --- reformat --------------------------------------------------------------------------------


def reformat(tree: ast.Module) -> int:
    """Identity on the AST; the change is in the text ``ast.unparse`` produces."""
    return 1


# --- rename-locals ---------------------------------------------------------------------------


def _params(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    a = fn.args
    names = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
    if a.vararg:
        names.append(a.vararg.arg)
    if a.kwarg:
        names.append(a.kwarg.arg)
    return set(names)


def rename_locals(tree: ast.Module) -> int:
    """Rename function-local variables to fresh names.

    A name is renamed only when ALL of these hold, which makes the rename invisible to anything but
    introspection: it is bound in the function's own scope by plain assignment, augmented
    assignment, a for target, a with/except ``as`` or ``del`` (Python then treats every use in that
    scope as local); it is not a parameter; it is not declared global/nonlocal (functions with such
    declarations are skipped); it does not occur anywhere inside a nested scope (def, lambda,
    class, comprehension) of the function, so no closure or comprehension can see it; it does not
    start with ``__`` (name mangling); and the function does not use frame or locals introspection
    (``locals``, ``vars``, ``eval``, ``exec``, ``inspect``, ``sys``, zero-argument ``super``...).
    The only observable differences are ``co_varnames`` and the variable name in an
    UnboundLocalError message.
    """
    taken = _all_identifiers(tree) | set(dir(builtins))
    counter = 0
    sites = 0
    for fn in list(_functions(tree)):
        if _introspective(fn):
            continue
        own = list(_own_nodes(fn))
        nested_names: set[str] = set()
        for n in own:
            if isinstance(n, _NESTED):
                nested_names |= _all_identifiers(n)
        bound: set[str] = set()
        for n in own:
            if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                bound.add(n.id)
            elif isinstance(n, ast.ExceptHandler) and n.name:
                nested_names.add(n.name)  # except-as names are deleted implicitly: leave them
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                nested_names |= {a.asname or a.name.split(".")[0] for a in n.names}
        candidates = sorted(b for b in bound - _params(fn) - nested_names if not b.startswith("__"))
        if not candidates:
            continue
        mapping: dict[str, str] = {}
        for b in candidates:
            while True:
                counter += 1
                new = f"v{counter}_"
                if new not in taken:
                    break
            taken.add(new)
            mapping[b] = new
        for n in own:
            if isinstance(n, ast.Name) and n.id in mapping:
                n.id = mapping[n.id]
        sites += len(mapping)
    return sites


# --- swap-constant-assignments ---------------------------------------------------------------


def _is_constant(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return (
            isinstance(node.operand, ast.Constant)
            and isinstance(node.operand.value, (int, float, complex))
            and not isinstance(node.operand.value, bool)
        )
    if isinstance(node, ast.Tuple):
        return all(_is_constant(e) for e in node.elts)
    return False


def _simple_const_assign(stmt: ast.stmt) -> str | None:
    if (
        isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Name)
        and _is_constant(stmt.value)
    ):
        return stmt.targets[0].id
    return None


def _blocks(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[list[ast.stmt]]:
    """Statement lists in ``fn``'s own scope (function body and nested compound statements)."""
    yield fn.body
    for n in _own_nodes(fn):
        if isinstance(n, _NESTED):
            continue
        for field in ("body", "orelse", "finalbody"):
            block = getattr(n, field, None)
            if isinstance(block, list) and block and isinstance(block[0], ast.stmt):
                yield block
        if isinstance(n, ast.Try):
            for h in n.handlers:
                yield h.body


def swap_constant_assignments(tree: ast.Module) -> int:
    """Swap adjacent ``a = <constant>`` / ``b = <constant>`` with a != b, in function bodies only.

    Evaluating a literal constant (numbers, strings, bytes, None, booleans, tuples of these, a
    signed number) cannot fail and has no side effects, and binding a function local is not
    observable by other code between the two statements (no code runs between them). Functions
    with frame or locals introspection, or global/nonlocal declarations, are skipped (a global
    binding order would be visible in the module ``__dict__`` order). Module and class bodies are
    never touched.
    """
    sites = 0
    for fn in list(_functions(tree)):
        if _introspective(fn):
            continue
        for block in list(_blocks(fn)):
            i = 0
            while i + 1 < len(block):
                a, b = _simple_const_assign(block[i]), _simple_const_assign(block[i + 1])
                if a is not None and b is not None and a != b:
                    block[i], block[i + 1] = block[i + 1], block[i]
                    sites += 1
                    i += 2
                else:
                    i += 1
    return sites


# --- loop-to-comprehension -------------------------------------------------------------------

_FORBIDDEN_IN_EXPR = (ast.Yield, ast.YieldFrom, ast.Await, ast.NamedExpr, *_NESTED)


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _target_names(target: ast.AST) -> set[str] | None:
    """Names bound by a for target made only of names and tuples/lists of names, else None."""
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        out: set[str] = set()
        for e in target.elts:
            sub = _target_names(e)
            if sub is None:
                return None
            out |= sub
        return out
    return None


def _append_of(stmt: ast.stmt, acc: str) -> ast.expr | None:
    if (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Call)
        and isinstance(stmt.value.func, ast.Attribute)
        and stmt.value.func.attr == "append"
        and isinstance(stmt.value.func.value, ast.Name)
        and stmt.value.func.value.id == acc
        and len(stmt.value.args) == 1
        and not stmt.value.keywords
        and not isinstance(stmt.value.args[0], ast.Starred)
    ):
        return stmt.value.args[0]
    return None


def loop_to_comprehension(tree: ast.Module) -> int:
    """``acc = []`` + ``for t in it: [if c:] acc.append(e)`` -> ``acc = [e for t in it [if c]]``.

    Conditions (all required; otherwise the site is skipped):
    - inside a function that has no try, with or match statements, no global/nonlocal
      declarations, no nested scopes at all and no frame/locals introspection; so if ``e``, ``c`` or
      the iteration raises, nothing in the function can observe the partly built list or the loop
      variable, and no closure can see ``acc``;
    - ``acc`` is a plain name bound to an empty list literal by the statement right before the loop;
    - the loop has no ``else``, and its body is exactly one ``acc.append(e)`` call, or one ``if c:``
      (no else) whose body is exactly that call;
    - the loop target is names or tuples of names only (no attribute or subscript stores), and none
      of those names is used anywhere else in the function (the loop leaks them; the
      comprehension does not);
    - ``it``, ``e`` and ``c`` do not mention ``acc`` and contain no yield, await, walrus, lambda or
      comprehension.
    ``it`` is evaluated once, before any element, in both forms; elements are produced and appended
    in the same order; ``list.append`` and the comprehension's append cannot be overridden.
    """
    sites = 0
    for fn in list(_functions(tree)):
        if _introspective(fn):
            continue
        if any(isinstance(n, (ast.Try, ast.With, ast.AsyncWith, ast.Match)) for n in ast.walk(fn)):
            continue
        if any(isinstance(n, _NESTED) for n in _own_nodes(fn)):
            continue
        for block in list(_blocks(fn)):
            i = 0
            while i + 1 < len(block):
                init, loop = block[i], block[i + 1]
                new = _comprehension_for(fn, init, loop)
                if new is None:
                    i += 1
                    continue
                block[i : i + 2] = [new]
                sites += 1
                i += 1
    return sites


def _comprehension_for(
    fn: ast.FunctionDef | ast.AsyncFunctionDef, init: ast.stmt, loop: ast.stmt
) -> ast.stmt | None:
    if not (
        isinstance(init, ast.Assign)
        and len(init.targets) == 1
        and isinstance(init.targets[0], ast.Name)
        and isinstance(init.value, ast.List)
        and not init.value.elts
        and isinstance(loop, ast.For)
        and not loop.orelse
        and len(loop.body) == 1
    ):
        return None
    acc = init.targets[0].id
    body = loop.body[0]
    cond: ast.expr | None = None
    if isinstance(body, ast.If) and not body.orelse and len(body.body) == 1:
        cond = body.test
        body = body.body[0]
    elem = _append_of(body, acc)
    if elem is None:
        return None
    targets = _target_names(loop.target)
    if targets is None or acc in targets:
        return None
    parts: list[ast.AST] = [loop.iter, elem, *([cond] if cond is not None else [])]
    for p in parts:
        if acc in _names(p) or any(isinstance(n, _FORBIDDEN_IN_EXPR) for n in ast.walk(p)):
            return None
    # the loop variables must not be used anywhere in the function outside this loop
    outside = 0
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and n.id in targets:
            outside += 1
    inside = sum(1 for n in ast.walk(loop) if isinstance(n, ast.Name) and n.id in targets)
    if outside != inside:
        return None
    comp = ast.ListComp(
        elt=elem,
        generators=[
            ast.comprehension(
                target=loop.target, iter=loop.iter, ifs=[cond] if cond else [], is_async=0
            )
        ],
    )
    return ast.Assign(targets=[ast.Name(id=acc, ctx=ast.Store())], value=comp, lineno=init.lineno)


# --- invert-if -------------------------------------------------------------------------------


def invert_if(tree: ast.Module) -> int:
    """``if c: A else: B`` <-> ``if not c: B else: A``.

    ``if c`` and ``if not c`` both evaluate ``c`` once and call ``bool`` on it once (``not`` on the
    result of ``bool`` cannot fail), so exactly one branch runs, the same one, in both forms. Only
    statement ``if`` nodes with a non-empty ``else`` are touched (``elif`` chains included, the
    nested ``if`` simply moves). ``if __name__ == "__main__"`` blocks are left alone.
    """
    sites = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not node.orelse:
            continue
        if ast.unparse(node.test).replace("'", '"') == '__name__ == "__main__"':
            continue
        if isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not):
            node.test = node.test.operand
        else:
            node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
        node.body, node.orelse = node.orelse, node.body
        sites += 1
    return sites


REWRITES: dict[str, tuple[Callable[[ast.Module], int], str]] = {
    "reformat": (reformat, "source reformatted: comments dropped, formatting and lines changed"),
    "rename-locals": (rename_locals, "function-local variables renamed"),
    "swap-constant-assignments": (
        swap_constant_assignments,
        "adjacent independent constant assignments swapped",
    ),
    "loop-to-comprehension": (loop_to_comprehension, "append loops turned into comprehensions"),
    "invert-if": (invert_if, "if/else branches swapped with the condition negated"),
}


def apply(name: str, source: str) -> Rewrite | None:
    """Apply one rewrite to a whole file. None when it has no site in this file."""
    fn, desc = REWRITES[name]
    tree = ast.parse(source)
    work = copy.deepcopy(tree)
    sites = fn(work)
    if sites == 0:
        return None
    ast.fix_missing_locations(work)
    new = ast.unparse(work)
    if new + "\n" == source or (name != "reformat" and new == ast.unparse(tree)):
        return None  # nothing observable changed
    compile(new, "<rewrite>", "exec")  # must still be valid Python
    return Rewrite(name=name, description=desc, source=new + "\n", sites=sites)
