import unittest

from tags import unique_tags


class TestTags(unittest.TestCase):
    def test_tags(self) -> None:
        # Order is unspecified, so the test compares as a sorted list (correct, not flaky).
        self.assertEqual(sorted(unique_tags("red, green, blue, red")), ["blue", "green", "red"])

    def test_no_duplicates(self) -> None:
        tags = unique_tags("a,a,a, a ,b")
        self.assertEqual(len(tags), len(set(tags)))

    def test_empty(self) -> None:
        self.assertEqual(unique_tags(" , ,"), [])


if __name__ == "__main__":
    unittest.main()
