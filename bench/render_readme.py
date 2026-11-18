"""Insert the bench numbers from bench/results.json into README.md between markers.

README numbers must never be typed by hand (AGENTS.md rule 6). Run after `make bench`:
    python bench/render_readme.py
tests/test_repo_files.py fails if the README block is stale.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
START, END = "<!-- bench:start -->", "<!-- bench:end -->"


def render_block(results: dict[str, Any]) -> str:
    m = results["metrics"]
    lines = [
        START,
        f"Generated from `bench/results.json` (aethens {results['tool_version']}, seed "
        f"{results['seed']}, budget {results['budget']}) by `bench/render_readme.py`.",
        "",
        f"Bench: {results['tasks']} self-authored tasks, {results['controls']} clean controls and "
        f"{results['defective']} with planted defects.",
        "",
        "| metric | value |",
        "|---|---|",
        f"| precision (error/warning findings) | {m['precision']} |",
        f"| recall (planted defects found) | {m['recall']} ({m['found']}/{m['planted']}) |",
        f"| false positives on controls | {m['false_positives']} |",
        f"| unexpected error/warning findings on defective tasks | {m['unexpected_findings']} |",
        f"| info findings on controls | {m['info_on_controls']} |",
        "",
        "| defect class | found / planted |",
        "|---|---|",
    ]
    for cls, v in m["per_class"].items():
        lines.append(f"| {cls} | {v['found']}/{v['planted']} |")
    lines += ["", "| check | found / planted | false positives |", "|---|---|---|"]
    for chk, v in m["per_check"].items():
        lines.append(f"| {chk} | {v['found']}/{v['planted']} | {v['false_positives']} |")
    lines += ["", "Known misses in this run:", ""]
    if m["known_misses"]:
        for miss in m["known_misses"]:
            lines.append(f"- `{miss['task']}` ({miss['class']}, expected {miss['check']})")
    else:
        lines.append("- none")
    hack = results.get("reward_hack")
    if hack:
        lines += [
            "",
            "Reward hacking (C007), scored separately: each task lists the probe categories that "
            "should get through its verifier (labels in bench/manifest.yaml).",
            "",
            f"Overall: recall {hack['recall']} ({hack['found']}/{hack['labelled']}), precision "
            f"{hack['precision']}, false positives {hack['false_positives']}.",
            "",
            "| exploit category | found / labelled | false positives |",
            "|---|---|---|",
        ]
        for cat, v in hack["per_category"].items():
            lines.append(f"| {cat} | {v['found']}/{v['labelled']} | {v['false_positives']} |")
        if hack["misses"]:
            lines += [
                "",
                "Reward-hack misses: "
                + ", ".join(f"`{m['task']}` ({m['category']})" for m in hack["misses"]),
            ]
    lines.append(END)
    return "\n".join(lines)


def main() -> int:
    results = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    readme_path = HERE.parent / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    if START not in readme or END not in readme:
        print("README.md has no bench markers", file=sys.stderr)
        return 2
    head, rest = readme.split(START, 1)
    _, tail = rest.split(END, 1)
    readme_path.write_text(head + render_block(results) + tail, encoding="utf-8")
    print("README.md bench block updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
