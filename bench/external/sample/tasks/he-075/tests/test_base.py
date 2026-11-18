# Converted by bench/external/convert.py from HumanEval base tests (MIT). HumanEval: github.com/openai/human-eval, Copyright (c) OpenAI.
# Task HumanEval/75. Do not edit by hand; re-run the converter.

import unittest

import solution as _solution

globals().update({k: v for k, v in vars(_solution).items() if not k.startswith("__")})
candidate = _solution.is_multiply_prime



class TestBase(unittest.TestCase):
    def test_000(self):
        assert candidate(5) == False

    def test_001(self):
        assert candidate(30) == True

    def test_002(self):
        assert candidate(8) == True

    def test_003(self):
        assert candidate(10) == False

    def test_004(self):
        assert candidate(125) == True

    def test_005(self):
        assert candidate(3 * 5 * 7) == True

    def test_006(self):
        assert candidate(3 * 6 * 7) == False

    def test_007(self):
        assert candidate(9 * 9 * 9) == False

    def test_008(self):
        assert candidate(11 * 9 * 9) == False

    def test_009(self):
        assert candidate(11 * 13 * 7) == True

