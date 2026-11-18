import unittest

from ids import IdGen


class TestIds(unittest.TestCase):
    def test_sequence(self) -> None:
        gen = IdGen()
        self.assertEqual([gen.next_id() for _ in range(3)], [1, 2, 3])

    def test_named(self) -> None:
        gen = IdGen()
        # PLANTED DEFECT: which name gets id 1 depends on set iteration order.
        ids = {name: gen.next_id() for name in {"alice", "bob"}}
        self.assertEqual(ids["alice"], 1)


if __name__ == "__main__":
    unittest.main()
