"""Declared checkpoint registry + canonical stage order (used by the replay engine)."""
from __future__ import annotations

from .stages import CP1_Ingest, CP2_Grounding, CP3_Synthesize

CHECKPOINTS = {
    "ingest": CP1_Ingest(),
    "grounding": CP2_Grounding(),
    "synthesize": CP3_Synthesize(),
}

# Order in which stages run; replay resumes from a named stage forward.
STAGE_ORDER = ["ingest", "grounding", "synthesize"]
