import unittest

from avg import average


class TestAverage(unittest.TestCase):
    def test_tenths(self) -> None:
        # Compared with a tolerance, as the statement allows.
        self.assertAlmostEqual(average([0.1, 0.2, 0.3]), 0.2, places=9)

    def test_ints(self) -> None:
        self.assertAlmostEqual(average([1.0, 2.0]), 1.5)

    def test_single(self) -> None:
        self.assertAlmostEqual(average([-4.0]), -4.0)


if __name__ == "__main__":
    unittest.main()
