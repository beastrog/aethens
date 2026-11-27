"""Aethens equivalence driver. Runs INSIDE the sandbox (copied to /work/.aethens/), never in
Aethens.

Usage: python .aethens/equiv_driver.py SEED MAX_INPUTS SECONDS FILE -- [unittest arguments, as in
the verifier]

FILE is the gold file that was mutated (relative to /work, e.g. ``solution.py``); the mutant copy of
it is at ``.aethens/mutant/FILE``. The driver:

1. wraps every module-level function of the gold module FILE and runs the verifier's own unittest
   tests (output discarded), recording the arguments of every call made from test code (not from
   the gold module itself): these are the seed inputs, i.e. inputs the task's tests already use;
2. derives more inputs from the seeds with small type-aware edits (EvalPlus-style: neighbouring
   numbers with the same sign, one-character string edits, list element drops, duplicates, swaps
   and element edits, plus boundary values around the integer constants in FILE and its string
   constants as words), deterministic for SEED;
3. calls the gold function and the mutant function on each input, each on its own deep copy, and
   compares results (``==``, floats with a relative tolerance of 1e-9) and the arguments after the
   call, until MAX_INPUTS inputs or SECONDS seconds. Inputs on which the gold raises, times out
   or is not deterministic are skipped: they are probably outside the task's input domain.

It prints one line on stdout:
  AETHENS-EQUIV-RESULT {"v": 1, "functions": [...], "seeds": n, "tried": n, "valid": n,
                        "difference": null | {"function", "args", "gold", "mutant", "from_tests"}}
A difference proves the mutant behaves differently from the gold on that input. No difference only
means none was found among the inputs tried. Standard library only.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import importlib
import importlib.util
import io
import json
import math
import os
import random
import signal
import sys
import time
import types
import unittest
from typing import Any

MARKER = "AETHENS-EQUIV-RESULT "
CALL_TIMEOUT_S = 2.0
SEED_CAP = 200  # recorded calls kept per function
REPR_CHARS = 300
_EXTRA_CHARS = " .!0Z"  # rare out-of-sample characters (spaces, punctuation, a digit, upper case)


class Pools:
    """Values harvested from the gold source: boundary-value analysis around its constants."""

    def __init__(self, source: str) -> None:
        ints: set[int] = set()
        strs: set[str] = set()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            tree = ast.Module(body=[], type_ignores=[])
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant):
                v = node.value
                if isinstance(v, int) and not isinstance(v, bool) and abs(v) <= 10**6:
                    ints.update((v - 1, v, v + 1))
                elif isinstance(v, str) and 0 < len(v) <= 20 and "\n" not in v:
                    strs.add(v)
        self.ints = sorted(ints)
        self.words = sorted(w for w in strs if w.strip() and " " not in w)
        self.chars = sorted({c for w in strs for c in w if c.isprintable()})


POOLS = Pools("")


class _CallTimeout(BaseException):
    pass


def _on_alarm(_signum: int, _frame: object) -> None:
    raise _CallTimeout


def _short(value: object) -> str:
    try:
        text = repr(value)
    except Exception as exc:
        text = f"<unrepresentable {type(value).__name__}: {exc}>"
    return text if len(text) <= REPR_CHARS else text[: REPR_CHARS - 3] + "..."


# --- recording ---------------------------------------------------------------------------------


def record(module: types.ModuleType, unittest_args: list[str]) -> dict[str, list[Any]]:
    seeds: dict[str, list[Any]] = {}
    own = module.__name__

    def wrap(name: str, fn: Any) -> Any:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            caller = sys._getframe(1).f_globals.get("__name__")
            if caller != own and len(seeds.setdefault(name, [])) < SEED_CAP:
                with contextlib.suppress(Exception):  # uncopyable inputs are not recorded
                    seeds[name].append(copy.deepcopy((args, kwargs)))
            return fn(*args, **kwargs)

        wrapper.__wrapped__ = fn  # type: ignore[attr-defined]
        return wrapper

    originals = {
        k: v
        for k, v in vars(module).items()
        if isinstance(v, types.FunctionType) and v.__module__ == own
    }
    for k, v in originals.items():
        setattr(module, k, wrap(k, v))
    saved_err, saved_out = sys.stderr, sys.stdout
    sys.stderr = sys.stdout = io.StringIO()
    try:
        unittest.main(module=None, argv=["python -m unittest", *unittest_args], exit=False)
    except BaseException:  # noqa: S110 - the tests' own failures do not matter here
        pass
    finally:
        sys.stderr, sys.stdout = saved_err, saved_out
        for k, v in originals.items():
            setattr(module, k, v)
    return {k: v for k, v in seeds.items() if v}


# --- input generation --------------------------------------------------------------------------


def _edit_number(x: Any, rng: random.Random) -> Any:
    if isinstance(x, bool):
        return not x
    if isinstance(x, int):
        if POOLS.ints and rng.random() < 0.3:
            y = rng.choice(POOLS.ints)
        else:
            y = rng.choice([x + 1, x - 1, x + 2, x - 2, x * 2, x // 2, x + rng.randint(3, 10)])
        return max(y, 0) if x >= 0 else y
    y = rng.choice([x + 0.5, x - 0.5, x * 2, x / 2, x + rng.random()])
    return max(y, 0.0) if x >= 0 else y


def _edit_tokens(s: str, rng: random.Random) -> str:
    words = s.split(" ")
    i = rng.randrange(len(words))
    op = rng.randrange(4)
    if op == 0 and len(words) > 1:
        del words[i]
    elif op == 1:
        words.insert(i, words[i])
    elif op == 2:
        rng.shuffle(words)
    elif POOLS.words:
        words.insert(i, rng.choice(POOLS.words))
    return " ".join(words)


def _edit_str(s: str, rng: random.Random) -> str:
    if not s:
        return s
    if " " in s.strip() and rng.random() < 0.5:
        return _edit_tokens(s, rng)
    i = rng.randrange(len(s))
    if rng.random() < 0.1:
        return s[:i] + rng.choice(_EXTRA_CHARS + "".join(POOLS.chars)) + s[i:]
    if rng.random() < 0.1 and s[i].isalpha():
        return s[:i] + s[i].swapcase() + s[i + 1 :]
    op = rng.randrange(5)
    if op == 0:
        return s[:i] + s[i + 1 :]
    if op == 1:
        return s[:i] + s[i] + s[i:]
    if op == 2 and len(s) > 1:
        j = min(i + 1, len(s) - 1)
        lst = list(s)
        lst[i], lst[j] = lst[j], lst[i]
        return "".join(lst)
    if op == 3:
        return s[:i] + rng.choice(s) + s[i:]
    return s[:i] + rng.choice(s) + s[i + 1 :]


def _edit_seq(seq: list[Any], rng: random.Random, depth: int) -> list[Any]:
    out = list(seq)
    if not out:
        return out
    i = rng.randrange(len(out))
    op = rng.randrange(5)
    if op == 0:
        del out[i]
    elif op == 1:
        out.insert(i, copy.deepcopy(out[i]))
    elif op == 2:
        j = rng.randrange(len(out))
        out[i], out[j] = out[j], out[i]
    elif op == 3:
        out.append(edit(copy.deepcopy(out[i]), rng, depth + 1))
    else:
        out[i] = edit(out[i], rng, depth + 1)
    return out


def edit(value: Any, rng: random.Random, depth: int = 0) -> Any:
    if depth > 4:
        return value
    if isinstance(value, bool | int | float):
        return _edit_number(value, rng)
    if isinstance(value, str):
        return _edit_str(value, rng)
    if isinstance(value, list):
        return _edit_seq(value, rng, depth)
    if isinstance(value, tuple):
        return tuple(_edit_seq(list(value), rng, depth))
    if isinstance(value, dict) and value:
        out = dict(value)
        k = rng.choice(list(out))
        if rng.random() < 0.3 and len(out) > 1:
            del out[k]
        else:
            out[k] = edit(out[k], rng, depth + 1)
        return out
    return value


def derive(seeds: list[Any], rng: random.Random, n: int) -> list[Any]:
    inputs = list(seeds)
    while len(inputs) < n and seeds:
        args, kwargs = copy.deepcopy(rng.choice(seeds))
        args = list(args)
        for _ in range(rng.randint(1, 3)):
            if args and (not kwargs or rng.random() < 0.7):
                i = rng.randrange(len(args))
                args[i] = edit(args[i], rng)
            elif kwargs:
                k = rng.choice(sorted(kwargs))
                kwargs[k] = edit(kwargs[k], rng)
        inputs.append((tuple(args), kwargs))
    return inputs


# --- comparison --------------------------------------------------------------------------------


def same(a: Any, b: Any, depth: int = 0) -> bool:
    if depth > 50:
        return False
    numbers = isinstance(a, int | float) and isinstance(b, int | float)
    if numbers and (isinstance(a, float) or isinstance(b, float)):
        if math.isnan(a) and math.isnan(b):
            return True
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
    if isinstance(a, list | tuple) and isinstance(b, list | tuple):
        return (
            type(a) is type(b)
            and len(a) == len(b)
            and all(same(x, y, depth + 1) for x, y in zip(a, b, strict=True))
        )
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k], depth + 1) for k in a)
    identity_eq: Any = type(a).__eq__
    if type(a) is type(b) and a is not b and identity_eq is object.__eq__:
        # No value equality (re.Match, plain class instances): `==` is identity, so two equal
        # results would never compare equal. Compare their repr instead (D-087).
        try:
            return repr(a) == repr(b)
        except Exception:
            return False
    try:
        return bool(a == b) and (a is None) == (b is None)
    except Exception:
        return False


def call(fn: Any, args: Any, kwargs: Any) -> tuple[str, Any, Any]:
    a, k = copy.deepcopy((args, kwargs))
    signal.setitimer(signal.ITIMER_REAL, CALL_TIMEOUT_S)
    try:
        out = fn(*a, **k)
        return "ok", out, (a, k)
    except _CallTimeout:
        return "timeout", None, None
    except Exception as exc:
        return "raise", type(exc).__name__, None
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def main(argv: list[str]) -> int:
    global POOLS
    seed, max_inputs, seconds, target = int(argv[0]), int(argv[1]), float(argv[2]), argv[3]
    rest = argv[argv.index("--") + 1 :] if "--" in argv else []
    signal.signal(signal.SIGALRM, _on_alarm)
    sys.path.insert(0, os.getcwd())
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 5000))
    modname = target[:-3].replace("/", ".")
    result: dict[str, Any] = {
        "v": 1,
        "functions": [],
        "seeds": 0,
        "tried": 0,
        "valid": 0,
        "unstable": 0,
        "difference": None,
    }
    try:
        gold = importlib.import_module(modname)
        spec = importlib.util.spec_from_file_location(
            "aethens_mutant_" + modname.replace(".", "_"),
            os.path.join(".aethens", "mutant", target),
        )
        if spec is None or spec.loader is None:
            raise ImportError("cannot load the mutant")
        mutant = importlib.util.module_from_spec(spec)
        saved = sys.stdout
        sys.stdout = io.StringIO()
        try:
            spec.loader.exec_module(mutant)
        finally:
            sys.stdout = saved
        with open(target, encoding="utf-8") as fh:
            POOLS = Pools(fh.read())
        seeds = record(gold, rest)
    except BaseException as exc:
        result["error"] = f"{type(exc).__name__}: {_short(exc)}"
        print(MARKER + json.dumps(result))
        return 0
    result["functions"] = sorted(seeds)
    result["seeds"] = sum(len(v) for v in seeds.values())
    rng = random.Random(seed)  # noqa: S311 - input generation, not security
    deadline = time.monotonic() + seconds
    per_fn = max(1, max_inputs // max(1, len(seeds)))
    saved_out = sys.stdout
    sys.stdout = io.StringIO()  # task code may print; keep the marker line clean
    try:
        for name in sorted(seeds):
            g, m = getattr(gold, name), getattr(mutant, name, None)
            if m is None:
                continue
            for index, (args, kwargs) in enumerate(derive(seeds[name], rng, per_fn)):
                if time.monotonic() > deadline or result["difference"] is not None:
                    break
                result["tried"] += 1
                g1 = call(g, args, kwargs)
                if g1[0] != "ok":
                    continue
                g2 = call(g, args, kwargs)
                if g2[0] != "ok" or not same(g1[1], g2[1]) or not same(g1[2], g2[2]):
                    result["unstable"] += 1  # the gold disagrees with itself here (D-087)
                    continue
                result["valid"] += 1
                mm = call(m, args, kwargs)
                differs = mm[0] != "ok" or not same(g1[1], mm[1]) or not same(g1[2], mm[2])
                if differs:
                    if mm[0] == "ok":
                        shown = _short(mm[1])
                        if same(g1[1], mm[1]):
                            shown += " (but it changes its arguments differently)"
                    elif mm[0] == "raise":
                        shown = f"raises {mm[1]}"
                    else:
                        shown = f"does not return within {CALL_TIMEOUT_S:g} s"
                    result["difference"] = {
                        "function": name,
                        "args": _short(args) + (f" {_short(kwargs)}" if kwargs else ""),
                        "gold": _short(g1[1]),
                        "mutant": shown,
                        "from_tests": index < len(seeds[name]),
                    }
    finally:
        sys.stdout = saved_out
    print(MARKER + json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
