from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LineData:
    incidental_executions: int
    deliberate_executions: int
    incidental_asserts: int
    deliberate_asserts: int


class SessionStore:
    def get_or_create(self, key):
        raise NotImplementedError

    def merge(self, other) -> None:
        raise NotImplementedError

    def to_dict(self) -> dict:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict) -> SessionStore:
        raise NotImplementedError
