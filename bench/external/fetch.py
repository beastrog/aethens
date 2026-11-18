"""Download the public datasets used by the external bench, pinned by URL and sha256.

Usage: python bench/external/fetch.py

This is the ONLY part of the external bench that uses the network. Tests and `make check` never
call it; they use the small vendored sample in bench/external/sample/. Licences are recorded in
bench/LICENSES.md (checked on 2026-11-18).
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"  # gitignored

SOURCES = {
    # OpenAI HumanEval, MIT licence, github.com/openai/human-eval at commit b9453e8f.
    "HumanEval.jsonl.gz": (
        "https://raw.githubusercontent.com/openai/human-eval/"
        "b9453e8f1865df0a0057a1383767caa400acfbcf/data/HumanEval.jsonl.gz",
        "b796127e635a67f93fb35c04f4cb03cf06f38c8072ee7cee8833d7bee06979ef",
    ),
    # EvalPlus HumanEval+, Apache-2.0, huggingface.co/datasets/evalplus/humanevalplus at d32357cf.
    "HumanEvalPlus.jsonl": (
        "https://huggingface.co/datasets/evalplus/humanevalplus/resolve/"
        "d32357cf319e50e9c8d8dab5ea876c72b0fd321b/test.jsonl",
        "908377f1daf28dcb36846db73a5662b2e05a9907407c2696c89ad9d3b0b04492",
    ),
}


def fetch(name: str, url: str, sha256: str) -> None:
    dest = DATA / name
    if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest() == sha256:
        print(f"fetch: {name} already present")
        return
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 - pinned https URL
        body = resp.read()
    digest = hashlib.sha256(body).hexdigest()
    if digest != sha256:
        raise SystemExit(f"fetch: {name}: sha256 {digest} != expected {sha256}")
    dest.write_bytes(body)
    print(f"fetch: {name} ({len(body)} bytes) ok")


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    for name, (url, sha) in SOURCES.items():
        fetch(name, url, sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
