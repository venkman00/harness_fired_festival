"""Claude-backed worker. Implements the same `Agent` protocol as MockAgent, so it drops
into the harness with zero changes. Uses tool-use for reliable structured output and
reports token usage + cost back through the AgentContext.

Pricing below is per-million-tokens, verified against the claude-api skill (2026-06-12).
Model ids are the current Claude family:
  - claude-opus-4-8   (default)   $5 / $25 per 1M in/out
  - claude-sonnet-4-6 (swap-in)   $3 / $15 per 1M in/out
"""
from __future__ import annotations

import json
import os

from ..material.types import Direction, Signal, SignalKind, SourceDoc
from .base import AgentContext

# $ per million tokens (input, output). Verified via claude-api skill 2026-06-12.
_PRICING = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
}

_SIGNAL_TOOL = {
    "name": "emit_signals",
    "description": "Emit investing signals extracted from the source documents.",
    "input_schema": {
        "type": "object",
        "properties": {
            "signals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string",
                                 "enum": [k.value for k in SignalKind]},
                        "claim": {"type": "string",
                                  "description": "one-sentence observation; NEVER advice"},
                        "quote": {"type": "string",
                                  "description": "EXACT verbatim substring from the source"},
                        "source_id": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "direction": {"type": "string",
                                      "enum": [d.value for d in Direction]},
                    },
                    "required": ["kind", "claim", "quote", "source_id", "confidence",
                                 "direction"],
                },
            }
        },
        "required": ["signals"],
    },
}

_SYSTEM = (
    "You are a buy-side research worker. Extract investing signals from the provided "
    "source documents. Rules: (1) every signal's `quote` MUST be an exact verbatim "
    "substring of the cited source — copy it character-for-character, never paraphrase; "
    "(2) report observations only — NEVER buy/sell/price-target/recommendation language; "
    "(3) set confidence honestly in [0,1]. Use the emit_signals tool."
)


def _loads(value):
    """json.loads a string if it is valid JSON; otherwise return the value unchanged."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


class ClaudeAgent:
    def __init__(self, model: str = "claude-opus-4-8", max_tokens: int = 8192):
        self.model = model
        self.name = f"claude:{model}"
        self.max_tokens = max_tokens
        from anthropic import Anthropic  # lazy: only required when this worker is used
        self._client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    def _prompt(self, docs: list[SourceDoc], ctx: AgentContext) -> str:
        blocks = [f"<source id=\"{d.source_id}\" type=\"{d.source_type.value}\">\n"
                  f"{d.text}\n</source>" for d in docs]
        parts = [f"Ticker: {ctx.ticker}", *blocks]
        if ctx.feedback:
            parts.append("HARNESS FEEDBACK (must address):\n- " + "\n- ".join(ctx.feedback))
        return "\n\n".join(parts)

    def extract_signals(self, docs: list[SourceDoc], ctx: AgentContext) -> list[Signal]:
        # streaming avoids HTTP timeouts and lets us recover a truncated tool call
        with self._client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=_SYSTEM,
            tools=[_SIGNAL_TOOL],
            tool_choice={"type": "tool", "name": "emit_signals"},
            messages=[{"role": "user", "content": self._prompt(docs, ctx)}],
        ) as stream:
            resp = stream.get_final_message()
        self._report_usage(resp, ctx)
        return self._parse(resp)

    def _parse(self, resp) -> list[Signal]:
        """Tolerant of every shape Claude has been observed to emit: input as dict or JSON
        string; signals as a list, a JSON-string array, or a list of JSON strings. Malformed
        fragments (e.g. a truncated tool call) are skipped, never fatal."""
        signals: list[Signal] = []
        for block in resp.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            data = _loads(block.input)
            raw_signals = data.get("signals", []) if isinstance(data, dict) else []
            raw_signals = _loads(raw_signals)
            if not isinstance(raw_signals, list):
                continue
            for raw in raw_signals:
                raw = _loads(raw)
                if not isinstance(raw, dict):
                    continue
                try:
                    signals.append(Signal(
                        kind=SignalKind(raw["kind"]),
                        claim=raw["claim"],
                        quote=raw["quote"],
                        source_id=raw["source_id"],
                        confidence=float(raw["confidence"]),
                        direction=Direction(raw.get("direction", "neutral")),
                    ))
                except (KeyError, ValueError, TypeError):
                    continue
        return signals

    def _report_usage(self, resp, ctx: AgentContext) -> None:
        u = getattr(resp, "usage", None)
        t_in = getattr(u, "input_tokens", 0) if u else 0
        t_out = getattr(u, "output_tokens", 0) if u else 0
        in_rate, out_rate = _PRICING.get(self.model, (0.0, 0.0))
        cost = t_in / 1e6 * in_rate + t_out / 1e6 * out_rate
        ctx.report_usage(tokens_in=t_in, tokens_out=t_out, cost_usd=cost)
