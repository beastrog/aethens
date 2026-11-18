import unittest

from fib import fib


class TestFib(unittest.TestCase):
    # The gold memoises across tests, but every test gives the same verdict in any order.
    def test_base(self) -> None:
        self.assertEqual((fib(0), fib(1)), (0, 1))

    def test_small(self) -> None:
        self.assertEqual([fib(i) for i in range(2, 10)], [1, 2, 3, 5, 8, 13, 21, 34])

    def test_large(self) -> None:
        self.assertEqual(fib(300) % 1_000_000, 979_600)
        self.assertEqual(fib(90), 2880067194370816120)
