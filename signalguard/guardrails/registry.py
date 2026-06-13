"""The DECLARED guardrail registry. The orchestrator iterates this list — guardrails are
never hard-coded inline. To add a constraint, add it here."""
from __future__ import annotations

from .base import Phase
from .rules import BudgetCap, EvidenceRequired, NoInvestmentAdvice, Redaction

REGISTRY = [
    Redaction(),           # PRE  — clean material before the worker sees it
    BudgetCap(),           # PRE  — refuse to run if over budget
    EvidenceRequired(),    # POST — every signal must be evidenced
    NoInvestmentAdvice(),  # POST — no compliance-risky recommendation language
]


def pre_guardrails():
    return [g for g in REGISTRY if g.phase == Phase.PRE]


def post_guardrails():
    return [g for g in REGISTRY if g.phase == Phase.POST]
