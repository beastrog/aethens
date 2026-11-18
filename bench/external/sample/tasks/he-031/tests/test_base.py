# Converted by bench/external/convert.py from HumanEval base tests (MIT). HumanEval: github.com/openai/human-eval, Copyright (c) OpenAI.
# Task HumanEval/31. Do not edit by hand; re-run the converter.

import unittest

import solution as _solution

globals().update({k: v for k, v in vars(_solution).items() if not k.startswith("__")})
candidate = _solution.is_prime


METADATA = {}


class TestBase(unittest.TestCase):
    def test_000(self):
        assert candidate(6) == False

    def test_001(self):
        assert candidate(101) == True

    def test_002(self):
        assert candidate(11) == True

    def test_003(self):
        assert candidate(13441) == True

    def test_004(self):
        assert candidate(61) == True

    def test_005(self):
        assert candidate(4) == False

    def test_006(self):
        assert candidate(1) == False

    def test_007(self):
        assert candidate(5) == True

    def test_008(self):
        assert candidate(11) == True

    def test_009(self):
        assert candidate(17) == True

    def test_010(self):
        assert candidate(5 * 17) == False

    def test_011(self):
        assert candidate(11 * 7) == False

    def test_012(self):
        assert candidate(13441 * 19) == False

