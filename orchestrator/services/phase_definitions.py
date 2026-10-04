"""Single per-phase definitions (WP8.3).

``orchestrator/phases/<phase>/phase.yaml`` holds the data that defines a Harper phase for the
local agent and, progressively, for the cloud path: write roots, required reads, output contract,
hard rules, validation expectations, prompt lines, canonical expectations. ``phases/_shared.yaml``
holds values common to several phases. Files are read once and returned as fresh copies, with
key order preserved (it is visible in the JSON written for the agent).
"""

from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import yaml

PHASES_DIR = Path(__file__).resolve().parents[1] / "phases"


@lru_cache(maxsize=None)
def _load(rel: str) -> Dict[str, Any]:
    path = PHASES_DIR / rel
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid phase definition: {path}")
    return data


def phase_definition(phase: str) -> Dict[str, Any]:
    """The phase.yaml of ``phase`` (a deep copy: callers may mutate it)."""
    return copy.deepcopy(_load(f"{phase}/phase.yaml"))


def shared_definitions() -> Dict[str, Any]:
    return copy.deepcopy(_load("_shared.yaml"))


def phase_text(target: str) -> Dict[str, List[str]]:
    """Static prompt/policy text of a phase (``phases/<target>/text.yaml``) or shared
    (``phases/_shared_text.yaml``). Callers copy the lists they use."""
    rel = "_shared_text.yaml" if target == "_shared" else f"{target}/text.yaml"
    return _load(rel)["text"]
