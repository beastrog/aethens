import unittest

from clamp import clamp


class TestClamp(unittest.TestCase):
    def test_inside(self) -> None:
        self.assertEqual(clamp(5, 0, 10), 5)

    def test_below(self) -> None:
        self.assertEqual(clamp(-3, 0, 10), 0)

    def test_above(self) -> None:
        self.assertEqual(clamp(11, 0, 10), 10)

    def test_edges(self) -> None:
        self.assertEqual(clamp(0, 0, 10), 0)
        self.assertEqual(clamp(10, 0, 10), 10)
        self.assertEqual(clamp(-1, 0, 10), 0)
        self.assertEqual(clamp(1, 0, 10), 1)
        self.assertEqual(clamp(9, 0, 10), 9)

    def test_degenerate(self) -> None:
        self.assertEqual(clamp(7, 3, 3), 3)


if __name__ == "__main__":
    unittest.main()
