"""Entry point for the ``aethens`` console script.

B1 provides only ``--version``; the ``audit`` command arrives with the checks (B4) and is
completed in B6.
"""

from __future__ import annotations

import argparse
import sys

from aethens import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aethens", description=__doc__)
    parser.add_argument("--version", action="version", version=f"aethens {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(sys.argv[1:] if argv is None else argv)
    parser.print_help()
    return 0
