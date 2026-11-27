"""C004 mutation probes: run small deliberate changes of the gold solution through the verifier.

A mutant that still passes ("survives") hints that the tests do not check that behaviour. Mutants
can be semantically equivalent to the gold (the known weakness of mutation testing), so survivors
are only ever severity info with confidence needs-review.

Equivalent-mutant filter (D-065): every survivor is probed (``aethens.checks.equivalence``). A
survivor the probe distinguishes from the gold is reported with the counterexample input; one that
behaved like the gold on every valid input tried is not reported, and is listed in C004's coverage
statement for the task instead; an inconclusive probe leaves the survivor reported as before.
"""

from __future__ import annotations

import ast
import difflib
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

from aethens.checks import equivalence
from aethens.checks.base import Check, CheckContext, evidence, hash_seed, make_finding, run_spec
from aethens.checks.mutation import Mutant, select_mutants
from aethens.models import Budget, Confidence, Coverage, Evidence, Finding, Severity, Task

MUTANT_CAP = {Budget.SMOKE: 5, Budget.STANDARD: 10, Budget.DEEP: 30}


class C004MutationProbes(Check):
    id = "C004"
    title = "Mutation probes"
    tier = "probe"
    cost_class = "high"

    def __init__(self, filter_equivalent: bool = True) -> None:
        self.filter_equivalent = filter_equivalent

    def cache_config(self) -> dict[str, str]:
        return {"filter_equivalent": "true" if self.filter_equivalent else "false"}

    def run(self, task: Task, ctx: CheckContext) -> list[Finding]:
        return self.run_with_coverage(task, ctx)[0]

    def run_with_coverage(
        self, task: Task, ctx: CheckContext
    ) -> tuple[list[Finding], list[Coverage]]:
        gold_dir = task.root / task.gold
        files = {
            p.relative_to(gold_dir).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(gold_dir.rglob("*.py"))
            if p.is_file()
        }
        cap = MUTANT_CAP[ctx.budget]
        mutants = select_mutants(files, seed=ctx.seed, salt=task.id, cap=cap)
        if not mutants:
            return [self._no_mutants(task, ctx, sorted(files))], []
        findings: list[Finding] = []
        filtered: list[tuple[Mutant, equivalence.Equivalence]] = []
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
                eq = equivalence.probe(task, m, ctx, hs) if self.filter_equivalent else None
                if eq is not None and eq.status == "equivalent":
                    filtered.append((m, eq))
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
                extra = {
                    "file": m.file,
                    "line": str(m.site.line),
                    "operator": m.site.operator,
                    "original_line": orig_line,
                    "diff": diff,
                    "PYTHONHASHSEED": hs,
                }
                detail = (
                    f"A deliberately changed copy of the gold solution "
                    f"({m.site.operator}: {m.site.description}) still passes the "
                    "verifier, so the tests may not check this behaviour. The mutant "
                    "may be semantically equivalent; review."
                )
                if eq is not None:
                    extra.update(_probe_extra(eq))
                    if eq.status == "distinguished":
                        detail += " " + _counterexample_sentence(eq)
                findings.append(
                    make_finding(
                        check_id=self.id,
                        severity=Severity.INFO,
                        task=task,
                        title=f"Mutant survived: {m.site.description} at {m.file}:{m.site.line}",
                        detail=detail,
                        ev=evidence(
                            f"mutant:{m.key}",
                            task,
                            [r],
                            "exit code 0: the mutant was accepted",
                            extra,
                        ),
                        ctx=ctx,
                        confidence=Confidence.NEEDS_REVIEW,
                        limits=(
                            f"{len(mutants)} mutants run (budget {ctx.budget.value}, cap {cap}). "
                            "Surviving mutants can be equivalent to the gold; killed mutants "
                            "do not prove the tests are strong. Survivors that behaved like the "
                            "gold on every generated input are not reported (see coverage); a "
                            "counterexample input may lie outside the task's intended inputs."
                        ),
                    )
                )
        counts = {
            "mutants_run": str(len(mutants)),
            "mutants_killed": str(killed),
            "mutants_filtered_as_equivalent": str(len(filtered)),
        }
        out = [
            replace(f, evidence=replace(f.evidence, extra={**f.evidence.extra, **counts}))
            for f in findings
        ]
        coverage = [self._coverage(task, filtered, counts)] if filtered else []
        return out, coverage

    def _coverage(
        self,
        task: Task,
        filtered: list[tuple[Mutant, equivalence.Equivalence]],
        counts: dict[str, str],
    ) -> Coverage:
        n = len(filtered)
        lowest = min(eq.valid_inputs for _m, eq in filtered)
        return Coverage(
            check_id=self.id,
            task_id=task.id,
            statement=(
                f"{n} surviving mutant{'s' if n != 1 else ''} not reported: each behaved exactly "
                f"like the gold on at least {lowest} valid inputs (the tests' own calls plus "
                "derived inputs), so it is probably an equivalent mutant. This is not a proof: "
                "a mutant that differs only on inputs that were not tried is hidden."
            ),
            stats={
                **counts,
                "likely_equivalent_mutants": ",".join(m.key for m, _eq in filtered),
                "likely_equivalent_descriptions": "; ".join(
                    f"{m.file}:{m.site.line} {m.site.description}" for m, _eq in filtered
                ),
                "method": "differential probe against the gold, see DECISIONS D-065",
            },
        )

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


def _probe_extra(eq: equivalence.Equivalence) -> dict[str, str]:
    extra = {"equivalence_probe": eq.status, "equivalence_probe_note": eq.reason}
    cx = eq.counterexample
    if cx:
        extra.update(
            {
                "counterexample_function": cx.get("function", ""),
                "counterexample_input": cx.get("args", ""),
                "counterexample_gold_result": cx.get("gold", ""),
                "counterexample_mutant_result": cx.get("mutant", ""),
                "counterexample_from_tests": "yes" if cx.get("from_tests") == "True" else "no",
            }
        )
    return extra


def _counterexample_sentence(eq: equivalence.Equivalence) -> str:
    cx = eq.counterexample
    where = (
        "an input the tests already use"
        if cx.get("from_tests") == "True"
        else "an input derived from the tests' inputs (it may be outside the intended inputs)"
    )
    return (
        f"It is not equivalent: on {where}, {cx.get('function', '?')}{cx.get('args', '')} "
        f"returns {cx.get('gold', '?')} for the gold but {cx.get('mutant', '?')} for the mutant."
    )
