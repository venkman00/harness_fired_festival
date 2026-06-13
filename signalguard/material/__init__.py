"""Material-handling pillar: clean typed interfaces for passing material in and out.

The worker only ever sees `SourceDoc` / `Signal` objects — never raw files, paths, or
storage. The harness owns normalization, redaction, serialization, and persistence.
"""
from .types import (
    SourceType,
    SignalKind,
    Direction,
    SourceDoc,
    Signal,
    Material,
    SignalReport,
)

__all__ = [
    "SourceType",
    "SignalKind",
    "Direction",
    "SourceDoc",
    "Signal",
    "Material",
    "SignalReport",
]
