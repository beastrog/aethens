import unittest

from summary import summarise


class TestSummary(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertIsNone(summarise([]))

    def test_mixed(self) -> None:
        self.assertEqual(summarise([3, -2, 0, -1, 5]), (2, [4, 1]))

    def test_errors_propagate(self) -> None:
        with self.assertRaises(TypeError):
            summarise([1, "x"])  # type: ignore[list-item]
