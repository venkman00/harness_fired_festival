"""Artifact store — persists every stage's output to runs/<run_id>/<stage>.json.

This is what makes runs auditable and replayable: each checkpoint snapshot is written
to disk, so a run can be resumed from any stage forward without re-running prior stages
(and, crucially, without re-calling the worker)."""
from __future__ import annotations

import json
import os
from typing import Any


def _default(o: Any):
    if hasattr(o, "to_dict"):
        return o.to_dict()
    if isinstance(o, set):
        return sorted(o)
    if hasattr(o, "value"):  # Enum
        return o.value
    raise TypeError(f"not JSON-serializable: {type(o)}")


class ArtifactStore:
    def __init__(self, root: str = "runs"):
        self.root = root

    def _dir(self, run_id: str) -> str:
        d = os.path.join(self.root, run_id)
        os.makedirs(d, exist_ok=True)
        return d

    def save(self, run_id: str, stage: str, obj: Any) -> str:
        path = os.path.join(self._dir(run_id), f"{stage}.json")
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(obj, f, indent=2, default=_default)
        os.replace(tmp, path)  # atomic — progress polling never sees a partial file
        return path

    def load(self, run_id: str, stage: str) -> Any:
        with open(os.path.join(self.root, run_id, f"{stage}.json")) as f:
            return json.load(f)

    def exists(self, run_id: str, stage: str) -> bool:
        return os.path.exists(os.path.join(self.root, run_id, f"{stage}.json"))

    def stages(self, run_id: str) -> list[str]:
        d = os.path.join(self.root, run_id)
        if not os.path.isdir(d):
            return []
        return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json"))
