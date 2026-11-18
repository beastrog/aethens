import unittest

from tags import unique_tags


class TestTags(unittest.TestCase):
    def test_tags(self) -> None:
        # PLANTED DEFECT: the order is unspecified, but the test pins one order.
        self.assertEqual(unique_tags("red, green, red"), ["red", "green"])


if __name__ == "__main__":
    unittest.main()
