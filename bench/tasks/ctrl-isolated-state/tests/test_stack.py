import unittest

from stack import Stack


class TestStack(unittest.TestCase):
    def setUp(self) -> None:
        # Fresh state for every test: no order dependence.
        self.s = Stack()

    def test_push_pop(self) -> None:
        for x in {3, 1, 2}:  # set order does not matter: only the multiset is checked
            self.s.push(x)
        self.assertEqual(sorted(self.s.pop() for _ in range(3)), [1, 2, 3])

    def test_lifo(self) -> None:
        self.s.push(1)
        self.s.push(2)
        self.assertEqual(self.s.pop(), 2)

    def test_empty_pop(self) -> None:
        with self.assertRaises(IndexError):
            self.s.pop()

    def test_size(self) -> None:
        self.assertEqual(self.s.size(), 0)
        self.s.push(5)
        self.assertEqual(self.s.size(), 1)


if __name__ == "__main__":
    unittest.main()
