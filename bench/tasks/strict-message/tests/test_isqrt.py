import unittest

from isqrt import sqrt_int


class TestIsqrt(unittest.TestCase):
    def test_values(self) -> None:
        self.assertEqual(sqrt_int(0), 0)
        self.assertEqual(sqrt_int(15), 3)
        self.assertEqual(sqrt_int(16), 4)

    def test_negative(self) -> None:
        # PLANTED DEFECT: the statement only asks for ValueError, not this exact message.
        with self.assertRaises(ValueError) as cm:
            sqrt_int(-1)
        self.assertEqual(str(cm.exception), "negative value: -1")


if __name__ == "__main__":
    unittest.main()
