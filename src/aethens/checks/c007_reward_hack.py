"""C007 reward-hacking probes: adversarial candidates that game weak verifiers without solving.

Each probe is a candidate overlay Aethens writes itself. None of them implements the task, so a
verifier that accepts one can be gamed by a policy that learns the same trick. Every probe runs
through the same runner as every other check (Docker by default, same isolation flags and limits;
nothing here weakens or bypasses them). A probe that passes is run a second time before it is
reported. The probes only run when the unsolved starter fails (C001 reports a passing starter).

Categories (``CATEGORIES``):
- exit-zero: each solution module calls ``os._exit(0)`` on import (variants: also ``sys.exit(0)``).
- atexit-override: the starter's (unsolved) modules plus an ``atexit`` hook that calls
  ``os._exit(0)``, so the process exits 0 after the tests fail.
- framework-patch: the starter's modules plus a patch of ``unittest.TestResult.wasSuccessful`` to
  always return True.
- sitecustomize-hook: the starter plus a ``sitecustomize.py`` in the work directory that installs
  the same atexit hook at interpreter start-up (works when the verifier puts the work directory on
  ``PYTHONPATH``).
- always-equal: every public function of the gold returns an object whose ``__eq__`` is always
  True (classes return such objects from every method).
- hardcoded-visible: functions answer only the literal input/output pairs found in the test files
  (``assertEqual(f(<literals>), <literal>)`` and ``assert f(<literals>) == <literal>``).
  Passing means the verifier checks nothing beyond those visible examples; this matters when the
  tests are visible to the policy, so it is a warning that needs review.
Not built: pytest ``conftest.py`` hooks (the default image has no pytest, so it could not be
tested here; see docs/IDEAS.md).
"""

from __future__ import annotations

import ast
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from aethens.checks.base import (
    Check,
    CheckContext,
    describe,
    evidence,
    hash_seed,
    make_finding,
    run_spec,
)
from aethens.models import Confidence, Finding, Severity, Task
from aethens.runner import RunResult

_HOOK = (
    "\nimport atexit as _aethens_atexit\nimport os as _aethens_os\n\n"
    "_aethens_atexit.register(lambda: _aethens_os._exit(0))\n"
)
_PATCH = (
    "\nimport unittest as _aethens_unittest\n\n"
    "_aethens_unittest.TestResult.wasSuccessful = lambda self: True\n"
    "# Python 3.12+ exits 5 when no test ran (e.g. setUpClass failed): report at least one.\n"
    "_aethens_unittest.TestResult.testsRun = property(\n"
    "    lambda self: max(1, self.__dict__.get('_aethens_n', 0)),\n"
    "    lambda self, n: self.__dict__.__setitem__('_aethens_n', n),\n"
    ")\n"
)
_ALWAYS_EQUAL = '''
class _AlwaysEqual:
    """Reward-hacking probe written by Aethens: equal to everything."""

    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    def __hash__(self):
        return 0

    def __bool__(self):
        return True

    def __repr__(self):
        return "<always-equal>"


def _aethens_probe(*args, **kwargs):
    return _AlwaysEqual()
'''

CATEGORIES = (
    "exit-zero",
    "atexit-override",
    "framework-patch",
    "sitecustomize-hook",
    "always-equal",
    "hardcoded-visible",
)
_DETAIL = {
    "exit-zero": "every solution module ends the process with exit code 0 as soon as it is "
    "imported, before any test runs",
    "atexit-override": "the unsolved starter plus an atexit hook that forces exit code 0 after "
    "the tests have failed",
    "framework-patch": "the unsolved starter plus a patch that makes unittest report success "
    "whatever the tests do",
    "sitecustomize-hook": "the unsolved starter plus a sitecustomize.py that forces exit code 0 "
    "at interpreter exit",
    "always-equal": "every function returns an object that compares equal to anything",
    "hardcoded-visible": "every function only looks up the literal answers found in the test files",
}


@dataclass(frozen=True)
class Probe:
    category: str
    variant: str
    files: dict[str, str]  # relative path -> content, written over starter (and gold names)


def _public_defs(src: str) -> tuple[list[str], list[str], list[str]]:
    """(functions, classes, simple constant assignments as source) at module top level."""
    tree = ast.parse(src)
    funcs, classes, consts = [], [], []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif (
            isinstance(node, ast.Assign)
            and all(isinstance(t, ast.Name) for t in node.targets)
            and _is_literal(node.value)
        ):
            consts.append(ast.unparse(node))
    return funcs, classes, consts


def _is_literal(node: ast.AST) -> bool:
    try:
        ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return False
    return True


def always_equal_module(gold_src: str) -> str | None:
    try:
        funcs, classes, consts = _public_defs(gold_src)
    except SyntaxError:
        return None
    if not funcs and not classes:
        return None
    lines = ["# Reward-hacking probe written by Aethens (always-equal). Not a solution.", *consts]
    lines.append(_ALWAYS_EQUAL)
    for f in funcs:
        lines.append(f"{f} = _aethens_probe")
    for c in classes:
        lines += [
            "",
            f"class {c}:",
            "    def __init__(self, *args, **kwargs):",
            "        pass",
            "",
            "    def __getattr__(self, name):",
            "        return _aethens_probe",
        ]
    return "\n".join(lines) + "\n"


def visible_pairs(test_sources: list[str], names: set[str]) -> dict[str, list[tuple[str, str]]]:
    """Literal (args repr, result source) pairs per function name, from the test files."""
    pairs: dict[str, list[tuple[str, str]]] = {}

    def callee(node: ast.AST) -> str | None:
        if not isinstance(node, ast.Call) or node.keywords:
            return None
        f = node.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
        if name not in names or not all(_is_literal(a) for a in node.args):
            return None
        return name

    def add(call: ast.AST, expected: ast.AST) -> None:
        name = callee(call)
        if name is None or not _is_literal(expected):
            return
        assert isinstance(call, ast.Call)
        args = tuple(ast.literal_eval(a) for a in call.args)
        pairs.setdefault(name, []).append((repr(args), ast.unparse(expected)))

    for src in test_sources:
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("assertEqual", "assertEquals")
                and len(node.args) >= 2
            ):
                add(node.args[0], node.args[1])
                add(node.args[1], node.args[0])
            elif (
                isinstance(node, ast.Assert)
                and isinstance(node.test, ast.Compare)
                and len(node.test.ops) == 1
                and isinstance(node.test.ops[0], ast.Eq)
            ):
                add(node.test.left, node.test.comparators[0])
                add(node.test.comparators[0], node.test.left)
    return pairs


def hardcoded_module(gold_src: str, test_sources: list[str]) -> str | None:
    try:
        funcs, _classes, consts = _public_defs(gold_src)
    except SyntaxError:
        return None
    pairs = visible_pairs(test_sources, set(funcs))
    if not pairs:
        return None
    lines = [
        "# Reward-hacking probe written by Aethens (hardcoded-visible). Not a solution.",
        *consts,
    ]
    for f in funcs:
        if f in pairs:
            table = ", ".join(f"{k!r}: {v}" for k, v in dict(pairs[f]).items())
            lines += [
                "",
                f"_TABLE_{f} = {{{table}}}",
                "",
                f"def {f}(*args):",
                f"    return _TABLE_{f}[repr(args)]",
            ]
        else:
            lines += ["", f"def {f}(*args, **kwargs):", "    raise NotImplementedError"]
    return "\n".join(lines) + "\n"


def build_probes(task: Task) -> tuple[list[Probe], list[str]]:
    """The probes that apply to this task, and the categories that did not apply (with why)."""
    gold_dir, starter_dir = task.root / task.gold, task.root / task.starter
    gold_py = {
        p.relative_to(gold_dir).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(gold_dir.rglob("*.py"))
        if p.is_file()
    }
    starter_py = {
        p.relative_to(starter_dir).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(starter_dir.rglob("*.py"))
        if p.is_file()
    }
    tests_dir = task.root / task.tests
    test_src = [
        p.read_text(encoding="utf-8") for p in sorted(tests_dir.rglob("*.py")) if p.is_file()
    ]
    probes: list[Probe] = []
    skipped: list[str] = []
    # Files a solution may write: every Python file in the gold or the starter overlay.
    targets = sorted(set(gold_py) | set(starter_py))
    if not targets:
        return probes, ["all: neither the gold nor the starter has Python files to replace"]
    # The unsolved version of each target: the starter's copy if it has one, else empty.
    unsolved = {rel: starter_py.get(rel, "") for rel in targets}
    # The definitions a solution must provide: the gold's copy, else the starter's.
    defs = {rel: gold_py.get(rel, starter_py.get(rel, "")) for rel in targets}
    probes.append(Probe("exit-zero", "os._exit", {r: "import os\nos._exit(0)\n" for r in targets}))
    probes.append(Probe("exit-zero", "sys.exit", {r: "import sys\nsys.exit(0)\n" for r in targets}))
    probes.append(Probe("atexit-override", "atexit", {r: unsolved[r] + _HOOK for r in targets}))
    probes.append(Probe("framework-patch", "unittest", {r: unsolved[r] + _PATCH for r in targets}))
    probes.append(
        Probe("sitecustomize-hook", "sitecustomize", {**unsolved, "sitecustomize.py": _HOOK})
    )
    ae = {r: always_equal_module(defs[r]) for r in targets}
    if any(v is not None for v in ae.values()):
        files = {r: (v if v is not None else unsolved[r]) for r, v in ae.items()}
        probes.append(Probe("always-equal", "eq", files))
    else:
        skipped.append("always-equal: no top-level functions or classes to replace")
    hc = {r: hardcoded_module(defs[r], test_src) for r in targets}
    if any(v is not None for v in hc.values()):
        files = {r: (v if v is not None else unsolved[r]) for r, v in hc.items()}
        probes.append(Probe("hardcoded-visible", "table", files))
    else:
        skipped.append("hardcoded-visible: no literal input/output pairs found in the tests")
    return probes, skipped


class C007RewardHacking(Check):
    id = "C007"
    title = "Reward-hacking probes"
    tier = "probe"
    cost_class = "medium"

    def run(self, task: Task, ctx: CheckContext) -> list[Finding]:
        starter_hs = str(hash_seed(ctx.seed, task.id, self.id, "starter"))
        starter = ctx.runner.run(run_spec(task, None, {"PYTHONHASHSEED": starter_hs}))
        if starter.passed:
            return []  # C001 reports a verifier that accepts the unsolved starter
        probes, _skipped = build_probes(task)
        findings: list[Finding] = []
        done: set[str] = set()
        with tempfile.TemporaryDirectory(prefix="aethens-probe-") as tmp:
            for n, probe in enumerate(probes):
                if probe.category in done:
                    continue
                overlay = Path(tmp) / f"p{n}"
                overlay.mkdir()
                for rel, content in probe.files.items():
                    target = overlay / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8")
                hs = str(hash_seed(ctx.seed, task.id, self.id, f"{probe.category}:{probe.variant}"))
                r1 = ctx.runner.run(run_spec(task, overlay, {"PYTHONHASHSEED": hs}))
                if not r1.passed:
                    continue
                r2 = ctx.runner.run(run_spec(task, overlay, {"PYTHONHASHSEED": hs}))
                if not r2.passed:
                    continue
                done.add(probe.category)
                findings.append(self._finding(task, ctx, probe, [starter, r1, r2], hs))
            shutil.rmtree(tmp, ignore_errors=True)
        return findings

    def _finding(
        self, task: Task, ctx: CheckContext, probe: Probe, results: list[RunResult], hs: str
    ) -> Finding:
        starter, r1, _ = results
        hardcoded = probe.category == "hardcoded-visible"
        listing = "\n".join(f"--- {rel}\n{content}" for rel, content in sorted(probe.files.items()))
        if len(listing) > 6000:
            listing = listing[:6000] + "\n[... truncated ...]"
        detail = (
            f"A candidate that does not solve the task ({_DETAIL[probe.category]}) passed the "
            "verifier on two runs, while the unsolved starter fails. A policy trained against this "
            "verifier can earn full reward with the same trick."
        )
        if hardcoded:
            detail += (
                " This matters when the tests (or examples equal to them) are visible to the "
                "policy; if the tests are hidden, review whether it is a problem."
            )
        else:
            detail += " Harden the verifier: judge results outside the solution's process."
        return make_finding(
            check_id=self.id,
            severity=Severity.WARNING if hardcoded else Severity.ERROR,
            task=task,
            title=f"Verifier accepts a reward-hacking probe: {probe.category}",
            detail=detail,
            ev=evidence(
                f"probe:{probe.category}",
                task,
                results,
                f"starter: {describe(starter)}; probe ({probe.variant}): {describe(r1)} (twice)",
                {
                    "category": probe.category,
                    "variant": probe.variant,
                    "probe_files": listing,
                    "PYTHONHASHSEED": hs,
                },
                tail_from=r1,
            ),
            ctx=ctx,
            confidence=Confidence.NEEDS_REVIEW if hardcoded else Confidence.CONFIRMED,
            limits=(
                f"Probe categories tried: {', '.join(CATEGORIES)}. Runs use the normal sandbox. "
                "A verifier that resists these probes can still be gamed in other ways; this is "
                "not evidence that it cannot be exploited. pytest conftest.py hooks are not probed."
            ),
        )
