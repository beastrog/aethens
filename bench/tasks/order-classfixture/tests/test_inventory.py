import unittest

from inventory import make_inventory, smallest


class TestInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.counts = make_inventory()

    # PLANTED DEFECT: test_a sorts the shared class fixture in place; test_b only passes because
    # unittest runs test_a first. Alone or reversed, test_b fails.
    def test_a_smallest(self) -> None:
        self.counts.sort()
        self.assertEqual(smallest(self.counts), 10)

    def test_b_first_is_smallest(self) -> None:
        self.assertEqual(self.counts[0], 10)
