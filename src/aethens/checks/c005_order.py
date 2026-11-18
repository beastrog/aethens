"""C005 test order and isolation: does any test's verdict depend on which tests ran before it?

The verifier's tests are run in their default order (the baseline), reversed, in seeded shuffles,
and one at a time in a fresh container, by a small driver that runs inside the sandbox
(``aethens.sandbox.order_driver``). Every C005 run of a task uses the same PYTHONHASHSEED, so the
order is the only thing that changes. A test whose verdict differs from the baseline is reported
only if the change reproduces on a second run of both the baseline and the changed order; changes
that do not reproduce are info (they point at flakiness, see C002).

Only ``python -m unittest ...`` verifiers are supported. Anything else gets one info finding that
says C005 checked nothing, so a silent C005 never reads as a clean bill of health.
"""

from __future__ import annotations

import json
import random
import re
import shlex
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath

from aethens.checks.base import Check, CheckContext, hash_seed, make_finding
from aethens.models import Budget, Confidence, Evidence, Finding, Severity, Task
from aethens.runner import RunResult, RunSpec

MARKER = "AETHENS-ORDER-RESULT "
DRIVER_DIR = Path(".aethens")
DRIVER_PATH = (DRIVER_DIR / "order_driver.py").as_posix()
SHUFFLES = {Budget.SMOKE: 1, Budget.STANDARD: 2, Budget.DEEP: 5}
ISOLATE_CAP = {Budget.SMOKE: 10, Budget.STANDARD: 30, Budget.DEEP: 200}
_PYTHON = re.compile(r"^python(3(\.\d+)?)?$")
_PASSING = {"P", "S", "X"}
_WORDS = {
    "P": "pass",
    "F": "fail",
    "E": "error",
    "S": "skip",
    "X": "expected failure",
    "U": "unexpected success",
}


def unittest_args(verifier: tuple[str, ...]) -> tuple[str, ...] | None:
    """The arguments of a ``python -m unittest ARGS`` verifier, or None if it is not one."""
    if len(verifier) < 3 or verifier[1:3] != ("-m", "unittest"):
        return None
    if not _PYTHON.match(PurePosixPath(verifier[0]).name):
        return None
    return tuple(verifier[3:])


@dataclass(frozen=True)
class DriverRun:
    mode: str
    tests: tuple[str, ...] | None
    outcomes: dict[int, str]  # default-order index -> outcome code
    fixture_errors: int


def parse_driver_output(stdout: str) -> DriverRun | None:
    pos = stdout.rfind(MARKER)
    if pos < 0:
        return None
    line = stdout[pos + len(MARKER) :].splitlines()[0] if stdout[pos + len(MARKER) :] else ""
    try:
        data = json.loads(line)
        tests = data.get("tests")
        outcomes = {int(i): str(code) for i, code in data["run"]}
        return DriverRun(
            mode=str(data.get("mode", "")),
            tests=tuple(str(t) for t in tests) if isinstance(tests, list) else None,
            outcomes=outcomes,
            fixture_errors=int(data.get("fixture_errors", 0)),
        )
    except (ValueError, KeyError, TypeError):
        return None


def _describe_mode(mode: str) -> str:
    if mode == "reverse":
        return "in reversed order"
    if mode.startswith("shuffle:"):
        return f"in shuffled order (driver seed {mode.split(':', 1)[1]})"
    if mode.startswith("only:"):
        return "alone in a fresh process"
    return "in the default order"


def _short(mode: str) -> str:
    return "alone" if mode.startswith("only:") else mode


class C005OrderDependence(Check):
    id = "C005"
    title = "Test order and isolation"
    tier = "core"
    cost_class = "medium"

    def run(self, task: Task, ctx: CheckContext) -> list[Finding]:
        args = unittest_args(task.verifier)
        if args is None:
            return [self._unsupported(task, ctx)]
        hs = str(hash_seed(ctx.seed, task.id, self.id, "order"))
        with tempfile.TemporaryDirectory(prefix="aethens-driver-") as tmp:
            driver_dir = Path(tmp)
            source = resources.files("aethens.sandbox").joinpath("order_driver.py")
            (driver_dir / "order_driver.py").write_text(source.read_text("utf-8"), "utf-8")
            return self._run(task, ctx, args, hs, driver_dir)

    def _spec(self, task: Task, mode: str, args: tuple[str, ...], hs: str, d: Path) -> RunSpec:
        layers: list[tuple[Path, Path]] = [
            (task.root / task.starter, Path(".")),
            (task.root / task.gold, Path(".")),
            (task.root / task.tests, task.tests),
            (d, DRIVER_DIR),
        ]
        return RunSpec(
            image=task.image,
            command=(task.verifier[0], DRIVER_PATH, mode, "--", *args),
            layers=tuple(layers),
            timeout_s=float(task.timeout_s),
            env={"PYTHONHASHSEED": hs},
        )

    def _run(
        self, task: Task, ctx: CheckContext, args: tuple[str, ...], hs: str, d: Path
    ) -> list[Finding]:
        def drive(mode: str) -> tuple[RunSpec, RunResult, DriverRun | None]:
            spec = self._spec(task, mode, args, hs, d)
            r = ctx.runner.run(spec)
            return spec, r, parse_driver_output(r.stdout_tail)

        base_spec, base_r, base = drive("default")
        if base is None or base.tests is None:
            return [self._unparsable(task, ctx, base_spec, base_r, hs)]
        n = len(base.tests)
        plan = ["reverse"]
        for k in range(SHUFFLES[ctx.budget]):
            plan.append(f"shuffle:{hash_seed(ctx.seed, task.id, self.id, f'shuffle{k}')}")
        cap = ISOLATE_CAP[ctx.budget]
        indices = list(range(n))
        if n > cap:
            rng = random.Random(hash_seed(ctx.seed, task.id, self.id, "isolate"))  # noqa: S311
            indices = sorted(rng.sample(indices, cap))
        plan += [f"only:{i}" for i in indices]

        # test index -> list of (mode, outcome) where its verdict differs from the baseline
        changes: dict[int, list[tuple[str, str]]] = {}
        runs: dict[str, tuple[RunSpec, RunResult]] = {}
        for mode in plan:
            spec, r, got = drive(mode)
            runs[mode] = (spec, r)
            for i, code in self._diff(base, got).items():
                changes.setdefault(i, []).append((mode, code))
        if not changes:
            return []

        # Reproduce: the baseline once more, and every order that changed a verdict once more.
        _, _, base2 = drive("default")
        recheck: dict[str, DriverRun | None] = {}
        for mode in sorted({m for lst in changes.values() for m, _ in lst}):
            recheck[mode] = drive(mode)[2]
        findings: list[Finding] = []
        for i in sorted(changes):
            confirmed = [
                (m, c)
                for m, c in changes[i]
                if base2 is not None
                and base2.outcomes.get(i) == base.outcomes.get(i)
                and recheck[m] is not None
                and (recheck[m].outcomes.get(i) == c)  # type: ignore[union-attr]
            ]
            test_id = base.tests[i]
            if confirmed:
                findings.append(
                    self._finding(task, ctx, hs, test_id, base, i, confirmed, runs, base_r)
                )
            else:
                findings.append(self._unconfirmed(task, ctx, hs, test_id, base, i, changes[i]))
        return findings

    @staticmethod
    def _diff(base: DriverRun, got: DriverRun | None) -> dict[int, str]:
        out: dict[int, str] = {}
        if got is None:
            # The driver produced no result (crash, os._exit, timeout): no per-test verdicts to
            # compare. This is stated in the limits; C001/C002 cover runs that do not finish.
            return out
        for i, code in got.outcomes.items():
            old = base.outcomes.get(i)
            if old is None:
                continue
            if (old in _PASSING) != (code in _PASSING):
                out[i] = code
        return out

    def _finding(
        self,
        task: Task,
        ctx: CheckContext,
        hs: str,
        test_id: str,
        base: DriverRun,
        i: int,
        confirmed: list[tuple[str, str]],
        runs: dict[str, tuple[RunSpec, RunResult]],
        base_r: RunResult,
    ) -> Finding:
        old = base.outcomes[i]
        first_mode, first_code = confirmed[0]
        spec, r = runs[first_mode]
        where = "; ".join(f"{_describe_mode(m)}: {_WORDS.get(c, c)}" for m, c in confirmed)
        if old in _PASSING:
            meaning = (
                "It passes only because of state left behind by tests that run before it in the "
                "default order (or it is broken by tests that run before it in another order)."
            )
        else:
            meaning = (
                "It fails in the default order but passes in another order, so another test "
                "leaves state behind that breaks it."
            )
        changed_in = ", ".join(f"{_short(m)}={_WORDS.get(c, c)}" for m, c in confirmed)
        return make_finding(
            check_id=self.id,
            severity=Severity.ERROR,
            task=task,
            title=f"Test verdict depends on test order or isolation: {test_id}",
            detail=(
                f"{test_id} gives '{_WORDS.get(old, old)}' in the verifier's default order but "
                f"a different verdict {where}. {meaning} Solutions are judged by an accident of "
                "test order. Both the baseline and the changed order were run twice with the same "
                "PYTHONHASHSEED and gave the same verdicts."
            ),
            ev=Evidence(
                subject=f"test:{test_id}",
                command=spec.command,
                observed=(
                    f"default order: {_WORDS.get(old, old)}; {_describe_mode(first_mode)}: "
                    f"{_WORDS.get(first_code, first_code)}"
                ),
                exit_codes=(base_r.exit_code, r.exit_code),
                timed_out=base_r.timed_out or r.timed_out,
                stdout_tail=r.stdout_tail,
                stderr_tail=r.stderr_tail,
                extra={
                    "test_id": test_id,
                    "default_outcome": _WORDS.get(old, old),
                    "changed_in": changed_in,
                    "driver_command": shlex.join(spec.command),
                    "default_order": ",".join(base.tests or ()),
                    "PYTHONHASHSEED": hs,
                },
            ),
            ctx=ctx,
            confidence=Confidence.CONFIRMED,
            limits=self._limits(ctx),
        )

    def _unconfirmed(
        self,
        task: Task,
        ctx: CheckContext,
        hs: str,
        test_id: str,
        base: DriverRun,
        i: int,
        changes: list[tuple[str, str]],
    ) -> Finding:
        old = base.outcomes[i]
        changed_in = ", ".join(f"{_short(m)}={_WORDS.get(c, c)}" for m, c in changes)
        return make_finding(
            check_id=self.id,
            severity=Severity.INFO,
            task=task,
            title=f"Test verdict changed with order but did not reproduce: {test_id}",
            detail=(
                "A verdict change seen once was not seen again on a second run, so it is more "
                "likely flakiness than order dependence. See C002."
            ),
            ev=Evidence(
                subject=f"test:{test_id}",
                command=task.verifier,
                observed=f"default order: {_WORDS.get(old, old)}; seen once: {changed_in}",
                exit_codes=(),
                timed_out=False,
                stdout_tail="",
                stderr_tail="",
                extra={"test_id": test_id, "changed_in": changed_in, "PYTHONHASHSEED": hs},
            ),
            ctx=ctx,
            confidence=Confidence.NEEDS_REVIEW,
            limits=self._limits(ctx),
        )

    def _limits(self, ctx: CheckContext) -> str:
        return (
            f"Orders tried: default, reversed, {SHUFFLES[ctx.budget]} seeded shuffle(s) and up to "
            f"{ISOLATE_CAP[ctx.budget]} tests alone (budget {ctx.budget.value}). Dependence that "
            "only shows in an order not tried is missed, and so is a run that crashes before "
            "reporting per-test verdicts. The driver adds .aethens/ to the work "
            "directory; tests that list the work directory could notice it."
        )

    def _unsupported(self, task: Task, ctx: CheckContext) -> Finding:
        return make_finding(
            check_id=self.id,
            severity=Severity.INFO,
            task=task,
            title="Verifier is not `python -m unittest`; C005 checked nothing for this task",
            detail=(
                "C005 can reorder tests only for `python -m unittest ...` verifiers. Nothing was "
                "run, so this is not evidence that the tests are order-independent."
            ),
            ev=Evidence(
                subject="verifier",
                command=task.verifier,
                observed="unsupported verifier command",
                exit_codes=(),
                timed_out=False,
                stdout_tail="",
                stderr_tail="",
                extra={},
            ),
            ctx=ctx,
            confidence=Confidence.CONFIRMED,
            limits="Nothing was run for C005 on this task.",
        )

    def _unparsable(
        self, task: Task, ctx: CheckContext, spec: RunSpec, r: RunResult, hs: str
    ) -> Finding:
        return make_finding(
            check_id=self.id,
            severity=Severity.INFO,
            task=task,
            title="C005 could not list the tests; it checked nothing for this task",
            detail=(
                "The order driver did not report a test list (for example the tests fail to "
                "import, the gold solution exits the process, or the run timed out)."
            ),
            ev=Evidence(
                subject="driver",
                command=spec.command,
                observed="no driver result line in the output",
                exit_codes=(r.exit_code,),
                timed_out=r.timed_out,
                stdout_tail=r.stdout_tail,
                stderr_tail=r.stderr_tail,
                extra={"PYTHONHASHSEED": hs},
            ),
            ctx=ctx,
            confidence=Confidence.CONFIRMED,
            limits="Only the baseline run was attempted.",
        )
