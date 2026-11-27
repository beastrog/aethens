import unittest

from solution import add


class TestAdd(unittest.TestCase):
    def test_small(self) -> None:
        self.assertEqual(add(2, 3), 5)

    def test_negative(self) -> None:
        self.assertEqual(add(-4, 1), -3)

    def test_zero(self) -> None:
        self.assertEqual(add(0, 0), 0)


if __name__ == "__main__":
    unittest.main()
