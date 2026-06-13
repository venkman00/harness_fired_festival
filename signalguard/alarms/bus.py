"""Alarm bus: collects structured alarms, prints them, and routes HIGH/CRITICAL alarms
to a human-in-the-loop queue. The orchestrator consults `hitl_queue` to decide when to
stop and ask a human rather than guess."""
from __future__ import annotations

from .types import Alarm, AlarmType, Severity

_GLYPH = {
    Severity.LOW: "·",
    Severity.MEDIUM: "▪",
    Severity.HIGH: "▲",
    Severity.CRITICAL: "■",
}


class AlarmBus:
    ESCALATE = {Severity.HIGH, Severity.CRITICAL}

    def __init__(self, verbose: bool = True):
        self.alarms: list[Alarm] = []
        self.hitl_queue: list[Alarm] = []
        self.verbose = verbose

    def raise_alarm(self, type: AlarmType, severity: Severity, context: dict,
                    recommended_action: str) -> Alarm:
        alarm = Alarm(type, severity, context, recommended_action)
        self.alarms.append(alarm)
        if severity in self.ESCALATE:
            self.hitl_queue.append(alarm)
        if self.verbose:
            tag = "  → HITL" if severity in self.ESCALATE else ""
            print(f"  {_GLYPH[severity]} ALARM [{severity.value}] {type.value}: "
                  f"{recommended_action}{tag}")
        return alarm

    def needs_human(self) -> bool:
        return len(self.hitl_queue) > 0

    def by_type(self, type: AlarmType) -> list[Alarm]:
        return [a for a in self.alarms if a.type == type]

    def to_dict(self) -> dict:
        return {
            "alarms": [a.to_dict() for a in self.alarms],
            "hitl_queue": [a.to_dict() for a in self.hitl_queue],
        }
