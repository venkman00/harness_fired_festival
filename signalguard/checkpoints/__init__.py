"""Checkpoints pillar: explicit pass/fail gates between stages.

Each checkpoint returns a CheckpointResult with a boolean `passed` and an itemized list
of (criterion, passed) pairs — never an implicit judgment. Results are persisted by the
orchestrator so a run can be replayed from any checkpoint forward."""
from .base import Checkpoint, CheckpointResult
from .registry import CHECKPOINTS, STAGE_ORDER

__all__ = ["Checkpoint", "CheckpointResult", "CHECKPOINTS", "STAGE_ORDER"]
