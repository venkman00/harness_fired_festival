"""Locks the four graded behaviors:
  1. grounding feedback loop changes the worker's output
  2. compliance guardrail blocks investment-advice + raises a CRITICAL alarm
  3. checkpoint persistence enables replay with no worker call
  4. swappable worker drops in with zero harness change
"""
from __future__ import annotations

import pytest

from signalguard.agents.base import AgentContext
from signalguard.agents.mock_agent import MockAgent
from signalguard.alarms.bus import AlarmBus
from signalguard.alarms.types import AlarmType
from signalguard.config import HarnessConfig
from signalguard.material.store import ArtifactStore
from signalguard.material.types import (Direction, Material, Signal, SignalKind,
                                        SourceDoc, SourceType)
from signalguard.orchestrator import replay, run

DOC_TEXT = (
    "For the third quarter, operating earnings increased to $11.2 billion. "
    "BNSF reported a decline in volumes and a decrease in net earnings to $1.3 billion. "
    "Berkshire Hathaway Energy delivered robust results with earnings up to $1.1 billion. "
    "Cash and short-term investments stood at a record $157 billion at quarter end. "
    "We expect underwriting margins to remain robust through the full year."
)


def _material(run_id="t-run"):
    doc = SourceDoc("earnings", SourceType.EARNINGS, "fixture.txt", DOC_TEXT)
    return Material(run_id=run_id, ticker="BRK.A", docs=[doc])


def _harness(tmp_path, run_id="t-run"):
    return dict(bus=AlarmBus(verbose=False),
                store=ArtifactStore(root=str(tmp_path)),
                config=HarnessConfig(min_report_tokens=20))


def test_grounding_loop_changes_output(tmp_path):
    h = _harness(tmp_path)
    report = run(_material(), MockAgent(simulate_hallucination=True), **h)
    # a grounding violation must have been raised on the first attempt
    assert h["bus"].by_type(AlarmType.GROUNDING_VIOLATION), "expected a GroundingViolation"
    # the worker was called more than once (re-extraction)
    assert report.audit and sum(1 for a in report.audit if a["event"] == "extract") >= 2
    # the final signal set is fully grounded
    for s in report.signals:
        assert _normalized(s.quote) in _normalized(DOC_TEXT)


def test_compliance_blocks_advice(tmp_path):
    class AdviceAgent:
        name, model = "advice", "test"

        def extract_signals(self, docs, ctx: AgentContext):
            ctx.report_usage(10, 10, 0.0)
            quote = "We expect underwriting margins to remain robust through the full year."
            return [Signal(kind=SignalKind.GUIDANCE,
                           claim="We recommend buying the stock here.",
                           quote=quote, source_id="earnings", confidence=0.9,
                           direction=Direction.BULLISH)]

    h = _harness(tmp_path)
    report = run(_material(), AdviceAgent(), **h)
    breaches = h["bus"].by_type(AlarmType.COMPLIANCE_BREACH)
    assert breaches and breaches[0].severity.value == "CRITICAL"
    # the offending signal is blocked from the report
    assert all("recommend buying" not in s.claim.lower() for s in report.signals)
    # critical alarm routed to a human
    assert h["bus"].needs_human()


def test_replay_uses_no_worker(tmp_path):
    h = _harness(tmp_path)
    run(_material(), MockAgent(), **h)
    replayed = replay("t-run", "synthesize",
                      config=h["config"], store=h["store"])
    extracts = [a for a in replayed.audit if a["event"] == "extract"]
    assert not extracts, "replay must not call the worker"
    assert len(replayed.signals) > 0


def test_swappable_worker(tmp_path):
    """A second worker with a different identity runs through the unchanged harness."""
    class SecondWorker(MockAgent):
        name, model = "second", "alt-v1"

    h = _harness(tmp_path)
    report = run(_material(), SecondWorker(simulate_hallucination=False), **h)
    assert report.signals
    assert all(_normalized(s.quote) in _normalized(DOC_TEXT) for s in report.signals)


def _normalized(s: str) -> str:
    import re
    return re.sub(r"\s+", " ", s).strip().lower()
