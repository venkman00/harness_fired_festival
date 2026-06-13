"""The three stage checkpoints.

  CP1 Ingest      — is the input a usable earnings document?
  CP2 Grounding   — is every signal backed by a verbatim quote from its source? (the spine)
  CP3 Synthesize  — is the signal set coherent and well-covered?
"""
from __future__ import annotations

import re
from typing import Any

from .base import CheckpointResult
from ..material.textnorm import ground_key
from ..material.types import SourceType


class CP1_Ingest:
    """Document-type-aware ingest gate.

    Berkshire and most issuers do NOT publish a call transcript with an analyst Q&A — the
    'earnings report' is a press release / 10-Q. So we accept the document if it looks like
    EITHER a call (Q&A/operator markers) OR a financial report (monetary figures + a
    reporting-period marker). Either shape is a legitimate earnings document."""
    name = "ingest"

    _QA_MARKERS = ["question-and-answer", "q&a", "your first question", "analyst",
                   "operator", "next question"]
    _PERIOD_MARKERS = ["quarter", "fiscal", "full year", "year ended", "three months",
                       "six months", "nine months", "q1", "q2", "q3", "q4"]
    _MONEY = re.compile(r"\$?\s?\d[\d,]*(?:\.\d+)?\s?(?:billion|million|thousand|bn|mm|%)",
                        re.I)

    def evaluate(self, material: Any, state: Any) -> CheckpointResult:
        docs = material.docs
        earnings = next((d for d in docs if d.source_type == SourceType.EARNINGS), None)
        text = earnings.text if earnings else ""
        low = text.lower()
        tokens = len(text.split())

        has_docs = len(docs) > 0
        has_earnings = earnings is not None
        enough = tokens >= state.config.min_report_tokens
        looks_like_call = any(m in low for m in self._QA_MARKERS)
        looks_like_report = (any(m in low for m in self._PERIOD_MARKERS)
                             and len(self._MONEY.findall(text)) >= 3)
        recognizable = looks_like_call or looks_like_report

        criteria = [
            ("at least one source document", has_docs),
            ("earnings document present", has_earnings),
            (f"document >= {state.config.min_report_tokens} tokens (got {tokens})", enough),
            ("recognizable as a call transcript OR a financial report", recognizable),
        ]
        passed = all(p for _, p in criteria)
        shape = "call" if looks_like_call else ("report" if looks_like_report else "unknown")
        return CheckpointResult(
            name=self.name, passed=passed, criteria=criteria,
            detail=f"ingested as '{shape}' document, {tokens} tokens"
            if passed else "input failed ingestion quality gate",
            data={"shape": shape, "tokens": tokens},
        )


class CP2_Grounding:
    """THE SPINE. Every signal's quote must appear verbatim (whitespace/case-normalized)
    in the source document it cites, and confidence must be in [0, 1]. Returns the ids of
    any ungrounded signals so the orchestrator can drop them and re-extract."""
    name = "grounding"

    def evaluate(self, material: Any, state: Any) -> CheckpointResult:
        ungrounded, bad_conf = [], []
        for s in material.signals:
            doc = material.doc(s.source_id)
            quote_key = ground_key(s.quote)
            if doc is None or not quote_key or quote_key not in ground_key(doc.text):
                ungrounded.append(s.id)
            if not (0.0 <= s.confidence <= 1.0):
                bad_conf.append(s.id)
        n = len(material.signals)
        criteria = [
            ("at least one signal extracted", n > 0),
            (f"all {n} quote(s) verbatim-match their source", not ungrounded),
            ("all confidences within [0, 1]", not bad_conf),
        ]
        passed = all(p for _, p in criteria)
        return CheckpointResult(
            name=self.name, passed=passed, criteria=criteria,
            detail="every signal is grounded in its source" if passed
            else f"{len(ungrounded)} ungrounded, {len(bad_conf)} out-of-range confidence",
            data={"ungrounded_ids": ungrounded, "bad_confidence_ids": bad_conf},
        )


class CP3_Synthesize:
    """Coherence gate on the final signal set: enough distinct signal kinds and no exact
    duplicates. Contradictions are flagged in data (not failed) for analyst attention."""
    name = "synthesize"

    def evaluate(self, material: Any, state: Any) -> CheckpointResult:
        signals = material.signals
        kinds = {s.kind for s in signals}
        keys = [(s.kind, s.quote[:40]) for s in signals]
        no_dupes = len(keys) == len(set(keys))

        # contradiction = same signal kind asserted in opposite directions
        dirs: dict = {}
        for s in signals:
            dirs.setdefault(s.kind, set()).add(s.direction)
        contradictions = [k.value for k, ds in dirs.items()
                          if {"bullish", "bearish"} <= {d.value for d in ds}]

        enough_kinds = len(kinds) >= state.config.min_signal_kinds
        criteria = [
            (f">= {state.config.min_signal_kinds} distinct signal kinds (got {len(kinds)})",
             enough_kinds),
            ("no duplicate signals", no_dupes),
        ]
        passed = all(p for _, p in criteria)
        return CheckpointResult(
            name=self.name, passed=passed, criteria=criteria,
            detail="signal set is coherent" if passed else "signal coverage is thin",
            data={"kinds": sorted(k.value for k in kinds), "contradictions": contradictions},
        )
