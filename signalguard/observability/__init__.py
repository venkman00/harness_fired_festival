"""Observability pillar (Pillar 4 — Tooling): wrap every worker call and stage in a span
carrying token, cost, and latency attributes. Emits OpenTelemetry spans when available —
no lock-in — and always keeps an in-process record that feeds the audit trail, the report,
and the BudgetCap guardrail."""
from .tracing import Telemetry, SpanRecord

__all__ = ["Telemetry", "SpanRecord"]
