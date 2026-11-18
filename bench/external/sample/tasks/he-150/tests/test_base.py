# Converted by bench/external/convert.py from HumanEval base tests (MIT). HumanEval: github.com/openai/human-eval, Copyright (c) OpenAI.
# Task HumanEval/150. Do not edit by hand; re-run the converter.

import unittest

import solution as _solution

globals().update({k: v for k, v in vars(_solution).items() if not k.startswith("__")})
candidate = _solution.x_or_y



class TestBase(unittest.TestCase):
    def test_000(self):
        assert candidate(7, 34, 12) == 34

    def test_001(self):
        assert candidate(15, 8, 5) == 5

    def test_002(self):
        assert candidate(3, 33, 5212) == 33

    def test_003(self):
        assert candidate(1259, 3, 52) == 3

    def test_004(self):
        assert candidate(7919, -1, 12) == -1

    def test_005(self):
        assert candidate(3609, 1245, 583) == 583

    def test_006(self):
        assert candidate(91, 56, 129) == 129

    def test_007(self):
        assert candidate(6, 34, 1234) == 1234

    def test_008(self):
        assert candidate(1, 2, 0) == 0

    def test_009(self):
        assert candidate(2, 2, 0) == 2

