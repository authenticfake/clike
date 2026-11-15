"""The visual foundation of a solution with a user interface: its design system.

A design profile (.clike/design-profiles/) says how a UI must behave (states, accessibility, list/detail);
it is not a visual language, and without one the KIT wrote a few lines of CSS: a working UI nobody wants to
show. The design system gives it one: a component library, its theme tokens, the app shell, the component to
use for each need. It is chosen in TECH_CONSTRAINTS.yaml (`tech_constraints.ui.design_system`), shadcn/ui by
default; a project may add its own guide as .clike/design-systems/<id>.md (a company design system), which also
overrides a bundled one. The same text reaches the cloud prompt and the local agents (services/quality_context.py).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

DEFAULT = "shadcn-ui"
NONE = "none"
BUNDLED_DIR = Path(__file__).resolve().parents[1] / "design_systems"
WORKSPACE_DIR = ".clike/design-systems"
ALIASES = {
    "shadcn": "shadcn-ui", "shadcn/ui": "shadcn-ui", "shadcn-ui": "shadcn-ui", "shadcnui": "shadcn-ui",
    "fluent": "fluent2", "fluent2": "fluent2", "fluent-2": "fluent2", "fluent-ui": "fluent2", "fluentui": "fluent2",
    "carbon": "carbon", "ibm-carbon": "carbon", "carbon-design-system": "carbon",
    "mui": "mui", "material": "mui", "material-ui": "mui", "material-design": "mui", "material3": "mui",
    "antd": "antd", "ant-design": "antd", "ant": "antd",
    "none": NONE, "custom": NONE, "no": NONE,
}
# lanes and design profiles that mean a REQ has a user interface
UI_LANES = frozenset({"typescript", "javascript", "frontend", "web", "react", "nextjs", "next", "vue", "angular", "svelte", "ui"})
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
MAX_GUIDE_CHARS = 12_000


def normalize(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "-")
    return ALIASES.get(text, text)


def _find_key(node: Any, key: str) -> Optional[Any]:
    if isinstance(node, dict):
        if key in node and not isinstance(node[key], (dict, list)):
            return node[key]
        for child in node.values():
            found = _find_key(child, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for child in node:
            found = _find_key(child, key)
            if found is not None:
                return found
    return None


def declared(tech_constraints_text: str) -> str:
    """The design system TECH_CONSTRAINTS names (`ui.design_system`, or `design_system` anywhere), '' if none."""
    try:
        data = yaml.safe_load(tech_constraints_text or "") or {}
    except yaml.YAMLError:
        match = re.search(r"^\s*design_system\s*:\s*['\"]?([^'\"#\n]+)", tech_constraints_text or "", re.MULTILINE)
        return normalize(match.group(1)) if match else ""
    value = _find_key(data, "design_system")
    return normalize(value) if value is not None else ""


def _guide(design_id: str, workspace_root: Optional[Path]) -> str:
    if not _ID_RE.match(design_id):
        return ""
    candidates = []
    if workspace_root is not None:
        candidates.append(Path(workspace_root) / WORKSPACE_DIR / f"{design_id}.md")
    candidates.append(BUNDLED_DIR / f"{design_id}.md")
    for path in candidates:
        try:
            return path.read_text(encoding="utf-8")[:MAX_GUIDE_CHARS].strip()
        except OSError:
            continue
    return ""


def resolve(tech_constraints_text: str, workspace_root: Optional[Path] = None) -> Dict[str, str]:
    """{id, source: tech_constraints | default, guide} — guide '' for `none` or a design system without a guide."""
    named = declared(tech_constraints_text)
    design_id = named or DEFAULT
    return {"id": design_id, "source": "tech_constraints" if named else "default",
            "guide": "" if design_id == NONE else _guide(design_id, workspace_root)}


def has_ui(req: Optional[Dict[str, Any]]) -> bool:
    """A REQ with a user interface: a design profile, or a UI lane."""
    if not isinstance(req, dict):
        return False
    caps = req.get("capabilities") if isinstance(req.get("capabilities"), dict) else {}
    profiles = req.get("design_profiles") or caps.get("design_profiles") or []
    if isinstance(profiles, list) and any(profiles):
        return True
    lanes = [req.get("lane"), *(req.get("lanes") or [])] if isinstance(req.get("lanes"), list) else [req.get("lane")]
    return any(str(lane or "").strip().lower() in UI_LANES for lane in lanes)


def plan_lines(resolved: Dict[str, str]) -> list:
    """For /plan and the cascade: every UI REQ uses the design system; the first one sets it up."""
    if resolved["id"] == NONE:
        return []
    origin = "from TECH_CONSTRAINTS ui.design_system" if resolved["source"] == "tech_constraints" else "CLike's default: TECH_CONSTRAINTS names none"
    return [
        "### UI design system",
        f"- When the solution has a user interface it is built with **{resolved['id']}** ({origin}). The first REQ with a"
        " UI sets it up — packages, theme tokens, the app shell (navigation, header, content area) — and owns it as a"
        " seam; later UI REQs add their screens with its components and tokens, never their own styling system.",
        "- The lane guide of every UI lane names the design system, its setup command and its component conventions.",
    ]


def kit_lines(resolved: Dict[str, str], req_id: str) -> list:
    """For a UI REQ's KIT: the design system guide, whole."""
    if resolved["id"] == NONE:
        return []
    head = [f"## CLIKE QUALITY CONTEXT — UI design system of {req_id}: {resolved['id']}",
            "Build every screen of this REQ with this design system: its components, its theme tokens, the app shell"
            " the first UI REQ set up (extend it, never replace it). No literal colours, sizes or ad-hoc CSS frameworks;"
            " a value the tokens lack is added as a token. The UI states, accessibility and tests of the design profile"
            " still apply."]
    if resolved["guide"]:
        return [*head, "", resolved["guide"], ""]
    return [*head, f"- No CLike guide for `{resolved['id']}`: follow its official documentation for setup, theming"
            " and components (add .clike/design-systems/" + resolved["id"] + ".md to give one).", ""]
