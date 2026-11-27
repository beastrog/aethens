"""Download the public benchmark exports used by the real-world audits, pinned by revision and
sha256, and convert the Parquet files to JSONL for ``aethens import``.

Usage: uv run --with pyarrow python bench/real/fetch_real.py [NAME ...]

This is the only part of the real-world audits that uses the network (besides `docker pull` of
the task images). Licences are recorded in bench/LICENSES.md. Nothing downloaded is committed:
bench/real/data/ is gitignored.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
HF = "https://huggingface.co/datasets"

# name: (url, sha256 of the downloaded file, output jsonl name)
SOURCES = {
    "mbppplus": (
        f"{HF}/evalplus/mbppplus/resolve/b2d74c91837c3f2a20c1299ae98133cbe7cfa077/"
        "data/test-00000-of-00001-d5781c9c51e02795.parquet",
        "dc20030b3788fccf617444edcb34138ef13d7e4fafd17bfcb8c1279dbb12399b",
        "mbppplus.jsonl",
    ),
    "swebench-verified": (
        f"{HF}/SWE-bench/SWE-bench_Verified/resolve/78f471bf655a3137b2e8a75af1501690ec009ec3/"
        "data/test-00000-of-00001.parquet",
        "030cfd7f2a704c4c0226e7f104c725a3b41230b1d3517f9c915ad7ea5be3fa25",
        "swebench-verified.jsonl",
    ),
    "bigcodebench": (
        f"{HF}/bigcode/bigcodebench/resolve/b74c0d0bf70d2c0bc459be537895cca163007f1a/"
        "data/v0.1.4-00000-of-00001.parquet",
        "d9a4965821c9507ebdfb551c288656b2d5fe553234f5183044333ca8a4018267",
        "bigcodebench-v0.1.4.jsonl",
    ),
}


def fetch(name: str) -> Path:
    url, sha, out_name = SOURCES[name]
    raw = DATA / (out_name + ".parquet")
    if not (raw.exists() and hashlib.sha256(raw.read_bytes()).hexdigest() == sha):
        with urllib.request.urlopen(url, timeout=300) as resp:  # noqa: S310 - pinned https URL
            body = resp.read()
        digest = hashlib.sha256(body).hexdigest()
        if digest != sha:
            raise SystemExit(f"fetch_real: {name}: sha256 {digest} != expected {sha}")
        raw.write_bytes(body)
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise SystemExit(
            "fetch_real: needs pyarrow: uv run --with pyarrow python bench/real/fetch_real.py"
        ) from exc
    rows = pq.read_table(raw).to_pylist()
    out = DATA / out_name
    with out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    print(f"fetch_real: {name}: {len(rows)} records -> {out}")
    return out


def main(argv: list[str] | None = None) -> int:
    names = (argv if argv is not None else sys.argv[1:]) or list(SOURCES)
    DATA.mkdir(parents=True, exist_ok=True)
    for name in names:
        if name not in SOURCES:
            raise SystemExit(f"fetch_real: unknown source {name!r}; known: {sorted(SOURCES)}")
        fetch(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
