"""Entry point for the ``aethens`` console script. The only module that prints or exits.

Exit codes: 0 pass, 1 findings at or above --fail-on, 2 tool error, 3 timeout (a gold-solution run
in C001 or C002 hit the task's timeout, so the gold verdict could not be established).
Precedence: 2 > 3 > 1 > 0.

An unexpected internal error, a report that cannot be written, and SIGTERM are tool errors (2):
an uncaught exception would make Python exit 1, which CI reads as "findings". SIGTERM is turned
into an exception so every runner's cleanup (container removal, temp directories) still runs.
"""

from __future__ import annotations

import argparse
import signal
import sys
import traceback
from collections.abc import Callable
from pathlib import Path

from aethens import __version__
from aethens.adapters import load_tasks
from aethens.audit import default_jobs, run_audit
from aethens.cache import DockerImageDigest, ResultCache, default_cache_dir
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aethens", description="Validate the verifiers of code tasks by running them."
    )
    parser.add_argument("--version", action="version", version=f"aethens {__version__}")
    sub = parser.add_subparsers(dest="command")
    audit = sub.add_parser("audit", help="audit one task directory or a directory of tasks")
    audit.add_argument("path", help="a task directory (with task.yaml) or a directory of tasks")
    audit.add_argument(
        "--budget",
        choices=[b.value for b in Budget],
        default="standard",
        help="smoke: 3 flaky runs, 5 mutants; standard: 5, 10; deep: 10, 30",
    )
    audit.add_argument("--fail-on", choices=["error", "warning"], default="error")
    audit.add_argument("--format", choices=["json", "markdown"], default="json")
    audit.add_argument("--seed", type=int, default=0)
    audit.add_argument(
        "--check",
        action="append",
        choices=sorted(ALL_CHECKS),
        dest="checks",
        help="run only this check (repeatable); default: all",
    )
    audit.add_argument("--output", help="write the report to this file instead of stdout")
    audit.add_argument(
        "--jobs",
        type=int,
        default=None,
        help="tasks to audit at once (default: min(cpu count, 4)); report order stays fixed",
    )
    cache = audit.add_mutually_exclusive_group()
    cache.add_argument(
        "--no-cache",
        action="store_true",
        help="recompute every task and do not read or write the result cache",
    )
    cache.add_argument(
        "--cache-dir",
        type=Path,
        help="result cache directory (default: $XDG_CACHE_HOME/aethens or ~/.cache/aethens)",
    )
    audit.add_argument(
        "--unsafe-local",
        action="store_true",
        help="run task code directly on this machine WITHOUT container isolation",
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
    raise Terminated(f"terminated by signal {signum}")


def main(argv: list[str] | None = None) -> int:
    previous = signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        return _main(argv)
    except Terminated as exc:
        print(f"aethens: error: {exc}; running containers were removed", file=sys.stderr)
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
        docker_bin = "docker"
        if args.unsafe_local:
            print(UNSAFE_WARNING, file=sys.stderr)
            runner = LocalRunner(allow_unsafe_local=True)
        else:
            docker = DockerRunner()
            docker.ensure_available()
            docker_bin = docker.docker_bin
            runner = docker
        ids = sorted(set(args.checks or ALL_CHECKS))
        ctx = CheckContext(
            runner=runner,
            seed=args.seed,
            budget=Budget(args.budget),
            unsafe_local=args.unsafe_local,
        )
        jobs = default_jobs() if args.jobs is None else args.jobs
        cache: ResultCache | None = None
        fingerprint: Callable[[str], str] | None = None
        if not args.no_cache:
            cache_dir = args.cache_dir if args.cache_dir is not None else default_cache_dir()
            cache = ResultCache(cache_dir)
            if not args.unsafe_local:
                fingerprint = DockerImageDigest(docker_bin)
        report = run_audit(
            tasks,
            [ALL_CHECKS[i]() for i in ids],
            ctx,
            jobs=jobs,
            cache=cache,
            image_fingerprint=fingerprint,
        )
        if cache is not None:
            noun = "task" if len(tasks) == 1 else "tasks"
            print(
                f"aethens: {len(tasks)} {noun} ({cache.hits} from cache, {cache.misses} ran) "
                f"jobs={jobs}",
                file=sys.stderr,
            )
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
