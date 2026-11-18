"""Entry point for the ``aethens`` console script. The only module that prints.

B4 scope: ``aethens audit PATH`` with JSON output, so repro commands can be run by hand.
Markdown output, --fail-on and exit code 3 arrive in B6.
"""

from __future__ import annotations

import argparse
import json
import sys

from aethens import __version__
from aethens.adapters import load_tasks
from aethens.audit import run_audit
from aethens.checks import (
    C001GoldSanity,
    C002Flakiness,
    C003LabeledCandidates,
    C004MutationProbes,
    Check,
    CheckContext,
)
from aethens.errors import AethensError
from aethens.models import Budget, Severity
from aethens.runner import DockerRunner, LocalRunner, Runner

ALL_CHECKS: dict[str, type[Check]] = {
    "C001": C001GoldSanity,
    "C002": C002Flakiness,
    "C003": C003LabeledCandidates,
    "C004": C004MutationProbes,
}

EXIT_OK, EXIT_FINDINGS, EXIT_TOOL_ERROR = 0, 1, 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aethens", description="Validate the verifiers of code tasks by running them."
    )
    parser.add_argument("--version", action="version", version=f"aethens {__version__}")
    sub = parser.add_subparsers(dest="command")
    audit = sub.add_parser("audit", help="audit one task directory or a directory of tasks")
    audit.add_argument("path")
    audit.add_argument("--check", action="append", choices=sorted(ALL_CHECKS), dest="checks")
    audit.add_argument("--seed", type=int, default=0)
    audit.add_argument("--budget", choices=[b.value for b in Budget], default="standard")
    audit.add_argument(
        "--unsafe-local",
        action="store_true",
        help="run task code directly on this machine WITHOUT container isolation",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command != "audit":
        parser.print_help()
        return EXIT_OK
    try:
        runner: Runner
        if args.unsafe_local:
            print(
                "WARNING: --unsafe-local runs task and candidate code on this machine without "
                "container isolation. Only use it on code you trust.",
                file=sys.stderr,
            )
            runner = LocalRunner(allow_unsafe_local=True)
        else:
            runner = DockerRunner()
        tasks = load_tasks(args.path)
        ids = args.checks or sorted(ALL_CHECKS)
        checks = [ALL_CHECKS[i]() for i in sorted(set(ids))]
        ctx = CheckContext(
            runner=runner,
            seed=args.seed,
            budget=Budget(args.budget),
            unsafe_local=args.unsafe_local,
        )
        report = run_audit(tasks, checks, ctx)
    except AethensError as exc:
        print(f"aethens: error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR
    print(json.dumps(report.to_dict(), indent=2))
    if any(f.severity is Severity.ERROR for f in report.findings):
        return EXIT_FINDINGS
    return EXIT_OK
