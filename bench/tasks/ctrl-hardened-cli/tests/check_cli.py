"""Hardened CLI verifier: runs totals.py as an isolated child on seeded random input and judges
its standard output here. The exit code of the child alone is never trusted."""

import random
import subprocess
import sys


def main() -> int:
    rng = random.Random(1118)
    rows = [[], [5], [-3, 3], [10**12, 1]]
    rows += [[rng.randrange(-1000, 1000) for _ in range(rng.randrange(0, 8))] for _ in range(100)]
    text = "".join(" ".join(map(str, r)) + "\n" for r in rows)
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-I", "totals.py"],
        input=text,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    want = "".join(f"{sum(r)}\n" for r in rows)
    if proc.returncode != 0 or proc.stdout != want:
        print(f"FAIL: exit {proc.returncode}; output differs from the reference")
        print(proc.stderr[-500:])
        return 1
    print(f"OK: {len(rows)} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
