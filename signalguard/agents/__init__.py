"""Swappable worker. Any object implementing the `Agent` protocol drops in with zero
harness changes. The worker imports NONE of the four pillars — it only sees material in
(`SourceDoc`) and material out (`Signal`), steered by `AgentContext`."""
from .base import Agent, AgentContext
from .mock_agent import MockAgent

__all__ = ["Agent", "AgentContext", "MockAgent"]
