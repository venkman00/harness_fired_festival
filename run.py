#!/usr/bin/env python3
"""SignalGuard CLI.

  Run:     python run.py --ticker BRK.A --earnings data/earnings.txt --worker mock
  Replay:  python run.py --replay-from synthesize --run-id <id>
"""
from __future__ import annotations

import argparse

from signalguard.agents.mock_agent import MockAgent
from signalguard.config import HarnessConfig
from signalguard.material.adapters import build_material
from signalguard.material.types import SourceType
from signalguard.orchestrator import replay, run


def make_agent(name: str):
    if name == "mock":
        return MockAgent()
    if name in ("opus", "claude-opus-4-8"):
        from signalguard.agents.claude_agent import ClaudeAgent
        return ClaudeAgent(model="claude-opus-4-8")
    if name in ("sonnet", "claude-sonnet-4-6"):
        from signalguard.agents.claude_agent import ClaudeAgent
        return ClaudeAgent(model="claude-sonnet-4-6")
    raise SystemExit(f"unknown worker: {name!r} (try: mock | opus | sonnet)")


def main() -> None:
    ap = argparse.ArgumentParser(description="SignalGuard harness")
    ap.add_argument("--ticker", default="BRK.A")
    ap.add_argument("--earnings", help="path to earnings report / transcript (.txt)")
    ap.add_argument("--podcast", help="path to podcast transcript (.txt)")
    ap.add_argument("--x", dest="x_posts", help="path to X posts (.json)")
    ap.add_argument("--worker", default="mock", help="mock | opus | sonnet")
    ap.add_argument("--replay-from", help="replay a persisted run from this stage")
    ap.add_argument("--run-id", help="run id to replay")
    args = ap.parse_args()

    if args.replay_from:
        if not args.run_id:
            raise SystemExit("--replay-from requires --run-id")
        replay(args.run_id, args.replay_from)
        return

    sources = []
    if args.earnings:
        sources.append((SourceType.EARNINGS, args.earnings))
    if args.podcast:
        sources.append((SourceType.PODCAST, args.podcast))
    if args.x_posts:
        sources.append((SourceType.X_POSTS, args.x_posts))
    if not sources:
        raise SystemExit("provide at least --earnings <path>")

    material = build_material(args.ticker, sources)
    run(material, make_agent(args.worker), HarnessConfig())


if __name__ == "__main__":
    main()
