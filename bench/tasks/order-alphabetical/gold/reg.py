_REGISTRY: dict[str, int] = {}


def register(name: str, value: int) -> None:
    _REGISTRY[name] = value


def lookup(name: str) -> int:
    return _REGISTRY[name]
