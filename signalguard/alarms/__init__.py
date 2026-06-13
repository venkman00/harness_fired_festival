"""Alarms pillar: structured, named alarms with severity + recommended action, routed
to a human-in-the-loop queue when severity warrants stopping to ask."""
from .types import Alarm, AlarmType, Severity
from .bus import AlarmBus

__all__ = ["Alarm", "AlarmType", "Severity", "AlarmBus"]
