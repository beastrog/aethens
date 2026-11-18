"""C004 mutation probes: run small deliberate changes of the gold solution through the verifier.

A mutant that still passes ("survives") hints that the tests do not check that behaviour. Mutants
can be semantically equivalent to the gold (the known weakness of mutation testing), so survivors
are only ever severity info with confidence needs-review.
"""

from __future__ import annotations

import ast
import difflib
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

from aethens.checks.base import Check, CheckContext, evidence, hash_seed, make_finding, run_spec
from aethens.checks.mutation import select_mutants
from aethens.models import Budget, Confidence, Evidence, Finding, Severity, Task

MUTANT_CAP = {Budget.SMOKE: 5, Budget.STANDARD: 10, Budget.DEEP: 30}


class C004MutationProbes(Check):
    id = "C004"
    title = "Mutation probes"
    tier = "probe"
    cost_class = "high"

    def run(self, task: Task, ctx: CheckContext) -> list[Finding]:
        gold_dir = task.root / task.gold
        files = {
            p.relative_to(gold_dir).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(gold_dir.rglob("*.py"))
            if p.is_file()
        }
        cap = MUTANT_CAP[ctx.budget]
        mutants = select_mutants(files, seed=ctx.seed, salt=task.id, cap=cap)
        if not mutants:
            return [self._no_mutants(task, ctx, sorted(files))]
        findings: list[Finding] = []
        killed = 0
        with tempfile.TemporaryDirectory(prefix="aethens-mutant-") as tmp:
            for n, m in enumerate(mutants):
                overlay = Path(tmp) / f"m{n}"
                shutil.copytree(gold_dir, overlay, symlinks=False)
                (overlay / m.file).write_text(m.source, encoding="utf-8")
                hs = str(hash_seed(ctx.seed, task.id, self.id, m.key))
                r = ctx.runner.run(run_spec(task, overlay, {"PYTHONHASHSEED": hs}))
                if not r.passed:
                    killed += 1
                    continue
                original = ast.unparse(ast.parse(files[m.file])).splitlines()
                diff = "\n".join(
                    difflib.unified_diff(
                        original,
                        m.source.splitlines(),
                        fromfile=f"gold/{m.file}",
                        tofile=f"mutant/{m.file}",
                        lineterm="",
                        n=1,
                    )
                )
                src_lines = files[m.file].splitlines()
                orig_line = src_lines[m.site.line - 1].strip() if m.site.line else ""
                findings.append(
                    make_finding(
                        check_id=self.id,
                        severity=Severity.INFO,
                        task=task,
                        title=f"Mutant survived: {m.site.description} at {m.file}:{m.site.line}",
                        detail=(
                            f"A deliberately changed copy of the gold solution "
                            f"({m.site.operator}: {m.site.description}) still passes the "
                            "verifier, so the tests may not check this behaviour. The mutant "
                            "may be semantically equivalent; review."
                        ),
                        ev=evidence(
                            f"mutant:{m.key}",
                            task,
                            [r],
                            "exit code 0: the mutant was accepted",
                            {
                                "file": m.file,
                                "line": str(m.site.line),
                                "operator": m.site.operator,
                                "original_line": orig_line,
                                "diff": diff,
                                "PYTHONHASHSEED": hs,
                            },
                        ),
                        ctx=ctx,
                        confidence=Confidence.NEEDS_REVIEW,
                        limits=(
                            f"{len(mutants)} mutants run (budget {ctx.budget.value}, cap {cap}). "
                            "Surviving mutants can be equivalent to the gold; killed mutants "
                            "do not prove the tests are strong."
                        ),
                    )
                )
        counts = {"mutants_run": str(len(mutants)), "mutants_killed": str(killed)}
        return [
            replace(f, evidence=replace(f.evidence, extra={**f.evidence.extra, **counts}))
            for f in findings
        ]

    def _no_mutants(self, task: Task, ctx: CheckContext, files: list[str]) -> Finding:
        observed = (
            "no Python files in the gold overlay"
            if not files
            else f"no mutation sites in {', '.join(files)}"
        )
        return make_finding(
            check_id=self.id,
            severity=Severity.INFO,
            task=task,
            title="No mutants could be generated; C004 checked nothing for this task",
            detail="C004 mutates the gold solution's Python files and found nothing to mutate.",
            ev=Evidence(
                subject="gold",
                command=task.verifier,
                observed=observed,
                exit_codes=(),
                timed_out=False,
                stdout_tail="",
                stderr_tail="",
                extra={"gold_python_files": ",".join(files)},
            ),
            ctx=ctx,
            confidence=Confidence.CONFIRMED,
            limits="Nothing was run for C004 on this task.",
        )
