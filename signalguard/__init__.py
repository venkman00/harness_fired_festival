"""SignalGuard — a trust harness governing an AI agent that extracts grounded
investing signals from multi-source financial data.

The four pillars live in dedicated, worker-agnostic subpackages:
  - material/    clean typed interfaces in/out (the only thing the worker touches)
  - guardrails/  declared constraints checked around every agent call
  - checkpoints/ explicit pass/fail gates between stages, persisted for replay
  - alarms/      structured, named alarms with severity + recommended action

The worker lives in agents/ and imports none of the pillars.
"""

__version__ = "0.1.0"
