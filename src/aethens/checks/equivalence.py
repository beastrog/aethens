"""Equivalent-mutant probe for C004 (D-065): is a surviving mutant really different from the gold?

A surviving mutant is only a sign of weak tests if it behaves differently from the gold on some
valid input. Many survivors are *equivalent mutants* (``if e > m: m = e`` vs ``>=`` in a running
maximum; a loop bound one step too far that only adds no-op iterations), and reporting them was
most of C004's false positives on the external bench.

The probe runs ``aethens.sandbox.equiv_driver`` in the same sandbox as every other run. The driver
records the arguments the task's own tests pass to the mutated module's functions, derives more
inputs from them, and calls the gold and the mutant side by side. Three outcomes:

- ``distinguished``: an input on which the mutant's result (or its effect on its arguments)
  differs from the gold's. The survivor is reported with that input as a counterexample.
- ``equivalent``: no difference on at least ``MIN_VALID`` valid inputs. The survivor is probably
  an equivalent mutant; C004 does not report it and lists it in its coverage statement instead.
- ``inconclusive``: the probe could not run or saw too few valid inputs (not a ``python -m
  unittest`` verifier, the tests never call a module-level function of the mutated file, the
  driver failed or timed out). The survivor is reported exactly as before the probe existed.

"No difference found" is not a proof of equivalence: a mutant that differs only on inputs the
derivation never produces (or only in speed) is filtered out. That is the recall cost, measured
by the external bench (docs/EXTERNAL_BENCH.md).
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path, PurePosixPath

from aethens.checks.base import CheckContext, hash_seed
from aethens.checks.c005_order import unittest_args
from aethens.checks.mutation import Mutant
from aethens.models import Budget, Task
from aethens.runner import RunSpec

MARKER = "AETHENS-EQUIV-RESULT "
DRIVER_DIR = Path(".aethens")
DRIVER_PATH = (DRIVER_DIR / "equiv_driver.py").as_posix()
PROBE_INPUTS = {Budget.SMOKE: 100, Budget.STANDARD: 300, Budget.DEEP: 1000}
PROBE_SECONDS = {Budget.SMOKE: 5.0, Budget.STANDARD: 8.0, Budget.DEEP: 30.0}
MIN_VALID = 20  # fewer valid inputs than this and "no difference" means nothing (inconclusive)
UNSTABLE_DIVISOR = 10  # gold self-disagreement on >= 1/10 of inputs: inconclusive (D-087)


@dataclass(frozen=True)
class Equivalence:
    status: str  # "distinguished", "equivalent" or "inconclusive"
    reason: str
    valid_inputs: int = 0
    counterexample: dict[str, str] = field(default_factory=dict)


def _module_file(file: str) -> bool:
    p = PurePosixPath(file)
    return p.suffix == ".py" and all(part.isidentifier() for part in (*p.parts[:-1], p.stem))


def parse(stdout: str) -> dict[str, object] | None:
    pos = stdout.rfind(MARKER)
    if pos < 0:
        return None
    rest = stdout[pos + len(MARKER) :]
    try:
        data = json.loads(rest.splitlines()[0] if rest else "")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def judge(data: dict[str, object] | None, min_valid: int = MIN_VALID) -> Equivalence:
    if data is None:
        return Equivalence("inconclusive", "the probe printed no result (failed or timed out)")
    if data.get("error"):
        return Equivalence("inconclusive", f"the probe could not start: {data['error']}")
    valid = data.get("valid")
    valid_n = valid if isinstance(valid, int) else 0
    diff = data.get("difference")
    if isinstance(diff, dict):
        cx = {k: str(v) for k, v in diff.items()}
        return Equivalence("distinguished", "a counterexample input was found", valid_n, cx)
    if not data.get("functions"):
        return Equivalence(
            "inconclusive", "the tests call no module-level function of the mutated file"
        )
    unstable = data.get("unstable")
    unstable_n = unstable if isinstance(unstable, int) else 0
    if unstable_n and unstable_n * UNSTABLE_DIVISOR >= valid_n + unstable_n:
        # The gold's own results differ between two calls on many inputs: the inputs that
        # remain "valid" are a biased sample, so "no difference" means nothing (D-087).
        return Equivalence(
            "inconclusive",
            f"the gold's results differ between two calls on {unstable_n} of "
            f"{valid_n + unstable_n} inputs",
            valid_n,
        )
    if valid_n < min_valid:
        return Equivalence(
            "inconclusive",
            f"only {valid_n} valid inputs (at least {min_valid} are needed)",
            valid_n,
        )
    return Equivalence(
        "equivalent", f"no difference from the gold on {valid_n} valid inputs", valid_n
    )


def probe(task: Task, mutant: Mutant, ctx: CheckContext, hs: str) -> Equivalence:
    """Run the driver for one surviving mutant (one sandbox run)."""
    args = unittest_args(task.verifier)
    if args is None:
        return Equivalence("inconclusive", "the verifier is not 'python -m unittest ...'")
    if not _module_file(mutant.file):
        return Equivalence("inconclusive", f"{mutant.file} is not an importable module")
    seed = hash_seed(ctx.seed, task.id, "C004-equivalence", mutant.key) % (2**31)
    budget_s = PROBE_SECONDS[ctx.budget]
    with tempfile.TemporaryDirectory(prefix="aethens-equiv-") as tmp:
        d = Path(tmp)
        source = resources.files("aethens.sandbox").joinpath("equiv_driver.py")
        (d / "equiv_driver.py").write_text(source.read_text("utf-8"), "utf-8")
        target = d / "mutant" / mutant.file
        target.parent.mkdir(parents=True)
        target.write_text(mutant.source, "utf-8")
        spec = RunSpec(
            image=task.image,
            command=(
                task.verifier[0],
                DRIVER_PATH,
                str(seed),
                str(PROBE_INPUTS[ctx.budget]),
                f"{budget_s:g}",
                mutant.file,
                "--",
                *args,
            ),
            layers=(
                (task.root / task.starter, Path(".")),
                (task.root / task.gold, Path(".")),
                (task.root / task.tests, task.tests),
                (d, DRIVER_DIR),
            ),
            timeout_s=float(task.timeout_s) + budget_s + 10.0,
            env={"PYTHONHASHSEED": hs},
        )
        r = ctx.runner.run(spec)
    if r.timed_out:
        return Equivalence("inconclusive", "the probe timed out")
    return judge(parse(r.stdout_tail))
