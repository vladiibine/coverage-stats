from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterator

# slots=True (Python 3.10+) eliminates __dict__ per instance and speeds up
# attribute access.  LineData is allocated once per unique (path, lineno) pair
# and its fields are incremented on every line event, so this matters.
_SLOTS_KW: dict[str, bool] = {"slots": True} if sys.version_info >= (3, 10) else {}


@dataclass(**_SLOTS_KW)
class ArcData:
    """Execution counts for a single (from_line, to_line) arc transition."""
    incidental_executions: int = 0
    deliberate_executions: int = 0


@dataclass(**_SLOTS_KW)
class LineData:
    incidental_executions: int = 0
    deliberate_executions: int = 0
    incidental_asserts: int = 0
    deliberate_asserts: int = 0
    incidental_tests: int = 0
    deliberate_tests: int = 0
    # Empty only when --coverage-stats-no-track-test-ids is set.
    incidental_test_ids: set[str] = field(default_factory=set)
    deliberate_test_ids: set[str] = field(default_factory=set)


class SessionStore:
    def __init__(self) -> None:
        # defaultdict reduces get_or_create to a single dict lookup on both hit
        # and miss (vs. two lookups with the previous `if key not in` pattern).
        # __contains__ / `in` checks do NOT trigger __missing__, so `key not in store`
        # remains safe.
        self._data: defaultdict[tuple[str, int], LineData] = defaultdict(LineData)
        self._arc_data: defaultdict[tuple[str, int, int], ArcData] = defaultdict(ArcData)

    def get_or_create(self, key: tuple[str, int]) -> LineData:
        return self._data[key]

    def get_or_create_arc(self, key: tuple[str, int, int]) -> ArcData:
        return self._arc_data[key]

    def has_arc_data(self) -> bool:
        """Return True if the store contains any arc data."""
        return len(self._arc_data) > 0

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

    def arcs_for_file(self, path: str) -> dict[tuple[int, int], ArcData]:
        """Return observed arc data for a single file as {(from_line, to_line): ArcData}."""
        result: dict[tuple[int, int], ArcData] = {}
        for (p, from_line, to_line), ad in self._arc_data.items():
            if p == path:
                result[(from_line, to_line)] = ad
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
            ld.incidental_test_ids |= other_ld.incidental_test_ids
            ld.deliberate_test_ids |= other_ld.deliberate_test_ids
        for arc_key, other_ad in other._arc_data.items():
            ad = self.get_or_create_arc(arc_key)
            ad.incidental_executions += other_ad.incidental_executions
            ad.deliberate_executions += other_ad.deliberate_executions

    def to_dict(self) -> dict[str, Any]:
        """Serialise the store to a JSON-safe dict.

        Format: ``{"lines": {path\\x00lineno: [inc_exec, del_exec, ...]},
        "arcs": {path\\x00from\\x00to: [inc_exec, del_exec]}}``

        Backward compatibility: old callers that received a flat dict of line
        data will see the same structure under the ``"lines"`` key.  Old JSON
        files without an ``"arcs"`` key load cleanly (arcs default to empty).
        """
        lines: dict[str, list[int | list[str]]] = {}
        for (path, lineno), ld in self._data.items():
            entry: list[int | list[str]] = [
                ld.incidental_executions,
                ld.deliberate_executions,
                ld.incidental_asserts,
                ld.deliberate_asserts,
                ld.incidental_tests,
                ld.deliberate_tests,
            ]
            if ld.incidental_test_ids or ld.deliberate_test_ids:
                entry.append(sorted(ld.incidental_test_ids))
                entry.append(sorted(ld.deliberate_test_ids))
            lines[f"{path}\x00{lineno}"] = entry
        arcs: dict[str, list[int]] = {}
        for (path, from_line, to_line), ad in self._arc_data.items():
            arcs[f"{path}\x00{from_line}\x00{to_line}"] = [
                ad.incidental_executions,
                ad.deliberate_executions,
            ]
        return {"lines": lines, "arcs": arcs}

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
    def from_dict(cls, data: dict[str, Any]) -> SessionStore:
        """Deserialise a store from the dict produced by ``to_dict()``.

        Backward-compatible: accepts both the new format (``{"lines": ..., "arcs": ...}``)
        and the old flat format (``{path\\x00lineno: [...]}``) without an ``"arcs"`` key.
        Values with only 6 elements (old format without IDs) deserialise cleanly
        with empty ID sets.
        """
        store = cls()
        # New format: {"lines": {...}, "arcs": {...}}
        # Old format: flat dict with path\x00lineno keys
        if "lines" in data and isinstance(data["lines"], dict):
            line_data = data["lines"]
            arc_data = data.get("arcs", {})
        else:
            line_data = data
            arc_data = {}
        for raw_key, values in line_data.items():
            path, lineno_str = raw_key.split("\x00", 1)
            key = (path, int(lineno_str))
            ld = store.get_or_create(key)
            ld.incidental_executions = values[0]
            ld.deliberate_executions = values[1]
            ld.incidental_asserts = values[2]
            ld.deliberate_asserts = values[3]
            ld.incidental_tests = values[4] if len(values) > 4 else 0
            ld.deliberate_tests = values[5] if len(values) > 5 else 0
            ld.incidental_test_ids = (
                set(values[6]) if len(values) > 6 and isinstance(values[6], list) else set()
            )
            ld.deliberate_test_ids = (
                set(values[7]) if len(values) > 7 and isinstance(values[7], list) else set()
            )
        for raw_key, values in arc_data.items():
            parts = raw_key.split("\x00")
            path = parts[0]
            from_line = int(parts[1])
            to_line = int(parts[2])
            ad = store.get_or_create_arc((path, from_line, to_line))
            ad.incidental_executions = values[0]
            ad.deliberate_executions = values[1]
        return store
