"""Aethens order driver. Runs INSIDE the sandbox (copied to /work/.aethens/), never in Aethens.

Usage: python .aethens/order_driver.py MODE -- [unittest arguments, exactly as in the verifier]

MODE is one of:
  default        the order unittest itself would use
  reverse        that order reversed
  shuffle:SEED   a seeded shuffle of modules, then classes within a module, then tests within a
                 class (like pytest-randomly), so class and module fixtures stay grouped
  only:INDEX     only the test at INDEX in the default order (run alone, in this fresh process)

Discovery and argument parsing are unittest's own (``unittest.TestProgram`` with ``runTests``
replaced), so the driver finds exactly the tests ``python -m unittest ARGS`` would run. It prints
the normal verbose unittest output on stderr, then one line on stdout:
  AETHENS-ORDER-RESULT {"v": 1, "mode": ..., "tests": [default-order ids], "run": [[index, code]]}
Codes: P pass, F fail, E error, S skip, X expected failure, U unexpected success.
Exit code 0 when every test that ran succeeded, else 1. Standard library only.
"""

from __future__ import annotations

import json
import os
import random
import sys
import unittest
from typing import Any

MARKER = "AETHENS-ORDER-RESULT "
CODES = {
    "success": "P",
    "failure": "F",
    "error": "E",
    "skip": "S",
    "expected_failure": "X",
    "unexpected_success": "U",
}
_WORST = {"P": 0, "S": 0, "X": 0, "U": 1, "F": 2, "E": 3}
_MAX_IDS_CHARS = 40000  # keep the marker line inside the runner's 64 KiB output tail


def flatten(suite: unittest.TestSuite | unittest.TestCase) -> list[unittest.TestCase]:
    if isinstance(suite, unittest.TestSuite):
        out: list[unittest.TestCase] = []
        for item in suite:
            out.extend(flatten(item))
        return out
    return [suite]


def order_tests(tests: list[unittest.TestCase], mode: str) -> list[unittest.TestCase]:
    if mode == "default":
        return list(tests)
    if mode == "reverse":
        return list(reversed(tests))
    if mode.startswith("only:"):
        index = int(mode.split(":", 1)[1])
        if not 0 <= index < len(tests):
            raise ValueError(f"test index {index} out of range (0..{len(tests) - 1})")
        return [tests[index]]
    if mode.startswith("shuffle:"):
        rng = random.Random(int(mode.split(":", 1)[1]))  # noqa: S311 - ordering, not security
        modules: dict[str, dict[str, list[unittest.TestCase]]] = {}
        for t in tests:
            cls = type(t)
            modules.setdefault(cls.__module__, {}).setdefault(cls.__qualname__, []).append(t)
        groups = list(modules.values())
        rng.shuffle(groups)
        out: list[unittest.TestCase] = []
        for classes in groups:
            blocks = list(classes.values())
            rng.shuffle(blocks)
            for block in blocks:
                members = list(block)
                rng.shuffle(members)
                out.extend(members)
        return out
    raise ValueError(f"unknown mode {mode!r}")


class _Collect(unittest.TestProgram):
    """unittest's own argument parsing and discovery; running is done by the driver."""

    def runTests(self) -> None:
        return None


class _Result(unittest.TextTestResult):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.codes: dict[int, str] = {}

    def _set(self, test: unittest.TestCase, kind: str) -> None:
        code = CODES[kind]
        old = self.codes.get(id(test))
        if old is None or _WORST[code] > _WORST[old]:
            self.codes[id(test)] = code

    def addSuccess(self, test: unittest.TestCase) -> None:
        super().addSuccess(test)
        self._set(test, "success")

    def addFailure(self, test: unittest.TestCase, err: Any) -> None:
        super().addFailure(test, err)
        self._set(test, "failure")

    def addError(self, test: unittest.TestCase, err: Any) -> None:
        super().addError(test, err)
        self._set(test, "error")

    def addSkip(self, test: unittest.TestCase, reason: str) -> None:
        super().addSkip(test, reason)
        self._set(test, "skip")

    def addExpectedFailure(self, test: unittest.TestCase, err: Any) -> None:
        super().addExpectedFailure(test, err)
        self._set(test, "expected_failure")

    def addUnexpectedSuccess(self, test: unittest.TestCase) -> None:
        super().addUnexpectedSuccess(test)
        self._set(test, "unexpected_success")

    def addSubTest(self, test: unittest.TestCase, subtest: Any, err: Any) -> None:
        super().addSubTest(test, subtest, err)
        if err is not None:
            failed = issubclass(err[0], test.failureException)
            self._set(test, "failure" if failed else "error")


def main(argv: list[str]) -> int:
    # Behave like `python -m unittest`: the working directory, not this file's directory, is
    # sys.path[0].
    sys.path[0] = os.getcwd()
    if len(argv) < 3 or argv[2] != "--":
        sys.stderr.write("usage: order_driver.py MODE -- [unittest arguments]\n")
        return 2
    mode = argv[1]
    program = _Collect(module=None, argv=["python -m unittest", *argv[3:]], exit=False)
    tests = flatten(getattr(program, "test"))  # noqa: B009 - set by unittest, untyped
    ordered = order_tests(tests, mode)
    index = {id(t): i for i, t in enumerate(tests)}
    runner = unittest.TextTestRunner(
        stream=sys.stderr,
        verbosity=2,
        failfast=bool(program.failfast),
        buffer=bool(program.buffer),
        warnings=program.warnings,
        tb_locals=bool(getattr(program, "tb_locals", False)),
        resultclass=_Result,
    )
    result = runner.run(unittest.TestSuite(ordered))
    assert isinstance(result, _Result)
    ids: list[str] | None = [t.id() for t in tests]
    if len(json.dumps(ids)) > _MAX_IDS_CHARS:
        ids = None
    payload = {
        "v": 1,
        "mode": mode,
        "tests": ids,
        "count": len(tests),
        "run": [[index[id(t)], result.codes[id(t)]] for t in ordered if id(t) in result.codes],
        "fixture_errors": len(result.errors) - sum(1 for t, _ in result.errors if id(t) in index),
    }
    sys.stdout.write("\n" + MARKER + json.dumps(payload) + "\n")
    sys.stdout.flush()
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
