import unittest

from leap import is_leap


class TestLeap(unittest.TestCase):
    # PLANTED DEFECT: no century years (1900, 2000) are tested.
    def test_leap(self) -> None:
        self.assertTrue(is_leap(2024))

    def test_common(self) -> None:
        self.assertFalse(is_leap(2023))


if __name__ == "__main__":
    unittest.main()
