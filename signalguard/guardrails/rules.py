"""The declared guardrail rules. Each is a small, named, single-responsibility object.

  PRE  (input):  Redaction, BudgetCap
  POST (output): EvidenceRequired, NoInvestmentAdvice
"""
from __future__ import annotations

import re
from typing import Any

from .base import GuardrailResult, Phase


# ----------------------------- POST guardrails ------------------------------ #

class EvidenceRequired:
    """Every signal must carry a non-empty quote and reference a real source doc."""
    name = "EvidenceRequired"
    phase = Phase.POST

    def check(self, material: Any, state: Any) -> GuardrailResult:
        bad = [s.id for s in material.signals
               if not s.quote.strip() or material.doc(s.source_id) is None]
        passed = not bad
        return GuardrailResult(
            name=self.name, phase=self.phase, passed=passed,
            detail="all signals carry evidence" if passed
            else f"{len(bad)} signal(s) missing a quote or valid source",
            recommended_action="" if passed else "quarantine unevidenced signals",
            flagged_signal_ids=bad,
        )


class NoInvestmentAdvice:
    """Compliance: the agent surfaces observations, never recommendations. Catches
    buy/sell/short/price-target/recommendation language in a signal's claim."""
    name = "NoInvestmentAdvice"
    phase = Phase.POST
    _PATTERNS = [
        r"\bbuy\b", r"\bsell\b", r"\bshort the\b", r"\bgo long\b", r"\bgoing long\b",
        r"price target", r"we recommend", r"\brecommend buying\b", r"strong buy",
        r"\boverweight\b", r"\bunderweight\b", r"\btable[- ]?pounding\b",
    ]
    _rx = re.compile("|".join(_PATTERNS), re.I)

    def check(self, material: Any, state: Any) -> GuardrailResult:
        flagged = [s.id for s in material.signals if self._rx.search(s.claim)]
        passed = not flagged
        return GuardrailResult(
            name=self.name, phase=self.phase, passed=passed,
            detail="no investment-advice language" if passed
            else f"{len(flagged)} signal(s) contain investment-advice language",
            recommended_action="" if passed else "block flagged signals + escalate to compliance (HITL)",
            flagged_signal_ids=flagged,
        )


# ------------------------------ PRE guardrails ------------------------------ #

class BudgetCap:
    """Bounds the run: max worker calls, tokens, and dollar cost."""
    name = "BudgetCap"
    phase = Phase.PRE

    def check(self, material: Any, state: Any) -> GuardrailResult:
        cfg = state.config
        over = []
        if state.agent_calls > cfg.max_agent_calls:
            over.append(f"calls {state.agent_calls} > {cfg.max_agent_calls}")
        if state.tokens_used > cfg.max_tokens:
            over.append(f"tokens {state.tokens_used} > {cfg.max_tokens}")
        if state.cost_usd > cfg.max_cost_usd:
            over.append(f"cost ${state.cost_usd:.2f} > ${cfg.max_cost_usd:.2f}")
        passed = not over
        return GuardrailResult(
            name=self.name, phase=self.phase, passed=passed,
            detail="within budget" if passed else "; ".join(over),
            recommended_action="" if passed else "halt run + escalate to operator",
        )


class Redaction:
    """Strips PII / MNPI patterns from documents BEFORE the worker reads them.
    Mutates the material in place and reports how many spans were redacted."""
    name = "Redaction"
    phase = Phase.PRE
    _RULES = [
        (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[REDACTED_EMAIL]"),
        (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
        (re.compile(r"\bMNPI\b", re.I), "[REDACTED_MNPI]"),
    ]

    def check(self, material: Any, state: Any) -> GuardrailResult:
        n = 0
        for doc in material.docs:
            txt = doc.text
            for rx, repl in self._RULES:
                txt, c = rx.subn(repl, txt)
                n += c
            doc.text = txt
        return GuardrailResult(
            name=self.name, phase=self.phase, passed=True,
            detail=f"redacted {n} sensitive span(s)" if n else "no sensitive spans found",
            mutations=n,
        )
