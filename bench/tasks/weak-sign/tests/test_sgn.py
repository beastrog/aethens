import unittest

from sgn import sign


class TestSign(unittest.TestCase):
    # PLANTED DEFECT: zero is never tested.
    def test_positive(self) -> None:
        self.assertEqual(sign(7), 1)

    def test_negative(self) -> None:
        self.assertEqual(sign(-2), -1)


if __name__ == "__main__":
    unittest.main()
