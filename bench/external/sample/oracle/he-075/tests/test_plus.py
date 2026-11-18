# Converted by bench/external/convert.py from HumanEval+ tests (Apache-2.0). HumanEval+: EvalPlus, huggingface.co/datasets/evalplus/humanevalplus.
# Task HumanEval/75. Do not edit by hand; re-run the converter.
import unittest

import solution as _solution

globals().update({k: v for k, v in vars(_solution).items() if not k.startswith("__")})
candidate = _solution.is_multiply_prime

import math


def is_floats(x) -> bool:
    # stdlib replacement for EvalPlus's numpy-based helper (see bench/external/convert.py)
    if isinstance(x, float):
        return True
    if isinstance(x, (list, tuple)):
        return all(isinstance(i, float) for i in x)
    return False


def _allclose(out, exp, atol):
    if isinstance(exp, (list, tuple)):
        assert isinstance(out, (list, tuple)) and len(out) == len(exp)
        for o, e in zip(out, exp):
            _allclose(o, e, atol)
        return
    o, e = float(out), float(exp)
    if math.isnan(o) or math.isnan(e):
        assert math.isnan(o) and math.isnan(e)
        return
    if math.isinf(o) or math.isinf(e):
        assert o == e
        return
    assert abs(o - e) <= atol + 1e-07 * abs(e)


def assertion(out, exp, atol):
    exact_match = out == exp

    if atol == 0 and is_floats(exp):
        atol = 1e-6
    if not exact_match and atol != 0:
        _allclose(out, exp, atol)
    else:
        assert exact_match


def check(candidate):
    inputs = [[5], [30], [8], [10], [33], [49], [77], [91], [99], [6], [90], [98], [25], [21], [48], [20], [22], [32], [26], [78], [19], [47], [31], [29], [-98], [-37], [-38], [28], [18], [23], [-92], [-2], [57], [-99], [58], [56], [-1], [92], [1], [-80], [34], [-75], [-100], [-95], [16], [-94], [17], [59], [-7], [93], [-82], [-15], [-81], [-96], [-74], [2], [3], [7], [97], [42], [-101], [43], [44], [45], [-56], [60], [-55], [46], [62], [55], [61], [41], [40], [-57], [63], [-102], [52], [-72], [-97], [94], [12], [89], [53], [0], [64], [-58], [65], [-71], [95], [35], [-70], [96], [-59], [15], [-33]]
    results = [False, True, True, False, False, False, False, False, True, False, False, True, False, False, False, True, False, False, False, True, False, False, False, False, False, False, False, True, True, False, False, False, False, False, False, False, False, True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, True, False, False, True, True, False, False, False, False, False, False, False, False, False, False, True, False, True, False, False, False, True, False, False, False, False, False, False, False, False, False, False, False, False, False, False]
    for i, (inp, exp) in enumerate(zip(inputs, results)):
        assertion(candidate(*inp), exp, 0)


class TestPlus(unittest.TestCase):
    def test_plus(self):
        check(candidate)
