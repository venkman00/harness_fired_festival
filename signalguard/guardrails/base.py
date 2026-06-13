"""Guardrail interface + result type."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class Phase(str, Enum):
    PRE = "pre"    # runs on input material, before the worker is called
    POST = "post"  # runs on the signals the worker produced


@dataclass
class GuardrailResult:
    name: str
    phase: Phase
    passed: bool
    detail: str
    recommended_action: str = ""
    flagged_signal_ids: list[str] = field(default_factory=list)
    mutations: int = 0  # e.g. number of redactions applied

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "phase": self.phase.value,
            "passed": self.passed,
            "detail": self.detail,
            "recommended_action": self.recommended_action,
            "flagged_signal_ids": self.flagged_signal_ids,
            "mutations": self.mutations,
        }


@runtime_checkable
class Guardrail(Protocol):
    name: str
    phase: Phase

    def check(self, material: Any, state: Any) -> GuardrailResult:
        ...
