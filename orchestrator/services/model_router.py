from __future__ import annotations

from typing import Dict, Any, Optional

from services.router import _load_cfg, resolve


def choose_model(
    task: str = "codegen",
    modality: Optional[str] = "chat",
    name_or_auto: str = "auto",
) -> Dict[str, Any]:
    """
    Legacy compatibility shim.
    Delegates routing to the shared resolver via services.router.resolve(...).
    """
    chosen, _warnings = resolve(
        task=task,
        hint=None,
        model=name_or_auto,
        provider=None,
    )

    if modality:
        wanted = str(modality).strip().lower()
        current = str(chosen.get("modality") or "chat").strip().lower()
        if wanted in {"embed", "embedding", "embeddings"} and current not in {"embed", "embedding", "embeddings"}:
            raise RuntimeError(f"resolved model '{chosen.get('name') or chosen.get('id')}' is not an embedding model")

    return chosen