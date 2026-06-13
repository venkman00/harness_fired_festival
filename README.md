# SignalGuard

A **trust harness** that governs an AI agent extracting **grounded investing signals** from
multi-source financial data (earnings reports, podcasts, X/Twitter). Built for the Fired
Festival 24-hour Build Challenge; designed as a vertical slice of Cohesion's core product.

> The model is the engine; the harness is the car. Grounding, compliance, budgets, replay,
> observability, and escalation live in the harness — never in the prompt.

## The pillars (each a distinct package, separate from the worker)

| Pillar | Package | Role |
|---|---|---|
| Material handling | `signalguard/material/` | typed material in/out; the worker never touches raw files |
| Guardrails | `signalguard/guardrails/` | declared registry: Evidence, NoInvestmentAdvice, BudgetCap, Redaction |
| Checkpoints | `signalguard/checkpoints/` | pass/fail gates: ingest → **grounding** → synthesize (persisted, replayable) |
| Alarms | `signalguard/alarms/` | 5 structured types with severity + recommended action, routed to HITL |
| Observability | `signalguard/observability/` | OTEL spans with cost / latency / token attributes (no lock-in) |
| Worker (swappable) | `signalguard/agents/` | `Agent` protocol; MockAgent + ClaudeAgent, zero harness change to swap |

## Quickstart (no API key needed — uses the deterministic mock worker)

```bash
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python run.py --ticker BRK.A --earnings data/earnings_sample.txt --worker mock
```

You'll see the **grounding feedback loop** in action: attempt 0 proposes a fabricated quote,
the grounding checkpoint fails, a `GroundingViolation` alarm fires and is fed back, and the
worker re-extracts with verbatim evidence on attempt 1.

### Replay a run from a checkpoint (no worker call)

```bash
.venv/bin/python run.py --replay-from synthesize --run-id <run_id_from_runs_dir>
```

### Run on a real Berkshire filing with Claude

```bash
export ANTHROPIC_API_KEY=sk-...
# put a real 10-Q / press release at data/earnings.txt
.venv/bin/python run.py --ticker BRK.A --earnings data/earnings.txt --worker opus
```

## Tests

```bash
.venv/bin/python -m pytest -q
```

Covers the four graded behaviors: grounding feedback loop, compliance block (CRITICAL + HITL),
replay without re-calling the worker, and worker swap.

See `HARNESS.md` for the full architecture and design (coming Saturday) and `PLANNING.md` for
the planning document.
