import unittest

import units


class TestPatchedConstant(unittest.TestCase):
    # PLANTED DEFECT: this module changes a shared module constant and never restores it.
    # unittest runs test_a_convert first, so the default order passes; any order that runs this
    # module first breaks test_a_convert.TestConvert.test_km.
    def test_nautical(self) -> None:
        units.MILES_PER_KM = 0.539957
        self.assertEqual(units.km_to_miles(10), 5.4)
