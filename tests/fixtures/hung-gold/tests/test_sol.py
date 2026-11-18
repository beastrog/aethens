import unittest

from sol import f


class T(unittest.TestCase):
    def test_f(self) -> None:
        self.assertEqual(f(), 1)
