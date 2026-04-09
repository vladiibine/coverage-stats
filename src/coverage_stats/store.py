from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterator

# slots=True (Python 3.10+) eliminates __dict__ per instance and speeds up
# attribute access.  LineData is allocated once per unique (path, lineno) pair
# and its fields are incremented on every line event, so this matters.
_SLOTS_KW: dict[str, bool] = {"slots": True} if sys.version_info >= (3, 10) else {}


@dataclass(**_SLOTS_KW)
class LineData:
    incidental_executions: int = 0
    deliberate_executions: int = 0
    incidental_asserts: int = 0
    deliberate_asserts: int = 0
    incidental_tests: int = 0
    deliberate_tests: int = 0


class SessionStore:
    def __init__(self) -> None:
        # defaultdict reduces get_or_create to a single dict lookup on both hit
        # and miss (vs. two lookups with the previous `if key not in` pattern).
        # __contains__ / `in` checks do NOT trigger __missing__, so `key not in store`
        # remains safe.
        self._data: defaultdict[tuple[str, int], LineData] = defaultdict(LineData)

    def get_or_create(self, key: tuple[str, int]) -> LineData:
        return self._data[key]

    def items(self) -> Iterator[tuple[tuple[str, int], LineData]]:
        """Iterate over all (path, lineno) → LineData entries."""
        return iter(self._data.items())

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def files(self) -> dict[str, dict[int, LineData]]:
        """Return line data grouped by file path."""
        result: dict[str, dict[int, LineData]] = {}
        for (path, lineno), ld in self._data.items():
            result.setdefault(path, {})[lineno] = ld
        return result

    def merge(self, other: SessionStore) -> None:
        for key, other_ld in other._data.items():
            ld = self.get_or_create(key)
            ld.incidental_executions += other_ld.incidental_executions
            ld.deliberate_executions += other_ld.deliberate_executions
            ld.incidental_asserts += other_ld.incidental_asserts
            ld.deliberate_asserts += other_ld.deliberate_asserts
            ld.incidental_tests += other_ld.incidental_tests
            ld.deliberate_tests += other_ld.deliberate_tests

    def to_dict(self) -> dict[str, list[int]]:
        return {
            f"{path}\x00{lineno}": [
                ld.incidental_executions,
                ld.deliberate_executions,
                ld.incidental_asserts,
                ld.deliberate_asserts,
                ld.incidental_tests,
                ld.deliberate_tests,
            ]
            for (path, lineno), ld in self._data.items()
        }

    def lines_by_file(self) -> dict[str, list[int]]:
        """Return executed line numbers grouped by file path.

        Only includes lines that were actually executed (non-zero execution count).
        The format matches what coverage.CoverageData.add_lines() expects.
        """
        result: dict[str, list[int]] = {}
        for (path, lineno), ld in self._data.items():
            if ld.incidental_executions > 0 or ld.deliberate_executions > 0:
                result.setdefault(path, []).append(lineno)
        return result

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
            ld.incidental_tests = values[4] if len(values) > 4 else 0
            ld.deliberate_tests = values[5] if len(values) > 5 else 0
        return store
