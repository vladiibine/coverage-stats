from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LineData:
    incidental_executions: int = 0
    deliberate_executions: int = 0
    incidental_asserts: int = 0
    deliberate_asserts: int = 0


class SessionStore:
    def __init__(self) -> None:
        self._data: dict[tuple[str, int], LineData] = {}

    def get_or_create(self, key: tuple[str, int]) -> LineData:
        if key not in self._data:
            self._data[key] = LineData()
        return self._data[key]

    def merge(self, other: SessionStore) -> None:
        for key, other_ld in other._data.items():
            ld = self.get_or_create(key)
            ld.incidental_executions += other_ld.incidental_executions
            ld.deliberate_executions += other_ld.deliberate_executions
            ld.incidental_asserts += other_ld.incidental_asserts
            ld.deliberate_asserts += other_ld.deliberate_asserts

    def to_dict(self) -> dict[str, list[int]]:
        return {
            f"{path}\x00{lineno}": [
                ld.incidental_executions,
                ld.deliberate_executions,
                ld.incidental_asserts,
                ld.deliberate_asserts,
            ]
            for (path, lineno), ld in self._data.items()
        }

    @classmethod
    def from_dict(cls, data: dict[str, list[int]]) -> SessionStore:
        store = cls()
        for raw_key, values in data.items():
            path, lineno_str = raw_key.split("\x00", 1)
            key = (path, int(lineno_str))
            ld = store.get_or_create(key)
            ld.incidental_executions = values[0]
            ld.deliberate_executions = values[1]
            ld.incidental_asserts = values[2]
            ld.deliberate_asserts = values[3]
        return store
