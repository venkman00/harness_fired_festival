"""Checkpoint interface + result type."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class CheckpointResult:
    name: str
    passed: bool
    criteria: list[tuple[str, bool]]  # explicit, itemized pass/fail
    detail: str = ""
    data: dict = field(default_factory=dict)  # e.g. failing signal ids

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "criteria": [{"criterion": c, "passed": p} for c, p in self.criteria],
            "detail": self.detail,
            "data": self.data,
        }


@runtime_checkable
class Checkpoint(Protocol):
    name: str

    def evaluate(self, material: Any, state: Any) -> CheckpointResult:
        ...
