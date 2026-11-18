# Converted by bench/external/convert.py from HumanEval base tests (MIT). HumanEval: github.com/openai/human-eval, Copyright (c) OpenAI.
# Task HumanEval/59. Do not edit by hand; re-run the converter.

import unittest

import solution as _solution

globals().update({k: v for k, v in vars(_solution).items() if not k.startswith("__")})
candidate = _solution.largest_prime_factor


METADATA = {}


class TestBase(unittest.TestCase):
    def test_000(self):
        assert candidate(15) == 5

    def test_001(self):
        assert candidate(27) == 3

    def test_002(self):
        assert candidate(63) == 7

    def test_003(self):
        assert candidate(330) == 11

    def test_004(self):
        assert candidate(13195) == 29

