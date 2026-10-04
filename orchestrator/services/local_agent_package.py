"""Local-agent execution packages (facade).

The implementation lives in ``services/local_agent/`` (WP8.5), one module per phase plus shared
helpers; phase data lives in ``orchestrator/phases/``. This module keeps the historical import
path for callers and tests.
"""

from services.local_agent.common import _materialize_attachments, resolve_local_executor
from services.local_agent.document import (
    _DOCUMENT_PHASE_CANONICAL_EXPECTATIONS,
    _DOCUMENT_PHASE_SPECS,
    _path_accepted,
    build_document_phase_local_agent_package,
)
from services.local_agent.eval import build_eval_local_agent_package
from services.local_agent.extend import build_extend_local_agent_package
from services.local_agent.finalize import build_finalize_local_agent_package
from services.local_agent.kit import build_kit_local_agent_package
from services.local_agent.normalize import normalize_local_agent_result

__all__ = [
    "build_document_phase_local_agent_package",
    "build_eval_local_agent_package",
    "build_extend_local_agent_package",
    "build_finalize_local_agent_package",
    "build_kit_local_agent_package",
    "normalize_local_agent_result",
    "resolve_local_executor",
    "_DOCUMENT_PHASE_CANONICAL_EXPECTATIONS",
    "_DOCUMENT_PHASE_SPECS",
    "_materialize_attachments",
    "_path_accepted",
]
