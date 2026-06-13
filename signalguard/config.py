"""Harness configuration — all tunable thresholds live here, declared not implicit."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class HarnessConfig:
    # extraction loop
    max_extract_retries: int = 2          # re-extractions allowed on grounding failure
    # CP1 ingest gate
    min_report_tokens: int = 150
    # CP2 grounding gate
    # (no threshold — quotes must verbatim-match; checked structurally)
    # confidence / HITL
    low_confidence_threshold: float = 0.55
    low_confidence_cluster_size: int = 2  # >= this many low-conf signals → HITL review
    # CP3 synthesis gate
    min_signal_kinds: int = 2
    # budget caps (BudgetCap guardrail)
    max_agent_calls: int = 6
    max_tokens: int = 200_000
    max_cost_usd: float = 5.0
    # default worker
    default_model: str = "claude-opus-4-8"
