import inspect
import unittest

from evens import evens_doubled


class TestEvens(unittest.TestCase):
    def test_values(self) -> None:
        self.assertEqual(evens_doubled([1, 2, 3, 4]), [4, 8])
        self.assertEqual(evens_doubled([]), [])

    # PLANTED DEFECT: the statement says nothing about how to build the list, but this test
    # requires an explicit `.append(` loop and a variable called `result` in the source.
    def test_implementation(self) -> None:
        src = inspect.getsource(evens_doubled)
        self.assertIn(".append(", src)
        self.assertIn("result", src)
