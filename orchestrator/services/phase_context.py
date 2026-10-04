"""PhaseContext v1: the typed contract of a Harper phase run (WP8.4).

Until now the orchestrator → gateway contract was an untyped "virtual filesystem": a
``core_blobs: Dict[str, str]`` whose entries the gateway recognizes by name or suffix. PhaseContext
gives that contract a schema and a version without changing the wire format:

* every blob is classified (``BlobKind``) with the same name rules the gateway applies, JSON
  blobs (target contract, file requirements, plan.json, ...) are parsed when valid;
* ``to_core_blobs()`` reproduces the original mapping exactly, key order included (order drives
  the gateway's "Included references" section), so the wire bytes do not change;
* the JSON Schema is exported to ``docs/contracts/phase_context.v1.schema.json``.

Later steps render prompts from this object (cloud and local agent) instead of re-parsing blobs.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "clike.phase_context.v1"


class BlobKind(str, Enum):
    canonical_document = "canonical_document"  # IDEA.md, SPEC.md, PLAN.md, lane guides
    plan_json = "plan_json"
    tech_constraints = "tech_constraints"
    target_contract = "target_contract"
    file_requirements = "file_requirements"
    repo_manifest = "repo_manifest"  # REPO_ACCESS / REPO_STRUCTURE / REPO_COMPOSITION
    req_promotion_manifest = "req_promotion_manifest"
    capability_manifest = "capability_manifest"
    capability_index = "capability_index"
    selected_capability_context = "selected_capability_context"
    candidate = "candidate"  # candidate::<path>, KIT stage inputs
    companion = "companion"  # companion::<path>, BMAD/UX companion documents
    methodology_vendor = "methodology_vendor"  # .clike/skills/vendor/<methodology>/**
    workspace_reference = "workspace_reference"  # any other workspace file


_JSON_KINDS = {
    BlobKind.plan_json,
    BlobKind.target_contract,
    BlobKind.file_requirements,
    BlobKind.capability_index,
    BlobKind.selected_capability_context,
}


def classify_blob(name: str) -> BlobKind:
    """Kind of a core blob, by the same name/suffix rules the gateway uses."""
    lower = str(name or "").strip().lower()
    base = lower.rsplit("/", 1)[-1]
    if lower.startswith("candidate::"):
        return BlobKind.candidate
    if lower.startswith("companion::"):
        return BlobKind.companion
    if lower.startswith(".clike/skills/vendor/"):
        return BlobKind.methodology_vendor
    if lower.endswith("target_contract.json"):
        return BlobKind.target_contract
    if lower.endswith("file_requirements.json"):
        return BlobKind.file_requirements
    if base.startswith("clike_selected_capability_context"):
        return BlobKind.selected_capability_context
    if base.startswith("clike_capability_index"):
        return BlobKind.capability_index
    if base.startswith("clike_capability_manifest"):
        return BlobKind.capability_manifest
    if base.startswith(("repo_access_manifest", "repo_structure_evidence", "repo_composition_manifest")):
        return BlobKind.repo_manifest
    if base.startswith("req_promotion_manifest"):
        return BlobKind.req_promotion_manifest
    if lower.endswith("plan.json"):
        return BlobKind.plan_json
    if base.startswith("tech_constraints"):
        return BlobKind.tech_constraints
    if base in {"idea.md", "spec.md", "plan.md"} or "/lane-guides/" in f"/{lower}":
        return BlobKind.canonical_document
    return BlobKind.workspace_reference


class PhaseBlob(BaseModel):
    """One entry of the wire ``core_blobs`` mapping."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Key in core_blobs (workspace-relative path or synthesized name).")
    kind: BlobKind
    content: str = Field(description="Raw content, sent unchanged.")
    data: Optional[Any] = Field(default=None, description="Parsed JSON for JSON kinds, when the content is valid JSON.")


class PhaseContext(BaseModel):
    """Everything a phase run receives as context, typed and versioned."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=SCHEMA_VERSION)
    phase: str
    run_id: Optional[str] = None
    req_id: Optional[str] = Field(default=None, description="Target REQ for REQ-scoped phases (kit, eval).")
    methodology: Optional[str] = None
    agent: Optional[str] = None
    blobs: List[PhaseBlob] = Field(default_factory=list, description="Blobs in wire order.")

    # --- construction / wire ---------------------------------------------------------------

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "PhaseContext":
        raw = payload.get("core_blobs") or {}
        if not isinstance(raw, dict):
            raise TypeError("core_blobs must be a mapping of name -> text")
        blobs: List[PhaseBlob] = []
        for name, content in raw.items():
            if not isinstance(name, str) or not isinstance(content, str):
                raise TypeError(f"core_blobs entries must be text: {name!r}")
            kind = classify_blob(name)
            data = None
            if kind in _JSON_KINDS:
                try:
                    data = json.loads(content)
                except ValueError:
                    data = None
            blobs.append(PhaseBlob(name=name, kind=kind, content=content, data=data))
        targets = ((payload.get("kit") or {}).get("targets") if isinstance(payload.get("kit"), dict) else None) or []
        return cls(
            phase=str(payload.get("phase") or payload.get("cmd") or ""),
            run_id=payload.get("runId"),
            req_id=str(targets[0]) if targets else None,
            methodology=payload.get("methodology"),
            agent=payload.get("agent"),
            blobs=blobs,
        )

    def to_core_blobs(self) -> Dict[str, str]:
        """The wire mapping, identical to the one the context was built from (order included)."""
        return {blob.name: blob.content for blob in self.blobs}

    # --- typed accessors -------------------------------------------------------------------

    def of_kind(self, kind: BlobKind) -> List[PhaseBlob]:
        return [blob for blob in self.blobs if blob.kind == kind]

    def _first_data(self, kind: BlobKind) -> Optional[Any]:
        for blob in self.of_kind(kind):
            return blob.data
        return None

    @property
    def target_contract(self) -> Optional[Dict[str, Any]]:
        data = self._first_data(BlobKind.target_contract)
        return data if isinstance(data, dict) else None

    @property
    def file_requirements(self) -> Optional[Dict[str, Any]]:
        data = self._first_data(BlobKind.file_requirements)
        return data if isinstance(data, dict) else None

    @property
    def plan(self) -> Optional[Dict[str, Any]]:
        data = self._first_data(BlobKind.plan_json)
        return data if isinstance(data, dict) else None

    @property
    def canonical_documents(self) -> Dict[str, str]:
        return {blob.name: blob.content for blob in self.of_kind(BlobKind.canonical_document)}

    @property
    def candidates(self) -> Dict[str, str]:
        return {blob.name.split("::", 1)[1]: blob.content for blob in self.of_kind(BlobKind.candidate)}


def phase_context_json_schema() -> Dict[str, Any]:
    schema = PhaseContext.model_json_schema()
    schema["$id"] = f"https://github.com/authenticfake/clike/docs/contracts/{SCHEMA_VERSION}.schema.json"
    schema["title"] = "CLike PhaseContext v1"
    return schema
