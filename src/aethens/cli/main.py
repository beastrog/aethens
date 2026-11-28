"""Entry point for the ``aethens`` console script. The only module that prints or exits.

Exit codes: 0 pass, 1 findings at or above --fail-on, 2 tool error, 3 timeout (a gold-solution run
in C001 or C002 hit the task's timeout, so the gold verdict could not be established).
Precedence: 2 > 3 > 1 > 0.

An unexpected internal error, a report that cannot be written, SIGTERM and Ctrl-C (SIGINT) are
tool errors (2): an uncaught exception would make Python exit 1, which CI reads as "findings".
SIGTERM is turned into an exception so every runner's cleanup (container removal, temp
directories) still runs; the message then says what that cleanup confirmed.
"""

from __future__ import annotations

import argparse
import signal
import sys
import traceback
from pathlib import Path

from aethens import __version__
from aethens.adapters import load_tasks
from aethens.audit import run_audit
from aethens.checks import (
    C001GoldSanity,
    C002Flakiness,
    C003LabeledCandidates,
    C004MutationProbes,
    C005OrderDependence,
    C006OverSpecified,
    C007RewardHacking,
    Check,
    CheckContext,
)
from aethens.errors import AethensError
from aethens.models import Budget, Report, Severity
from aethens.report import render_json, render_markdown
from aethens.runner import DockerRunner, LocalRunner, Runner
from aethens.runner.docker import LEDGER

ALL_CHECKS: dict[str, type[Check]] = {
    "C001": C001GoldSanity,
    "C002": C002Flakiness,
    "C003": C003LabeledCandidates,
    "C004": C004MutationProbes,
    "C005": C005OrderDependence,
    "C006": C006OverSpecified,
    "C007": C007RewardHacking,
}

EXIT_OK, EXIT_FINDINGS, EXIT_TOOL_ERROR, EXIT_TIMEOUT = 0, 1, 2, 3
GOLD_TIMING_CHECKS = ("C001", "C002")

UNSAFE_WARNING = (
    "WARNING: --unsafe-local runs task and candidate code on this machine without container "
    "isolation. It can read your files and use your network. Only use it on code you trust."
)

# Shown by `aethens` and `aethens audit --help`. Kept in one place so the two texts cannot drift.
HELP_EPILOG = """\
examples:
  aethens audit path/to/task
  aethens audit path/to/task --budget smoke --check C001 --seed 0
  aethens audit path/to/task --format markdown --fail-on warning

exit codes:
  0  no finding at or above --fail-on
  1  findings at or above --fail-on
  2  tool error (bad task, Docker unavailable, Ctrl-C, internal error)
  3  a gold-solution run in C001 or C002 timed out

A run with no error or warning findings means these checks found nothing at this
budget and seed. It does not mean the verifier is sound.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aethens",
        description=(
            "Audit the verifiers of code tasks by running them in a Docker sandbox. "
            "Every finding includes what was run, what happened, and a one-line repro."
        ),
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"aethens {__version__}")
    sub = parser.add_subparsers(dest="command")
    audit = sub.add_parser(
        "audit",
        help="audit one task directory or a directory of tasks",
        description=(
            "Run the task verifiers in a Docker sandbox and write a report. "
            "Each finding has evidence and a one-line repro command."
        ),
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    audit.add_argument(
        "path",
        help="a task directory (contains task.yaml) or a directory of tasks",
    )
    audit.add_argument(
        "--budget",
        choices=[b.value for b in Budget],
        default="standard",
        help=(
            "how far the checks go (default: %(default)s). "
            "smoke / standard / deep: C002 starts at 3 / 5 / 10 gold runs "
            "(stops early once it can bound the flake rate); "
            "C004 tries up to 5 / 10 / 30 mutants"
        ),
    )
    audit.add_argument(
        "--fail-on",
        choices=["error", "warning"],
        default="error",
        help="minimum severity that exits 1 (default: %(default)s). warning also fails on warnings",
    )
    audit.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="report on stdout, or in --output (default: %(default)s)",
    )
    audit.add_argument(
        "--seed",
        type=int,
        default=0,
        help="seed for shuffles, mutants and PYTHONHASHSEED (default: %(default)s)",
    )
    audit.add_argument(
        "--check",
        action="append",
        choices=sorted(ALL_CHECKS),
        dest="checks",
        help="run only this check (repeatable). Default: C001 through C007",
    )
    audit.add_argument("--output", help="write the report to this file instead of stdout")
    audit.add_argument(
        "--unsafe-local",
        action="store_true",
        help=(
            "run task code on this machine with no container isolation. "
            "It can read your files and use your network. Only for code you trust"
        ),
    )
    return parser


def exit_code_for(report: Report, fail_on: Severity) -> int:
    for f in report.findings:
        ev = f.evidence
        if f.check_id in GOLD_TIMING_CHECKS and ev.subject == "gold" and ev.timed_out:
            return EXIT_TIMEOUT
    if any(f.severity.rank >= fail_on.rank for f in report.findings):
        return EXIT_FINDINGS
    return EXIT_OK


class Terminated(BaseException):  # not Exception: generic handlers must not swallow it
    """SIGTERM arrived; raised in the main thread so cleanup code runs."""


def _on_sigterm(signum: int, _frame: object) -> None:
    # Python runs this in the main thread between bytecode instructions. A wait in
    # subprocess.Popen.wait (DockerRunner._wait) is interrupted, so the runner's finally removes
    # the container. A future wait inside C code that ignores signals would delay this until it
    # returns.
    raise Terminated(f"terminated by signal {signum}")


def cleanup_summary() -> str:
    """What container cleanup confirmed after an interruption (never claims more than that)."""
    started, left = LEDGER.snapshot()
    if left:
        return (
            f"removal of {len(left)} container(s) was not confirmed: {' '.join(left)}; "
            "check with: docker ps -a --filter label=aethens.run=1"
        )
    if started == 0:
        return "no container had been started"
    return f"cleanup ran: removal of all {started} container(s) confirmed"


def main(argv: list[str] | None = None) -> int:
    LEDGER.reset()
    previous = signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        return _main(argv)
    except Terminated as exc:
        print(f"aethens: error: {exc}; {cleanup_summary()}", file=sys.stderr)
        return EXIT_TOOL_ERROR
    except KeyboardInterrupt:
        print(f"aethens: error: interrupted (Ctrl-C); {cleanup_summary()}", file=sys.stderr)
        return EXIT_TOOL_ERROR
    except Exception as exc:  # a crash must never look like "findings" (exit 1)
        traceback.print_exc(file=sys.stderr)
        print(f"aethens: internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR
    finally:
        signal.signal(signal.SIGTERM, previous)


def _main(argv: list[str] | None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command != "audit":
        parser.print_help()
        return EXIT_OK
    try:
        runner: Runner
        tasks = load_tasks(args.path)
        if args.unsafe_local:
            print(UNSAFE_WARNING, file=sys.stderr)
            runner = LocalRunner(allow_unsafe_local=True)
        else:
            docker = DockerRunner()
            docker.ensure_available()
            runner = docker
        ids = sorted(set(args.checks or ALL_CHECKS))
        ctx = CheckContext(
            runner=runner,
            seed=args.seed,
            budget=Budget(args.budget),
            unsafe_local=args.unsafe_local,
        )
        report = run_audit(tasks, [ALL_CHECKS[i]() for i in ids], ctx)
    except AethensError as exc:
        print(f"aethens: error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR
    text = render_json(report) if args.format == "json" else render_markdown(report)
    if args.output:
        try:
            Path(args.output).write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"aethens: error: cannot write {args.output}: {exc}", file=sys.stderr)
            return EXIT_TOOL_ERROR
    else:
        print(text)
    return exit_code_for(report, Severity(args.fail_on))
