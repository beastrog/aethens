import unittest

from avg import average


class TestAverage(unittest.TestCase):
    def test_tenths(self) -> None:
        # PLANTED DEFECT: pins the exact float the gold's summation order produces.
        self.assertEqual(average([0.1, 0.2, 0.3]), 0.20000000000000004)

    def test_ints(self) -> None:
        self.assertEqual(average([1.0, 2.0]), 1.5)


if __name__ == "__main__":
    unittest.main()
