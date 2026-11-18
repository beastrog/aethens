import unittest

from money import format_money


class TestMoney(unittest.TestCase):
    # The exact format is specified by the statement, so pinning it is correct.
    def test_examples(self) -> None:
        self.assertEqual(format_money(1234.5), "$1,234.50")
        self.assertEqual(format_money(0), "$0.00")
        self.assertEqual(format_money(1000000), "$1,000,000.00")
        self.assertEqual(format_money(12.345), "$12.35")


if __name__ == "__main__":
    unittest.main()
