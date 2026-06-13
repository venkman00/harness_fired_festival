"""The worker contract. One method: read docs, return signals. The harness steers the
worker only through `AgentContext` (attempt number + feedback), and the worker reports
resource usage back through `ctx.report_usage(...)` so the observability layer can record
tokens/cost without the worker knowing anything about OTEL."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ..material.types import Signal, SourceDoc


@dataclass
class AgentContext:
    stage: str = "extract"
    attempt: int = 0
    feedback: list[str] = field(default_factory=list)
    ticker: str = ""
    # usage reported by the worker for the most recent call (read by the harness)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0

    def report_usage(self, tokens_in: int, tokens_out: int, cost_usd: float) -> None:
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.cost_usd = cost_usd


@runtime_checkable
class Agent(Protocol):
    name: str
    model: str

    def extract_signals(self, docs: list[SourceDoc], ctx: AgentContext) -> list[Signal]:
        ...
