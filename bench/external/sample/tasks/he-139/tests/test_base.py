# Converted by bench/external/convert.py from HumanEval base tests (MIT). HumanEval: github.com/openai/human-eval, Copyright (c) OpenAI.
# Task HumanEval/139. Do not edit by hand; re-run the converter.

import unittest

import solution as _solution

globals().update({k: v for k, v in vars(_solution).items() if not k.startswith("__")})
candidate = _solution.special_factorial



class TestBase(unittest.TestCase):
    def test_000(self):
        assert candidate(4) == 288, 'Test 4'

    def test_001(self):
        assert candidate(5) == 34560, 'Test 5'

    def test_002(self):
        assert candidate(7) == 125411328000, 'Test 7'

    def test_003(self):
        assert candidate(1) == 1, 'Test 1'

