import unittest

from stats import median

SAMPLES = ((3, 1, 2), (4, 1, 3, 2))  # module constant, never mutated


class TestMedian(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = [5, 3, 9, 1]  # shared class fixture, read-only in every test

    def test_odd(self) -> None:
        self.assertEqual(median(list(SAMPLES[0])), 2.0)

    def test_even(self) -> None:
        self.assertEqual(median(list(SAMPLES[1])), 2.5)

    def test_fixture(self) -> None:
        self.assertEqual(median(self.data), 4.0)
        self.assertEqual(self.data, [5, 3, 9, 1])

    def test_input_not_mutated(self) -> None:
        values = list(self.data)
        median(values)
        self.assertEqual(values, self.data)
