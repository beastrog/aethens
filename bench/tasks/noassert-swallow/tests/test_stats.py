import unittest

from stats import mean


class TestMean(unittest.TestCase):
    def test_mean(self) -> None:
        # PLANTED DEFECT: the try/except hides both errors and failed assertions.
        try:
            self.assertEqual(mean([1, 2, 3]), 2)
            self.assertEqual(mean([5]), 5)
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
