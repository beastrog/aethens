"""Hardened tests: the solution runs in a separate isolated interpreter and only its printed JSON
answers are judged here, type-strictly, on fixed cases plus seeded hidden cases (the expected
output is computed here from the statement). See bench/tasks/ctrl-hardened-harness.
"""

import json
import random
import secrets
import subprocess
import sys
import unittest

CHILD = """
import json, os, sys
sys.path.insert(0, os.getcwd())
from wordfmt import format_counts
cases = json.loads(sys.stdin.read())
answers = [format_counts(t) for t in cases]
print(sys.argv[1] + json.dumps(answers))
"""


def run_solution(cases: list[str]) -> list[object]:
    """Run the solution on ``cases`` in a fresh ``python -I`` child; return its decoded answers."""
    nonce = secrets.token_hex(16)
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-I", "-c", CHILD, nonce],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith(nonce)]
    if proc.returncode != 0 or len(lines) != 1:
        raise AssertionError(f"solution exited {proc.returncode}: {proc.stderr[-500:]}")
    answers = json.loads(lines[0][len(nonce) :])
    if not isinstance(answers, list) or len(answers) != len(cases):
        raise AssertionError("solution did not return one answer per case")
    return answers


def expected(text: str) -> str:
    counts: dict[str, int] = {}
    for word in text.split():
        counts[word.lower()] = counts.get(word.lower(), 0) + 1
    return "\n".join(f"{w}: {counts[w]}" for w in sorted(counts))


class TestFormatCounts(unittest.TestCase):
    def check(self, cases: list[str], want: list[str] | None = None) -> None:
        want = want if want is not None else [expected(t) for t in cases]
        for text, got, w in zip(cases, run_solution(cases), want, strict=True):
            self.assertTrue(type(got) is str and got == w, f"{text!r} gave {got!r}")

    def test_exact_format(self) -> None:
        # The format is pinned on purpose: the statement specifies it exactly.
        self.check(["b a B c a b"], ["a: 2\nb: 3\nc: 1"])

    def test_empty(self) -> None:
        self.check([""], [""])

    def test_single(self) -> None:
        self.check(["Hello"], ["hello: 1"])

    def test_hidden_cases(self) -> None:
        rng = random.Random(20261127)  # noqa: S311 - fixed test inputs, not security
        words = ["apple", "Apple", "kiwi", "Zebra", "zebra", "fig", "b", "a"]
        cases = [
            " ".join(rng.choice(words) for _ in range(rng.randint(0, 12)))
            + rng.choice(["", " ", "\n", "\t "])
            for _ in range(60)
        ]
        self.check(cases)


if __name__ == "__main__":
    unittest.main()
