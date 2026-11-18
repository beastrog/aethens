import unittest

from tail import last_n


class TestLastN(unittest.TestCase):
    # PLANTED DEFECT: n = 0 is never tested.
    def test_two(self) -> None:
        self.assertEqual(last_n([1, 2, 3], 2), [2, 3])

    def test_more_than_len(self) -> None:
        self.assertEqual(last_n([1], 5), [1])


if __name__ == "__main__":
    unittest.main()
