# Converted by bench/external/convert.py from HumanEval base tests (MIT). HumanEval: github.com/openai/human-eval, Copyright (c) OpenAI.
# Task HumanEval/2. Do not edit by hand; re-run the converter.

import unittest

import solution as _solution

globals().update({k: v for k, v in vars(_solution).items() if not k.startswith("__")})
candidate = _solution.truncate_number


METADATA = {'author': 'jt', 'dataset': 'test'}


class TestBase(unittest.TestCase):
    def test_000(self):
        assert candidate(3.5) == 0.5

    def test_001(self):
        assert abs(candidate(1.33) - 0.33) < 1e-06

    def test_002(self):
        assert abs(candidate(123.456) - 0.456) < 1e-06

