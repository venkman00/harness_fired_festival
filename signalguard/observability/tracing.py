"""Telemetry: OTEL-compatible span recording for the harness.

Each model/tool call and each stage is wrapped in a span with standard attributes
(`llm.model`, `llm.tokens_in`, `llm.tokens_out`, `llm.cost_usd`, `duration_s`). If the
`opentelemetry` SDK is installed we emit real spans (console exporter by default, swap in
any OTLP backend with one env var — no rewrite). If it is not installed we still record
every span in-process, so cost/latency/token tracking and the audit trail work unchanged."""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

try:  # optional dependency — no lock-in, graceful fallback
    from opentelemetry import trace as _otel_trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )
    _OTEL_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only when SDK absent
    _OTEL_AVAILABLE = False


@dataclass
class SpanRecord:
    """An in-process record of one span — works with or without the OTEL SDK."""
    name: str
    attributes: dict = field(default_factory=dict)
    duration_s: float = 0.0

    def set(self, key: str, value) -> None:
        self.attributes[key] = value

    def to_dict(self) -> dict:
        return {"name": self.name, "duration_s": round(self.duration_s, 4),
                "attributes": self.attributes}


def _build_tracer(service: str):
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:  # any OTLP backend ingests it — pick your stack, no code change
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    else:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    _otel_trace.set_tracer_provider(provider)
    return _otel_trace.get_tracer(service)


class Telemetry:
    def __init__(self, service: str = "signalguard", enable_otel: bool = True):
        self.spans: list[SpanRecord] = []
        self.totals = {
            "llm_calls": 0, "tokens_in": 0, "tokens_out": 0,
            "cost_usd": 0.0, "latency_s": 0.0,
        }
        self.enabled_otel = bool(enable_otel and _OTEL_AVAILABLE)
        self._tracer = _build_tracer(service) if self.enabled_otel else None

    @contextmanager
    def span(self, name: str, **attrs):
        """Open a span. The yielded SpanRecord can have attributes set during the call
        (e.g. token usage that is only known after the model returns)."""
        rec = SpanRecord(name=name, attributes=dict(attrs))
        start = time.perf_counter()
        otel_cm = otel_span = None
        if self._tracer is not None:
            otel_cm = self._tracer.start_as_current_span(name)
            otel_span = otel_cm.__enter__()
        try:
            yield rec
        finally:
            rec.duration_s = time.perf_counter() - start
            if otel_span is not None:
                for k, v in rec.attributes.items():
                    otel_span.set_attribute(k, v)
                otel_span.set_attribute("duration_s", rec.duration_s)
                otel_cm.__exit__(None, None, None)
            self.spans.append(rec)
            self._accumulate(rec)

    def _accumulate(self, rec: SpanRecord) -> None:
        a = rec.attributes
        self.totals["latency_s"] += rec.duration_s
        if "llm.tokens_in" in a or "llm.tokens_out" in a:
            self.totals["llm_calls"] += 1
            self.totals["tokens_in"] += int(a.get("llm.tokens_in", 0))
            self.totals["tokens_out"] += int(a.get("llm.tokens_out", 0))
            self.totals["cost_usd"] += float(a.get("llm.cost_usd", 0.0))

    def to_dict(self) -> dict:
        return {
            "otel_emitting": self.enabled_otel,
            "totals": {**self.totals,
                       "cost_usd": round(self.totals["cost_usd"], 6),
                       "latency_s": round(self.totals["latency_s"], 4)},
            "spans": [s.to_dict() for s in self.spans],
        }
