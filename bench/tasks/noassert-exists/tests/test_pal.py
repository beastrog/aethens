import unittest

import pal


class TestPal(unittest.TestCase):
    def test_defined(self) -> None:
        # PLANTED DEFECT: only checks that the function exists.
        self.assertTrue(callable(pal.is_palindrome))


if __name__ == "__main__":
    unittest.main()
