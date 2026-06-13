"""Guardrails pillar: declared constraints checked around every agent call.

Guardrails are DECLARED, not implicit — they live in an explicit `REGISTRY` that the
orchestrator iterates. PRE guardrails run on input material before the worker sees it;
POST guardrails run on the worker's output."""
from .base import Guardrail, GuardrailResult, Phase
from .registry import REGISTRY, pre_guardrails, post_guardrails

__all__ = [
    "Guardrail", "GuardrailResult", "Phase",
    "REGISTRY", "pre_guardrails", "post_guardrails",
]
