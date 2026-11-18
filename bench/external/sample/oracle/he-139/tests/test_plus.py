# Converted by bench/external/convert.py from HumanEval+ tests (Apache-2.0). HumanEval+: EvalPlus, huggingface.co/datasets/evalplus/humanevalplus.
# Task HumanEval/139. Do not edit by hand; re-run the converter.
import unittest

import solution as _solution

globals().update({k: v for k, v in vars(_solution).items() if not k.startswith("__")})
candidate = _solution.special_factorial

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


def ref_func(n):
    fac, ans = (1, 1)
    for i in range(2, n + 1):
        fac *= i
        ans *= fac
    return ans

def check(candidate):
    inputs = [[4], [5], [7], [1], [2], [3], [6], [8], [10], [13], [20], [50], [15], [12], [11], [22], [14], [9], [21], [51], [30], [29], [32], [49], [77], [52], [23], [48], [19], [33], [16], [53], [27], [34], [35], [17], [28], [26], [47], [74], [24], [36], [95], [18], [31], [45], [37], [38], [46], [78], [39], [73], [75], [79], [80], [72], [81], [25], [76], [96], [44], [94], [40], [43], [93], [71], [42], [83], [41], [70], [97], [84], [54], [85], [92], [91], [55], [82], [69], [98], [86], [56], [99], [57], [100], [101], [58], [87], [68], [62], [59], [102], [103], [60], [88], [67], [66], [104], [63], [200], [500], [199], [198], [499], [197], [497], [501], [498], [502], [496], [201], [503], [495], [493], [196], [492], [195], [202], [504], [505], [203], [491], [204], [105], [90], [494], [89]]
    for i, inp in enumerate(inputs):
        assertion(candidate(*inp), ref_func(*inp), 0)


class TestPlus(unittest.TestCase):
    def test_plus(self):
        check(candidate)
