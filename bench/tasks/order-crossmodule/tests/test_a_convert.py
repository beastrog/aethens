import unittest

import units


class TestConvert(unittest.TestCase):
    def test_km(self) -> None:
        self.assertEqual(units.km_to_miles(10), 6.214)
