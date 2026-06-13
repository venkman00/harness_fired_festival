"""Deterministic, no-LLM worker. Two jobs:

  1. Let the whole harness run offline (no API key) for dev + CI.
  2. Make the feedback loop *visible*: on its first attempt it deliberately corrupts one
     quote (simulating a hallucinated citation) so the grounding checkpoint fails; once the
     harness feeds that failure back, it returns only verbatim quotes. Same protocol as a
     real model — the harness cannot tell the difference."""
from __future__ import annotations

import re

from ..material.types import Direction, Signal, SignalKind, SourceDoc
from .base import AgentContext

# (kind, direction, trigger keywords, confidence)
_PATTERNS = [
    (SignalKind.GUIDANCE, Direction.BULLISH,
     ["expect", "outlook", "guidance", "anticipate", "full year"], 0.82),
    (SignalKind.METRIC_SURPRISE, Direction.BULLISH,
     ["record", "grew", "increased", "rose", "gain", "up "], 0.74),
    (SignalKind.RISK_FLAG, Direction.BEARISH,
     ["headwind", "decline", "pressure", "decrease", "loss", "weakness", "uncertain"], 0.50),
    (SignalKind.SENTIMENT, Direction.BULLISH,
     ["strong", "robust", "momentum", "confident", "resilient"], 0.48),
]


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if len(p.strip()) > 25]


def _claim(kind: SignalKind, sentence: str) -> str:
    label = {
        SignalKind.GUIDANCE: "Guidance signal",
        SignalKind.METRIC_SURPRISE: "Metric surprise",
        SignalKind.RISK_FLAG: "Risk flag",
        SignalKind.SENTIMENT: "Sentiment shift",
    }[kind]
    snippet = sentence[:100] + ("…" if len(sentence) > 100 else "")
    return f"{label}: {snippet}"


class MockAgent:
    name = "mock"
    model = "deterministic-v1"

    def __init__(self, simulate_hallucination: bool = True, max_signals: int = 8):
        self.simulate_hallucination = simulate_hallucination
        self.max_signals = max_signals

    def extract_signals(self, docs: list[SourceDoc], ctx: AgentContext) -> list[Signal]:
        first_attempt = ctx.attempt == 0 and not ctx.feedback
        signals: list[Signal] = []
        seen: set[tuple] = set()
        corrupted = False

        for doc in docs:
            for sent in _sentences(doc.text):
                low = sent.lower()
                for kind, direction, kws, conf in _PATTERNS:
                    if not any(k in low for k in kws):
                        continue
                    key = (kind, sent[:40])
                    if key in seen:
                        break
                    seen.add(key)
                    quote = sent
                    # First pass: fabricate a tail on one quote to trip CP2 grounding.
                    if self.simulate_hallucination and first_attempt and not corrupted:
                        quote = sent + " — margins expanded 900bps year over year"
                        corrupted = True
                    signals.append(Signal(
                        kind=kind, claim=_claim(kind, sent), quote=quote,
                        source_id=doc.source_id, confidence=conf, direction=direction,
                    ))
                    break  # one signal per sentence

        signals = signals[: self.max_signals]
        # report (estimated) usage so the observability layer can record it
        approx_in = sum(len(d.text) for d in docs) // 4
        ctx.report_usage(tokens_in=approx_in, tokens_out=len(signals) * 60, cost_usd=0.0)
        return signals
