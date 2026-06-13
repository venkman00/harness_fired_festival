"""The harness orchestrator — the only place that knows about all the pillars. It owns the
staged loop and makes constraint-handling invisible to the worker:

    Ingest (CP1) → [PRE guardrails] → Extract loop (POST guardrails + CP2 grounding, with
    feedback-driven re-extraction) → low-confidence scan → Synthesize (corroboration + CP3)

Every worker call is wrapped in a telemetry span; every stage result is persisted; every
failure raises a structured alarm and, when severe, routes to a human."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .agents.base import Agent, AgentContext
from .alarms.bus import AlarmBus
from .alarms.types import AlarmType, Severity
from .checkpoints.registry import CHECKPOINTS
from .config import HarnessConfig
from .guardrails.registry import post_guardrails, pre_guardrails
from .guardrails.rules import BudgetCap
from .material.store import ArtifactStore
from .material.types import Material, Signal, SignalReport
from .observability.tracing import Telemetry


@dataclass
class RunState:
    run_id: str
    ticker: str
    config: HarnessConfig
    bus: AlarmBus
    store: ArtifactStore
    telemetry: Telemetry
    agent_calls: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0
    audit: list = field(default_factory=list)

    def log(self, event: str, **data) -> None:
        self.audit.append({"t": round(time.time(), 3), "event": event, **data})


# --------------------------------------------------------------------------- #
#  Main entry: run()
# --------------------------------------------------------------------------- #
def run(material: Material, agent: Agent, config: HarnessConfig | None = None,
        bus: AlarmBus | None = None, store: ArtifactStore | None = None,
        telemetry: Telemetry | None = None) -> SignalReport:
    config = config or HarnessConfig()
    bus = bus or AlarmBus()
    store = store or ArtifactStore()
    telemetry = telemetry or Telemetry()
    st = RunState(material.run_id, material.ticker, config, bus, store, telemetry)

    print(f"\n=== SignalGuard · run {st.run_id} · {st.ticker} · "
          f"worker={agent.name} ({agent.model}) ===")

    with telemetry.span("harness.run", **{"run.id": st.run_id, "ticker": st.ticker,
                                          "worker": agent.name}):
        # ---- Stage 1: Ingest (CP1) -------------------------------------- #
        cp1 = _checkpoint(st, "ingest", material)
        if not cp1.passed:
            bus.raise_alarm(
                AlarmType.CHECKPOINT_FAILURE, Severity.HIGH,
                context={"checkpoint": "ingest",
                         "failed": [c for c, p in cp1.criteria if not p]},
                recommended_action="halt: input failed ingestion gate; human to verify source")
            return _finalize(st, material, halted=True)

        # ---- PRE guardrails (redaction, budget) ------------------------- #
        for g in pre_guardrails():
            res = _guardrail(st, g, material)
            if not res.passed:  # only BudgetCap can fail here
                bus.raise_alarm(AlarmType.BUDGET_EXCEEDED, Severity.MEDIUM,
                                context={"detail": res.detail},
                                recommended_action=res.recommended_action)
                return _finalize(st, material, halted=True)

        # snapshot redacted material so replay needs no re-ingest / re-call
        store.save(st.run_id, "material", material.to_dict())

        # ---- Stage 2: Extract loop with grounding feedback -------------- #
        ctx = AgentContext(stage="extract", ticker=material.ticker)
        grounded = _extract_loop(st, material, agent, ctx)
        if not grounded:
            bus.raise_alarm(
                AlarmType.CHECKPOINT_FAILURE, Severity.HIGH,
                context={"checkpoint": "grounding",
                         "attempts": config.max_extract_retries + 1},
                recommended_action="could not ground signals after retries; escalate to analyst")

        # ---- Low-confidence cluster ------------------------------------- #
        low = [s for s in material.signals if s.confidence < config.low_confidence_threshold]
        if len(low) >= config.low_confidence_cluster_size:
            bus.raise_alarm(
                AlarmType.LOW_CONFIDENCE_CLUSTER, Severity.LOW,
                context={"signal_ids": [s.id for s in low],
                         "threshold": config.low_confidence_threshold},
                recommended_action="route low-confidence signals to analyst for review (HITL)")

        # ---- Stage 3: Synthesize (corroboration + CP3) ------------------ #
        _corroborate(material)
        cp3 = _checkpoint(st, "synthesize", material)
        if not cp3.passed:
            bus.raise_alarm(
                AlarmType.CHECKPOINT_FAILURE, Severity.MEDIUM,
                context={"checkpoint": "synthesize",
                         "failed": [c for c, p in cp3.criteria if not p]},
                recommended_action="synthesis coverage thin; analyst review recommended")

        return _finalize(st, material)


def _extract_loop(st: RunState, material: Material, agent: Agent,
                  ctx: AgentContext) -> bool:
    """Returns True once the worker's output passes CP2 grounding with no compliance block."""
    for attempt in range(st.config.max_extract_retries + 1):
        ctx.attempt = attempt

        # budget gate before every (potentially paid) worker call
        budget = _guardrail(st, BudgetCap(), material)
        if not budget.passed:
            st.bus.raise_alarm(AlarmType.BUDGET_EXCEEDED, Severity.MEDIUM,
                               context={"detail": budget.detail},
                               recommended_action=budget.recommended_action)
            return False

        # ---- the worker call, wrapped in a telemetry span ---- #
        with st.telemetry.span("agent.extract", **{"llm.model": agent.model,
                                                    "attempt": attempt}) as span:
            signals = agent.extract_signals(material.docs, ctx)
            span.set("llm.tokens_in", ctx.tokens_in)
            span.set("llm.tokens_out", ctx.tokens_out)
            span.set("llm.cost_usd", ctx.cost_usd)
            span.set("signals", len(signals))
        st.agent_calls += 1
        st.tokens_used += ctx.tokens_in + ctx.tokens_out
        st.cost_usd += ctx.cost_usd
        material.signals = signals
        st.log("extract", attempt=attempt, n_signals=len(signals),
               cost_usd=round(ctx.cost_usd, 6))
        print(f"\n  [extract] attempt {attempt}: {len(signals)} signal(s) proposed "
              f"(+${ctx.cost_usd:.4f})")

        # ---- POST guardrails ---- #
        compliance_blocked = False
        for g in post_guardrails():
            res = _guardrail(st, g, material)
            _print_guardrail(res)
            if res.passed:
                continue
            if g.name == "NoInvestmentAdvice":
                material.signals = [s for s in material.signals
                                    if s.id not in res.flagged_signal_ids]
                st.bus.raise_alarm(
                    AlarmType.COMPLIANCE_BREACH, Severity.CRITICAL,
                    context={"blocked_signal_ids": res.flagged_signal_ids,
                             "detail": res.detail},
                    recommended_action="block flagged signals + route to compliance (HITL)")
                ctx.feedback.append("Do NOT include buy/sell/price-target or recommendation "
                                    "language. Report observations only.")
                compliance_blocked = True
            elif g.name == "EvidenceRequired":
                material.signals = [s for s in material.signals
                                    if s.id not in res.flagged_signal_ids]

        # ---- Checkpoint 2: grounding ---- #
        cp2 = _checkpoint(st, "grounding", material)
        if cp2.passed and not compliance_blocked:
            return True

        # ---- feed grounding failure back → re-extract ---- #
        ungrounded = cp2.data.get("ungrounded_ids", [])
        if ungrounded:
            examples = [s.quote[:70] for s in material.signals if s.id in ungrounded]
            st.bus.raise_alarm(
                AlarmType.GROUNDING_VIOLATION, Severity.HIGH,
                context={"ungrounded_ids": ungrounded, "examples": examples,
                         "attempt": attempt},
                recommended_action="drop fabricated quotes + re-extract with verbatim evidence")
            material.signals = [s for s in material.signals if s.id not in ungrounded]
            ctx.feedback.append(
                f"{len(ungrounded)} quote(s) were NOT found verbatim in the source and were "
                "rejected. Re-extract using ONLY exact substrings copied from the document.")
        if attempt < st.config.max_extract_retries:
            print("  ↻ feeding feedback to worker, re-extracting…")
    return False


# --------------------------------------------------------------------------- #
#  Replay: resume from a persisted checkpoint without re-running prior stages
# --------------------------------------------------------------------------- #
def replay(run_id: str, from_stage: str, config: HarnessConfig | None = None,
           store: ArtifactStore | None = None) -> SignalReport:
    config = config or HarnessConfig()
    store = store or ArtifactStore()
    bus = AlarmBus()
    telemetry = Telemetry()

    material = Material.from_dict(store.load(run_id, "material"))
    # reuse the signals that were persisted at (or before) the requested stage
    snap_stage = "grounding" if from_stage == "synthesize" else from_stage
    if store.exists(run_id, snap_stage):
        snap = store.load(run_id, snap_stage)
        material.signals = [Signal.from_dict(s) for s in snap.get("signals", [])]

    st = RunState(run_id, material.ticker, config, bus, store, telemetry)
    print(f"\n=== REPLAY · run {run_id} · resuming from '{from_stage}' (no worker call) ===")

    if from_stage in ("grounding", "synthesize"):
        if from_stage == "grounding":
            _checkpoint(st, "grounding", material)
        _corroborate(material)
        _checkpoint(st, "synthesize", material)
        return _finalize(st, material, replayed_from=from_stage)
    raise ValueError(f"cannot replay from stage '{from_stage}'")


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def _checkpoint(st: RunState, stage: str, material: Material):
    with st.telemetry.span(f"checkpoint.{stage}"):
        cp = CHECKPOINTS[stage].evaluate(material, st)
    st.store.save(st.run_id, stage, {
        "checkpoint": cp.to_dict(),
        "ticker": material.ticker,
        "signals": [s.to_dict() for s in material.signals],
    })
    st.log("checkpoint", stage=stage, passed=cp.passed)
    _print_cp(cp)
    return cp


def _guardrail(st: RunState, g, material: Material):
    res = g.check(material, st)
    st.store.save(st.run_id, f"guardrail_{g.name}", res.to_dict())
    st.log("guardrail", name=g.name, passed=res.passed, detail=res.detail)
    return res


def _corroborate(material: Material) -> None:
    """Cross-source corroboration: a signal is corroborated by signals of the same kind and
    direction drawn from a *different* source document."""
    for s in material.signals:
        s.corroborating_sources = sorted({
            o.source_id for o in material.signals
            if o.id != s.id and o.kind == s.kind and o.direction == s.direction
            and o.source_id != s.source_id
        })


def _finalize(st: RunState, material: Material, halted: bool = False,
              replayed_from: str | None = None) -> SignalReport:
    report = SignalReport(
        run_id=st.run_id, ticker=material.ticker, signals=material.signals,
        escalations=[a.to_dict() for a in st.bus.hitl_queue], audit=st.audit,
    )
    payload = report.to_dict()
    payload["alarms"] = st.bus.to_dict()
    payload["telemetry"] = st.telemetry.to_dict()
    payload["halted"] = halted
    payload["replayed_from"] = replayed_from
    st.store.save(st.run_id, "report", payload)
    _print_summary(st, report, halted)
    return report


# ------------------------------- printing ---------------------------------- #
def _print_cp(cp) -> None:
    mark = "✓ PASS" if cp.passed else "✗ FAIL"
    print(f"\n  [checkpoint:{cp.name}] {mark} — {cp.detail}")
    for crit, ok in cp.criteria:
        print(f"      {'✓' if ok else '✗'} {crit}")


def _print_guardrail(res) -> None:
    mark = "✓" if res.passed else "✗"
    print(f"  [guardrail:{res.name}] {mark} {res.detail}")


def _print_summary(st: RunState, report: SignalReport, halted: bool) -> None:
    t = st.telemetry.totals
    print("\n" + "─" * 64)
    print(f"  RESULT: {'HALTED' if halted else 'COMPLETE'} · "
          f"{len(report.signals)} signal(s) · {len(st.bus.alarms)} alarm(s) · "
          f"{len(st.bus.hitl_queue)} HITL escalation(s)")
    print(f"  OBSERVABILITY: {t['llm_calls']} worker call(s) · "
          f"{t['tokens_in'] + t['tokens_out']} tokens · ${t['cost_usd']:.4f} · "
          f"{t['latency_s']:.3f}s")
    for s in report.signals:
        corr = f"  [+{len(s.corroborating_sources)} corroborating]" if s.corroborating_sources else ""
        print(f"    • ({s.confidence:.2f}) {s.claim}{corr}")
    if st.bus.needs_human():
        print(f"  ⚑ {len(st.bus.hitl_queue)} item(s) awaiting human review")
    print("─" * 64)
