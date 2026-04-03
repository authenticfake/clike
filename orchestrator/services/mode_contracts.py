from __future__ import annotations

from typing import Any, Dict, Optional


def normalize_mode_contract(payload_contract: Optional[Dict[str, Any]], fallback: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    base = dict(fallback or {})
    if isinstance(payload_contract, dict):
        for k, v in payload_contract.items():
            base[k] = v
    return base


def validate_chat_contract(contract: Dict[str, Any]) -> None:
    mode = str(contract.get("mode") or "free").lower()
    allow_file_output = bool(contract.get("allow_file_output", False))
    require_phase_artifacts = bool(contract.get("require_phase_artifacts", False))

    if mode == "free":
        if allow_file_output:
            raise ValueError("free mode cannot allow file output")
        if require_phase_artifacts:
            raise ValueError("free mode cannot require phase artifacts")


def apply_generate_contract(
    *,
    payload: Dict[str, Any],
    provider: str,
    contract: Dict[str, Any],
    files_bundle_schema: Dict[str, Any],
    emit_files_tool: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(payload)
    mode = str(contract.get("mode") or "coding").lower()
    allow_file_output = bool(contract.get("allow_file_output", False))
    prefer_tools = bool(contract.get("prefer_tools", True))
    prefer_response_format = bool(contract.get("prefer_response_format", True))

    if not allow_file_output:
        raise ValueError(f"mode '{mode}' does not allow file output")

    prov = str(provider or "").lower().strip()
    response_format_providers = {"openai", "azure_openai"}
    tool_call_providers = {"ollama", "anthropic", "deepseek", "vllm"}

    out.pop("tools", None)
    out.pop("tool_choice", None)
    out.pop("response_format", None)

    model_name = str(out.get("model") or "").lower()
    is_gpt5_family = model_name.startswith("openai:gpt-5") or model_name.startswith("gpt-5")

    # GPT-5 / Responses-family models are more reliable with tool calling for coding output.
    if prov in response_format_providers and prefer_response_format and not is_gpt5_family:
        out["response_format"] = {
            "type": "json_schema",
            "json_schema": files_bundle_schema,
        }
        return out

    if (prov in response_format_providers and is_gpt5_family and prefer_tools) or (prov in tool_call_providers and prefer_tools):
        out["tools"] = [emit_files_tool]
        out["tool_choice"] = {"type": "function", "function": {"name": "emit_files"}}
        return out

    if prov in tool_call_providers and prefer_tools:
        out["tools"] = [emit_files_tool]
        out["tool_choice"] = {"type": "function", "function": {"name": "emit_files"}}
        return out

    # Conservative fallback:
    # if provider family is unknown, use response_format only when explicitly preferred.
    if prefer_response_format:
        out["response_format"] = {
            "type": "json_schema",
            "json_schema": files_bundle_schema,
        }
    elif prefer_tools:
        out["tools"] = [emit_files_tool]
        out["tool_choice"] = {"type": "function", "function": {"name": "emit_files"}}

    return out


def sanitize_gateway_chat_payload(
    *,
    provider: str,
    mode_contract: Optional[Dict[str, Any]],
    response_format: Any,
    tools: Any,
    tool_choice: Any,
) -> Dict[str, Any]:
    contract = dict(mode_contract or {})
    mode = str(contract.get("mode") or "free").lower()
    allow_file_output = bool(contract.get("allow_file_output", False))

    rf = response_format
    tl = tools
    tc = tool_choice

    # Free chat must not carry file-generation contract.
    if mode == "free" and not allow_file_output:
        rf = None
        tl = None
        tc = None

    prov = str(provider or "").lower().strip()
    if prov in {"openai", "azure_openai"} and tl:
        tl = None
        tc = None

    if prov in {"anthropic", "ollama", "deepseek", "vllm"} and rf:
        # keep providers on the tool-oriented path
        rf = None

    return {
        "response_format": rf,
        "tools": tl,
        "tool_choice": tc,
    }