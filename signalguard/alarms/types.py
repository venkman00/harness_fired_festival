"""Structured alarm types. An alarm is never a bare string — it is a named type with a
severity, machine-readable context, and a recommended action the harness can route on."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlarmType(str, Enum):
    GROUNDING_VIOLATION = "GroundingViolation"        # quote not found in source
    COMPLIANCE_BREACH = "ComplianceBreach"            # investment-advice language
    BUDGET_EXCEEDED = "BudgetExceeded"                # token / call / cost cap hit
    LOW_CONFIDENCE_CLUSTER = "LowConfidenceCluster"   # too many low-confidence signals
    CHECKPOINT_FAILURE = "CheckpointFailure"          # a stage gate failed terminally


@dataclass
class Alarm:
    type: AlarmType
    severity: Severity
    context: dict
    recommended_action: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "severity": self.severity.value,
            "context": self.context,
            "recommended_action": self.recommended_action,
            "timestamp": self.timestamp,
        }
