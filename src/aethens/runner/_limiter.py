"""Exec wrapper for local mode: apply rlimits, then exec the verifier.

Invoked as ``python -I path/to/_limiter.py MEM_BYTES FSIZE_BYTES -- CMD...`` in a fresh process
group. Using a wrapper instead of ``preexec_fn`` keeps it safe when the parent has threads.
"""

from __future__ import annotations

import contextlib
import os
import resource
import sys


def main(argv: list[str]) -> None:
    mem, fsize = int(argv[0]), int(argv[1])
    if argv[2] != "--":
        raise SystemExit("usage: _limiter MEM FSIZE -- CMD...")
    cmd = argv[3:]
    for lim, value in ((resource.RLIMIT_AS, mem), (resource.RLIMIT_FSIZE, fsize)):
        # Not every OS supports every limit (macOS ignores RLIMIT_AS); see docs/STATUS.md.
        with contextlib.suppress(ValueError, OSError):
            resource.setrlimit(lim, (value, value))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.execvp(cmd[0], cmd)  # noqa: S606 - argument list, no shell


if __name__ == "__main__":
    main(sys.argv[1:])
