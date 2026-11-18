class IdGen:
    def __init__(self) -> None:
        self._n = 0

    def next_id(self) -> int:
        self._n += 1
        return self._n
