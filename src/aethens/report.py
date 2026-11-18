"""Render a Report as JSON (aethens-report/v2) or Markdown (sized for a PR comment)."""

from __future__ import annotations

import json
from collections import Counter

from aethens.models import Finding, Report, Severity

_MD_TAIL = 1500


def render_json(report: Report) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=False)


def _esc(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _fence(text: str) -> str:
    text = text if len(text) <= _MD_TAIL else "[...]\n" + text[-_MD_TAIL:]
    return "```text\n" + text.replace("```", "``\u200b`").rstrip() + "\n```"


def _finding_md(f: Finding) -> list[str]:
    ev = f.evidence
    lines = [
        f"<details><summary><b>{f.severity.value}</b> {f.check_id} "
        f"<code>{f.task_id}</code>: {_esc(f.title)}</summary>",
        "",
        _esc(f.detail),
        "",
        f"- Observed: {_esc(ev.observed)}",
        f"- Subject: `{ev.subject}`; confidence: `{f.confidence.value}`; seed: `{f.seed}`",
        f"- Command: `{_esc(' '.join(ev.command))}`",
        f"- Limits: {_esc(f.limits)}",
        "",
        "Reproduce:",
        "",
        "```sh",
        f.repro,
        "```",
    ]
    if "diff" in ev.extra:
        lines += ["", "Mutant diff:", "", "```diff", ev.extra["diff"], "```"]
    if ev.stderr_tail.strip():
        lines += ["", "stderr (tail):", "", _fence(_esc_block(ev.stderr_tail))]
    if ev.stdout_tail.strip():
        lines += ["", "stdout (tail):", "", _fence(_esc_block(ev.stdout_tail))]
    lines += ["", "</details>", ""]
    return lines


def _esc_block(text: str) -> str:
    return text.replace("|", "\\|")


def render_markdown(report: Report) -> str:
    counts = Counter(f.severity for f in report.findings)
    out = [
        "## Aethens report",
        "",
        f"Tool `aethens {report.tool_version}` · Budget: `{report.budget.value}` · "
        f"Seed: `{report.seed}` · Checks run: {', '.join(report.checks_run)} · "
        f"Tasks: {len(report.task_ids)} · Duration: {report.duration_s:.1f}s",
        "",
        f"**{counts[Severity.ERROR]} error, {counts[Severity.WARNING]} warning, "
        f"{counts[Severity.INFO]} info**",
        "",
    ]
    if not report.findings:
        out += [
            "No findings. This only means the checks listed above found nothing at this budget "
            "and seed; it is not a guarantee about the verifier.",
            "",
        ]
        return "\n".join(out + _coverage_md(report))
    out += ["| severity | check | task | title |", "|---|---|---|---|"]
    order = sorted(report.findings, key=lambda f: (-f.severity.rank, f.task_id, f.check_id, f.id))
    for f in order:
        out.append(f"| {f.severity.value} | {f.check_id} | {_esc(f.task_id)} | {_esc(f.title)} |")
    out.append("")
    for f in order:
        out += _finding_md(f)
    out += [
        "Info findings (C004 surviving mutants) may be semantically equivalent to the gold "
        "solution; review before acting. Findings rely on what was run; see each finding's limits.",
        "",
    ]
    return "\n".join(out + _coverage_md(report))


def _coverage_md(report: Report) -> list[str]:
    if not report.coverage:
        return []
    out = ["### Coverage (what was established where nothing was found)", ""]
    out += ["| check | task | statement |", "|---|---|---|"]
    for c in sorted(report.coverage, key=lambda c: (c.task_id, c.check_id)):
        out.append(f"| {c.check_id} | {_esc(c.task_id)} | {_esc(c.statement)} |")
    out.append("")
    return out
