import unittest

from reg import lookup, register


class TestRegistry(unittest.TestCase):
    # PLANTED DEFECT: test_b only passes because unittest runs test_a first (alphabetical order)
    # and the registry is module-level state. Run alone, or in another order, test_b fails.
    def test_a_register(self) -> None:
        register("x", 1)
        self.assertEqual(lookup("x"), 1)

    def test_b_lookup(self) -> None:
        self.assertEqual(lookup("x"), 1)


if __name__ == "__main__":
    unittest.main()
