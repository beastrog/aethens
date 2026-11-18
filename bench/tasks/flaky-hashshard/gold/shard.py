def assign_shards(keys: list[str], n: int) -> dict[str, int]:
    return {k: hash(k) % n for k in keys}
