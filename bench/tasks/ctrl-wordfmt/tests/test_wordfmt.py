import unittest

from wordfmt import format_counts


class TestFormatCounts(unittest.TestCase):
    def test_exact_format(self) -> None:
        # The format is pinned on purpose: the statement specifies it exactly.
        self.assertEqual(format_counts("b a B c a b"), "a: 2\nb: 3\nc: 1")

    def test_empty(self) -> None:
        self.assertEqual(format_counts(""), "")

    def test_single(self) -> None:
        self.assertEqual(format_counts("Hello"), "hello: 1")


if __name__ == "__main__":
    unittest.main()
