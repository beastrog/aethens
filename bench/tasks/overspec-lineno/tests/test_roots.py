import unittest
import warnings

from roots import checked_sqrt


class TestRoots(unittest.TestCase):
    def test_positive(self) -> None:
        self.assertEqual(checked_sqrt(9.0), 3.0)

    # PLANTED DEFECT: pins the line number the warning comes from, an accident of the gold's layout.
    def test_negative_warns(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.assertEqual(checked_sqrt(-1.0), 0.0)
        self.assertEqual(len(caught), 1)
        self.assertIs(caught[0].category, RuntimeWarning)
        self.assertEqual(caught[0].lineno, 8)
