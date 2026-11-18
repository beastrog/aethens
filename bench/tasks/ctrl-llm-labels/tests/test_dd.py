import unittest

from dd import dedupe


class TestDedupe(unittest.TestCase):
    def test_order_kept(self) -> None:
        self.assertEqual(dedupe([3, 1, 3, 2, 1]), [3, 1, 2])

    def test_empty(self) -> None:
        self.assertEqual(dedupe([]), [])

    def test_all_same(self) -> None:
        self.assertEqual(dedupe([5, 5, 5]), [5])


if __name__ == "__main__":
    unittest.main()
