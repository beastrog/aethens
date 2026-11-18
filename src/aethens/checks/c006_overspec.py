"""C006 over-specified tests: do the tests reject a behaviour-preserving rewrite of the gold?

Each rewrite in ``aethens.checks.rewrites`` changes only what introspection can see (source text,
line numbers, local names, code shape) and keeps behaviour identical, under conditions each rewrite
checks (sites it cannot prove are skipped). If the gold passes but a rewritten gold fails, the tests
depend on implementation details, so they would also reject correct solutions written differently.
A rejection must reproduce on a second run, and the gold must pass, before it is reported.
No LLM is involved; Aethens never judges correctness here, it only compares two runs of programs
that behave identically.
"""

from __future__ import annotations

import difflib
import shutil
import tempfile
from pathlib import Path

from aethens.checks import rewrites
from aethens.checks.base import (
    Check,
    CheckContext,
    describe,
    evidence,
    hash_seed,
    make_finding,
    run_spec,
)
from aethens.models import Budget, Confidence, Evidence, Finding, Severity, Task
from aethens.runner import RunResult

FAMILIES = {
    Budget.SMOKE: ("reformat", "rename-locals"),
    Budget.STANDARD: tuple(rewrites.REWRITES),
    Budget.DEEP: tuple(rewrites.REWRITES),
}


class C006OverSpecified(Check):
    id = "C006"
    title = "Over-specified tests (behaviour-preserving rewrites)"
    tier = "probe"
    cost_class = "medium"

    def run(self, task: Task, ctx: CheckContext) -> list[Finding]:
        gold_dir = task.root / task.gold
        files: dict[str, str] = {}
        for p in sorted(gold_dir.rglob("*.py")):
            if p.is_file():
                files[p.relative_to(gold_dir).as_posix()] = p.read_text(encoding="utf-8")
        variants: list[tuple[str, dict[str, str], int]] = []
        for family in FAMILIES[ctx.budget]:
            changed: dict[str, str] = {}
            sites = 0
            for rel, src in files.items():
                try:
                    rw = rewrites.apply(family, src)
                except (SyntaxError, ValueError, RecursionError):
                    rw = None
                if rw is not None:
                    changed[rel] = rw.source
                    sites += rw.sites
            if changed:
                variants.append((family, changed, sites))
        if not variants:
            return [self._nothing(task, ctx, sorted(files))]
        gold_hs = str(hash_seed(ctx.seed, task.id, self.id, "gold"))
        gold = ctx.runner.run(run_spec(task, task.gold, {"PYTHONHASHSEED": gold_hs}))
        if not gold.passed:
            return []  # C001 reports a failing gold; nothing to compare against
        findings: list[Finding] = []
        with tempfile.TemporaryDirectory(prefix="aethens-rewrite-") as tmp:
            for n, (family, changed, sites) in enumerate(variants):
                overlay = Path(tmp) / f"r{n}"
                shutil.copytree(gold_dir, overlay, symlinks=False)
                for rel, src in changed.items():
                    (overlay / rel).write_text(src, encoding="utf-8")
                hs = str(hash_seed(ctx.seed, task.id, self.id, family))
                r1 = ctx.runner.run(run_spec(task, overlay, {"PYTHONHASHSEED": hs}))
                if r1.passed:
                    continue
                r2 = ctx.runner.run(run_spec(task, overlay, {"PYTHONHASHSEED": hs}))
                g2 = ctx.runner.run(run_spec(task, task.gold, {"PYTHONHASHSEED": hs}))
                if r2.passed or not g2.passed:
                    continue  # not reproducible: flakiness, not over-specification (see C002)
                findings.append(
                    self._finding(task, ctx, family, changed, files, sites, [gold, r1, r2], hs)
                )
        return findings

    def _finding(
        self,
        task: Task,
        ctx: CheckContext,
        family: str,
        changed: dict[str, str],
        files: dict[str, str],
        sites: int,
        results: list[RunResult],
        hs: str,
    ) -> Finding:
        _, desc = rewrites.REWRITES[family]
        diff_parts: list[str] = []
        for rel, new in changed.items():
            diff_parts.extend(
                difflib.unified_diff(
                    files[rel].splitlines(),
                    new.splitlines(),
                    fromfile=f"gold/{rel}",
                    tofile=f"rewritten/{rel}",
                    lineterm="",
                    n=1,
                )
            )
        diff = "\n".join(diff_parts)
        if len(diff) > 6000:
            diff = diff[:6000] + "\n[... diff truncated ...]"
        gold, r1, _ = results
        return make_finding(
            check_id=self.id,
            severity=Severity.WARNING,
            task=task,
            title=f"Tests reject a behaviour-preserving rewrite of the gold ({family})",
            detail=(
                f"The gold passes, but the same gold with {desc} ({sites} site(s)) fails, on two "
                "runs. The rewrite keeps behaviour identical; it changes only what introspection "
                "can see (source text, line numbers, local names or code shape). The tests "
                "therefore depend on implementation details and would reject correct solutions "
                "written differently. Review: if the task statement requires that implementation "
                "detail, the test may be intended."
            ),
            ev=evidence(
                f"rewrite:{family}",
                task,
                results,
                f"gold: {describe(gold)}; rewritten gold: {describe(r1)} (twice)",
                {
                    "rewrite": family,
                    "sites": str(sites),
                    "files": ",".join(sorted(changed)),
                    "diff": diff,
                    "PYTHONHASHSEED": hs,
                },
                tail_from=r1,
            ),
            ctx=ctx,
            confidence=Confidence.NEEDS_REVIEW,
            limits=(
                f"Rewrites tried: {', '.join(FAMILIES[ctx.budget])} (budget {ctx.budget.value}), "
                "each applied to every provable site at once. Catches only tests coupled to "
                "implementation details; tests that pin behaviour the statement leaves open "
                "(exact messages, float digits) need labelled candidates (C003)."
            ),
        )

    def _nothing(self, task: Task, ctx: CheckContext, files: list[str]) -> Finding:
        return make_finding(
            check_id=self.id,
            severity=Severity.INFO,
            task=task,
            title="No behaviour-preserving rewrite applies; C006 checked nothing for this task",
            detail="C006 rewrites the gold's Python files and found no site it could prove safe.",
            ev=Evidence(
                subject="gold",
                command=task.verifier,
                observed="no rewrite sites" if files else "no Python files in the gold overlay",
                exit_codes=(),
                timed_out=False,
                stdout_tail="",
                stderr_tail="",
                extra={"gold_python_files": ",".join(files)},
            ),
            ctx=ctx,
            confidence=Confidence.CONFIRMED,
            limits="Nothing was run for C006 on this task.",
        )
