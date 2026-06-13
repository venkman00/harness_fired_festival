# Harness Planning Document — *SignalGuard*

**Engineer:** Venky Gangisetti · **Challenge:** 24-hour Build · **Date:** Fri Jun 12, 2026

## What it does
**SignalGuard** is a harness that governs an AI agent which reads **real multi-source data**
— an **earnings-call transcript**, a **podcast transcript**, and a **batch of X/Twitter posts**
— and emits **structured investing signals** (guidance changes, sentiment shifts, metric
surprises, risk flags), each with a verbatim evidence quote and a confidence score, plus
**cross-source corroboration** ("3 sources confirm margin pressure"). This is Cohesion's core
problem: analysts drown in non-traditional data and miss signals.

> **Thesis:** summarizing earnings is a red ocean. The moat — and the only reason a fund lets
> an agent run *autonomously* — is trust: it never fabricates, shows its evidence, refuses
> advice it can't give, and stops to ask when unsure. **That trust layer IS the harness.**
> The model is the engine; grounding, compliance, budgets, replay, and escalation are the car.

## The four pillars (each a distinct, identifiable component)

| Pillar | Module | What it enforces |
|---|---|---|
| **Guardrails** | `guardrails/` | *Declared, not implicit.* A registry of named rules checked around every agent call: (1) **EvidenceRequired** — every signal must cite a quote; (2) **NoInvestmentAdvice** — block "buy/sell/price-target" language (compliance); (3) **BudgetCap** — max tokens / tool-calls / cost per run; (4) **MNPI/PII** redaction on material in. |
| **Checkpoints** | `checkpoints/` | Explicit **pass/fail** gates between stages. **CP1 Ingest:** transcript parsed, has Q&A, > min tokens. **CP2 Extract:** schema-valid, confidence ∈ [0,1], **every quote substring-matches the transcript** (grounding). **CP3 Synthesize:** deduped, no contradictions, key sections covered. Each result is **persisted** → replayable. |
| **Material handling** | `material/` | Clean typed interfaces. Input adapter normalizes raw transcript (txt/json) → canonical `Transcript`. Agent never touches raw files; it receives typed material and returns a typed `SignalReport`. Harness owns serialization, redaction, and per-stage artifact storage. |
| **Alarms** | `alarms/` | **Structured output**: `{type, severity, context, recommended_action}`. Named types: `GroundingViolation`(HIGH→drop+re-extract), `ComplianceBreach`(CRITICAL→block+escalate), `BudgetExceeded`(MED→halt+escalate), `LowConfidenceCluster`(LOW→human review), `CheckpointFailure`(wraps a failed gate). |

## How the agent's behavior changes (the "Must")
The loop is **feedback-driven**. When **CP2** finds signals whose quotes don't match the
transcript, the harness raises a `GroundingViolation` and **feeds it back** to the agent:
*"these 3 signals lack valid evidence — re-extract with verbatim quotes."* The agent retries
and its output measurably changes. Likewise `NoInvestmentAdvice` forces a rephrase. Bounded
retries; on repeated failure the harness **stops and escalates to a human** (HITL).

## Swappable worker (Should + Bonus)
Workers implement one protocol: `Agent.run(material, context) -> material`. The harness knows
nothing about the model. Demo swaps **Claude Opus 4.8** (`claude-opus-4-8`) ⇄ **Sonnet 4.6**
(`claude-sonnet-4-6`) ⇄ a deterministic **MockAgent** — zero harness changes.

## Replay & HITL (Should)
Every stage writes `runs/<run_id>/<stage>.json`. A replay engine resumes from any checkpoint
without re-running prior stages. CRITICAL/HIGH alarms route to a human-review queue; the
harness pauses and asks rather than guessing.

## Architecture & stack
Python orchestrator (`harness.py`) running a staged loop: **Ingest → Extract → Synthesize**,
with guardrails wrapped around each agent call and a checkpoint gating each transition.
LLM via Anthropic SDK (default `claude-opus-4-8`, swappable). Deploy: thin **FastAPI** service
(`POST /run`, `GET /runs/<id>`) + minimal web view, hosted on Render/Modal for the demo URL.

```
material in → [Guardrail:in] → Agent.run → [Guardrail:out] → [Checkpoint] → persist
                    │                              │              │
                    └────────── Alarms ◄───────────┴── fail ──────┘  → retry / escalate(HITL)
```

## 24-hour plan  *(locked scope: Tier 0 spine + cross-source; real pre-captured data)*
**Tonight:** repo scaffold, four pillar modules + interfaces, MockAgent, end-to-end run on the
earnings transcript. **Sat AM:** Claude worker, grounding + compliance guardrails, the
feedback re-extraction loop, alarms + HITL, checkpoint persistence/replay. **Sat midday:**
cross-source fan-in (podcast + X) with corroboration, FastAPI + deploy, HARNESS.md,
second-worker swap demo, 5-min video.

## Risks / cuts
Single source (earnings) is the floor; cross-source corroboration is the differentiator and the
first stretch. UI degrades to CLI + JSON viewer if needed. Non-negotiable (it's what's graded):
*four separate pillars, the grounding feedback loop, persistence/replay, and worker-swap.*
