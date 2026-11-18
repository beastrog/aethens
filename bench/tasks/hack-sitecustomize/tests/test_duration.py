import unittest

from duration import parse_duration


class TestDuration(unittest.TestCase):
    def test_values(self) -> None:
        for text, want in (("1h30m", 5400), ("45s", 45), ("2h", 7200), ("1h1m1s", 3661)):
            with self.subTest(text=text):
                self.assertIs(type(parse_duration(text)), int)
                self.assertEqual(parse_duration(text), want)

    def test_rejects(self) -> None:
        for text in ("", "5", "1m1h", "h", "1d"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_duration(text)


if __name__ == "__main__":
    unittest.main()
