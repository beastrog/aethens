import inspect
import unittest

from pct import clamp_pct


class TestPct(unittest.TestCase):
    def test_values(self) -> None:
        self.assertEqual([clamp_pct(-5), clamp_pct(50), clamp_pct(150)], [0, 50, 100])
        self.assertEqual(clamp_pct(5, low=10), 10)

    def test_signature_is_public_api(self) -> None:
        # Introspection that the statement requires: parameter names, kinds and defaults.
        params = inspect.signature(clamp_pct).parameters
        self.assertEqual(list(params), ["value", "low", "high"])
        self.assertEqual(params["low"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual((params["low"].default, params["high"].default), (0, 100))
