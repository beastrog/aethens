import unittest

from words import word_lengths


class TestWords(unittest.TestCase):
    def test_values(self) -> None:
        self.assertEqual(word_lengths("a bb  ccc"), {"a": 1, "bb": 2, "ccc": 3})

    # PLANTED DEFECT: pins the gold's local variable names through the code object.
    def test_locals(self) -> None:
        self.assertEqual(word_lengths.__code__.co_varnames, ("text", "lengths", "word"))
