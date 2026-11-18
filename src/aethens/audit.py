"""Run checks over tasks and assemble a Report. Library code: no printing, no exit codes."""

from __future__ import annotations

import time
from collections.abc import Sequence
from datetime import UTC, datetime

from aethens import __version__
from aethens.checks import Check, CheckContext
from aethens.models import Report, Task


def run_audit(tasks: Sequence[Task], checks: Sequence[Check], ctx: CheckContext) -> Report:
    started = datetime.now(UTC).replace(microsecond=0).isoformat()
    t0 = time.monotonic()
    findings = []
    for task in tasks:
        for check in checks:
            findings.extend(check.run(task, ctx))
    return Report(
        tool_version=__version__,
        task_ids=tuple(t.id for t in tasks),
        checks_run=tuple(c.id for c in checks),
        budget=ctx.budget,
        seed=ctx.seed,
        findings=tuple(findings),
        started_at=started,
        duration_s=round(time.monotonic() - t0, 3),
    )
