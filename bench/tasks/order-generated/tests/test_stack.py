import unittest
from collections.abc import Callable

from stack import Stack

# PLANTED DEFECT: tests share one Stack, and the generated test names (test_0, test_1) are
# assigned in set iteration order, so whether "pop" runs before "push" depends on the hash seed.
SHARED = Stack()


def _make(op: str) -> Callable[[unittest.TestCase], None]:
    def test(self: unittest.TestCase) -> None:
        if op == "push":
            SHARED.push(1)
            self.assertGreaterEqual(SHARED.size(), 1)
        else:
            self.assertEqual(SHARED.pop(), 1)

    return test


class TestStack(unittest.TestCase):
    def test_fresh(self) -> None:
        s = Stack()
        s.push(2)
        self.assertEqual((s.size(), s.pop(), s.size()), (1, 2, 0))


for i, op in enumerate({"push", "pop"}):
    setattr(TestStack, f"test_{i}", _make(op))


if __name__ == "__main__":
    unittest.main()
