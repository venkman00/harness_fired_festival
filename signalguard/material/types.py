"""Canonical typed material. These are the ONLY objects that cross the harness/worker
boundary. Everything is a plain dataclass with explicit (de)serialization so artifacts
can be persisted and replayed."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SourceType(str, Enum):
    EARNINGS = "earnings_report"      # press release / 10-Q / 10-K / shareholder letter
    PODCAST = "podcast_transcript"
    X_POSTS = "x_posts"


class SignalKind(str, Enum):
    GUIDANCE = "guidance_change"
    SENTIMENT = "sentiment_shift"
    METRIC_SURPRISE = "metric_surprise"
    RISK_FLAG = "risk_flag"


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class SourceDoc:
    """A single normalized source document the worker may read from."""
    source_id: str
    source_type: SourceType
    title: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
            "title": self.title,
            "text": self.text,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SourceDoc":
        return cls(
            source_id=d["source_id"],
            source_type=SourceType(d["source_type"]),
            title=d["title"],
            text=d["text"],
            metadata=d.get("metadata", {}),
        )


@dataclass
class Signal:
    """One investing signal. Every signal MUST carry a verbatim evidence quote and the
    id of the source document it came from — that is what the grounding checkpoint verifies."""
    kind: SignalKind
    claim: str
    quote: str
    source_id: str
    confidence: float
    direction: Direction = Direction.NEUTRAL
    corroborating_sources: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "claim": self.claim,
            "quote": self.quote,
            "source_id": self.source_id,
            "confidence": self.confidence,
            "direction": self.direction.value,
            "corroborating_sources": self.corroborating_sources,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Signal":
        return cls(
            kind=SignalKind(d["kind"]),
            claim=d["claim"],
            quote=d["quote"],
            source_id=d["source_id"],
            confidence=d["confidence"],
            direction=Direction(d.get("direction", "neutral")),
            corroborating_sources=d.get("corroborating_sources", []),
            id=d.get("id", uuid.uuid4().hex[:8]),
        )


@dataclass
class Material:
    """The unit of work passed through the harness. The worker reads `docs` and writes
    `signals`; the harness owns everything else."""
    run_id: str
    ticker: str
    docs: list[SourceDoc] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)

    def doc(self, source_id: str) -> SourceDoc | None:
        return next((d for d in self.docs if d.source_id == source_id), None)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "ticker": self.ticker,
            "docs": [d.to_dict() for d in self.docs],
            "signals": [s.to_dict() for s in self.signals],
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Material":
        return cls(
            run_id=d["run_id"],
            ticker=d["ticker"],
            docs=[SourceDoc.from_dict(x) for x in d.get("docs", [])],
            signals=[Signal.from_dict(x) for x in d.get("signals", [])],
            notes=d.get("notes", {}),
        )


@dataclass
class SignalReport:
    """The harness's final output artifact."""
    run_id: str
    ticker: str
    signals: list[Signal]
    escalations: list[dict] = field(default_factory=list)
    audit: list[dict] = field(default_factory=list)
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "ticker": self.ticker,
            "signals": [s.to_dict() for s in self.signals],
            "escalations": self.escalations,
            "audit": self.audit,
            "generated_at": self.generated_at,
        }
