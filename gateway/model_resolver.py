from typing import List, Dict

def resolve_model(models_list: List[Dict], name_or_auto: str, want_modality: str | None = None) -> Dict:
    candidates = [m for m in models_list if m.get("enabled", True)]
    if want_modality:
        candidates = [m for m in candidates if m.get("modality") == want_modality]
    if not candidates:
        raise RuntimeError("no enabled models matching filters")

    if name_or_auto != "auto":
        for m in candidates:
            if m.get("name") == name_or_auto:
                return m
        raise RuntimeError(f"model '{name_or_auto}' not found or disabled")

    def is_local(m): 
        return (m.get("provider") or "").lower() in {"ollama", "vllm"}
    locals_first = [m for m in candidates if is_local(m)] or candidates

    def cap_score(m):
        cap = (m.get("capability") or "medium").lower()
        return {"high": 0, "medium": 1, "low": 2}.get(cap, 1)

    locals_first.sort(key=cap_score)
    return locals_first[0]
