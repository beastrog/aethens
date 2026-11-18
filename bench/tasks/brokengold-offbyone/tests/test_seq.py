import unittest

from seq import count_up


class TestCountUp(unittest.TestCase):
    def test_three(self) -> None:
        self.assertEqual(count_up(3), [1, 2, 3])

    def test_zero(self) -> None:
        self.assertEqual(count_up(0), [])


if __name__ == "__main__":
    unittest.main()
