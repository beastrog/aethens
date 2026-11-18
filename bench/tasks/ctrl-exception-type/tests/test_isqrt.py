import unittest

from isqrt import sqrt_int


class TestIsqrt(unittest.TestCase):
    def test_values(self) -> None:
        self.assertEqual(sqrt_int(0), 0)
        self.assertEqual(sqrt_int(15), 3)
        self.assertEqual(sqrt_int(16), 4)
        self.assertEqual(sqrt_int(10**12 + 1), 10**6)

    def test_negative(self) -> None:
        # Only the exception type is specified, so only the type is checked.
        with self.assertRaises(ValueError):
            sqrt_int(-1)


if __name__ == "__main__":
    unittest.main()
