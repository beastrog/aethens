import unittest

from temps import celsius_to_f


class TestTemps(unittest.TestCase):
    def test_freezing(self) -> None:
        self.assertEqual(celsius_to_f(0), 32)

    def test_boiling(self) -> None:
        self.assertEqual(celsius_to_f(100), 212)


if __name__ == "__main__":
    unittest.main()
