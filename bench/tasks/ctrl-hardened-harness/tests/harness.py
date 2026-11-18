"""Hardened verifier: the candidate runs in a separate isolated interpreter and only its printed
JSON answers are judged, here, against a reference on seeded random inputs plus edge cases.

The candidate cannot change this process's exit code, its test framework, or its comparisons.
"""

import json
import math
import random
import secrets
import subprocess
import sys

CHILD = """
import json, os, sys
sys.path.insert(0, os.getcwd())
from numtheory import gcd
cases = json.loads(sys.stdin.read())
answers = [gcd(a, b) for a, b in cases]
if not all(type(x) is int for x in answers):
    raise SystemExit("non-int answer")
print(sys.argv[1] + json.dumps(answers))
"""


def main() -> int:
    rng = random.Random(20261118)
    cases = [(0, 0), (0, 7), (7, 0), (1, 1), (12, 18), (17, 5)]
    cases += [(rng.randrange(0, 10**6), rng.randrange(0, 10**6)) for _ in range(200)]
    nonce = secrets.token_hex(16)
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-I", "-c", CHILD, nonce],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith(nonce)]
    if proc.returncode != 0 or len(lines) != 1:
        print(f"FAIL: candidate exited {proc.returncode} without one answer line", proc.stderr[-500:])
        return 1
    try:
        answers = json.loads(lines[0][len(nonce):])
    except ValueError:
        print("FAIL: answers are not JSON")
        return 1
    expected = [math.gcd(a, b) for a, b in cases]
    if answers != expected:
        bad = next(i for i, (x, y) in enumerate(zip(answers, expected)) if x != y) if len(answers) == len(expected) else -1
        print(f"FAIL: wrong answer (first mismatch index {bad})")
        return 1
    print(f"OK: {len(cases)} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main())
