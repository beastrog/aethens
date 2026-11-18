import unittest

from shard import assign_shards


class TestShards(unittest.TestCase):
    def test_in_range(self) -> None:
        shards = assign_shards(["a", "b", "c", "d"], 4)
        self.assertTrue(all(0 <= s < 4 for s in shards.values()))

    def test_spread(self) -> None:
        # PLANTED DEFECT: assumes the keys land on at least three distinct shards, which depends
        # on the per-process string hash seed.
        shards = assign_shards(["a", "b", "c", "d"], 4)
        self.assertGreaterEqual(len(set(shards.values())), 3)


if __name__ == "__main__":
    unittest.main()
