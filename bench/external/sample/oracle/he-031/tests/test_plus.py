# Converted by bench/external/convert.py from HumanEval+ tests (Apache-2.0). HumanEval+: EvalPlus, huggingface.co/datasets/evalplus/humanevalplus.
# Task HumanEval/31. Do not edit by hand; re-run the converter.
import unittest

import solution as _solution

globals().update({k: v for k, v in vars(_solution).items() if not k.startswith("__")})
candidate = _solution.is_prime

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
    inputs = [[6], [101], [11], [13441], [61], [4], [1], [5], [17], [85], [77], [255379], [-5], [0], [2], [31], [40], [103], [199], [1009], [8999], [1234567], [9000], [32], [9001], [-1], [39], [1234566], [-4], [9002], [-6], [102], [200], [56], [38], [37], [1010], [1234568], [1008], [33], [35], [64], [63], [1234564], [34], [1011], [1234569], [197], [-3], [8998], [57], [28], [-2], [3], [1234563], [36], [9003], [30], [1234570], [-29], [9004], [-7], [16], [1012], [55], [-30], [-17], [7937], [34981], [42043], [-10], [10000000029], [123456789], [-9], [-18], [10000000028], [42042], [12], [123456790], [-16], [10000000030], [-15], [7939], [7938], [7936], [13], [7935], [23], [42044], [-11], [-14], [7934], [7933], [10000000027], [14], [34980], [24], [15], [42041], [-8], [7940], [70], [-13], [-40], [18], [-12], [-47], [-49], [34979], [42040], [34978], [-41], [-42], [22], [25], [10], [67], [-39], [26], [62], [-48], [66], [-20], [7941], [-50], [-37], [-21], [-28], [-101], [-255379], [-2147483648], [9999991], [7567216125], [34982], [34977], [123456788], [123456791], [-91], [93], [10000000031], [-90], [92], [34983], [-92], [-89], [-78], [82], [-76], [45], [10000000032], [42045], [44], [46], [-100], [19], [72], [91], [-38], [-75]]
    results = [False, True, True, True, True, False, False, True, True, False, False, False, False, False, True, True, False, True, True, True, True, False, False, False, True, False, False, False, False, False, False, False, False, False, False, True, False, False, False, False, False, False, False, False, False, False, False, True, False, False, False, False, False, True, False, False, False, False, False, False, False, False, False, False, False, False, False, True, True, True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, True, False, True, False, False, False, False, True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, True, False, False, False, False, True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, True, False, False, False, False]
    for i, (inp, exp) in enumerate(zip(inputs, results)):
        assertion(candidate(*inp), exp, 0)


class TestPlus(unittest.TestCase):
    def test_plus(self):
        check(candidate)
