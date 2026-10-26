"""Native tools of the eval sandbox: which ones a REQ needs, which are missing, how to get them.

The sandbox image carries the language runtimes and the PostgreSQL client. Other native programs a
check may run (kcat, mysqldump, aws, kubectl, mvn, a JDK…) come from a catalog
(``eval_tools_catalog.yaml``, conda-forge packages) and are installed, after the developer's
confirmation, into a tools volume the sandbox mounts read-only (``CLIKE_EVAL_TOOLS_BIN`` on its PATH).

A REQ's needs are found three ways, cheapest first:
* declared: ``environment.tools`` in ci/LTC.json (``["pg_dump", "kcat"]`` or catalog names);
* used: a catalog program the KIT's code, tests or scripts run (a quoted program name, or a
  command line starting with it);
* failed: a check that stopped because a program is missing (``kcat: command not found``,
  ``spawn kcat ENOENT``, ``No such file or directory: 'kcat'``).
A project may add its own entries (other conda-forge packages) in ``.clike/eval-tools.yaml``:

    tools:                      # installed without asking
      - kafkacat
      - jdk@17
    custom:                     # entries of its own, same shape as the catalog
      oracle-sqlcl: {packages: ["sqlcl"], binaries: ["sql"], about: "Oracle SQLcl"}
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

CATALOG_PATH = Path(__file__).with_name("eval_tools_catalog.yaml")
PROJECT_FILE = Path(".clike") / "eval-tools.yaml"
TOOLS_BIN_ENV = "CLIKE_EVAL_TOOLS_BIN"

# conda-forge package specs: name, optionally "=version" / "==version" / ">=…" (no URLs, no paths).
_PACKAGE_SPEC = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,80}(?:(?:==|=|>=|<=|>|<|!=)[A-Za-z0-9_.*+!-]{1,40})?$")
_TOOL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,60}(?:@[A-Za-z0-9_.*+-]{1,40})?$")
_SCANNED_SUFFIXES = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".java", ".kt", ".cs", ".go", ".rb", ".sh", ".bash",
    ".ps1", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".gradle", ".xml",
}
_SKIPPED_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".git", "dist", "build", ".next", "coverage", "reports"}
_MAX_SCANNED = 1500
_COMMON_WORDS = {"go", "jar", "bq", "az", "jq", "yq", "sql", "isql", "helm", "tofu", "cargo", "gradle", "dotnet"}
# short names that are no word: a quoted command with an option counts ("pwsh -NoProfile -File …")
_DISTINCT_SHORT = {"pwsh"}
_MAX_FILE_BYTES = 256 * 1024


def load_catalog(project_root: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """CLike's catalog plus the project's own entries (``custom`` in .clike/eval-tools.yaml)."""
    data = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8")) or {}
    catalog = {str(k): dict(v) for k, v in (data.get("tools") or {}).items() if isinstance(v, dict)}
    for name, entry in (project_config(project_root).get("custom") or {}).items():
        if isinstance(entry, dict) and _TOOL_NAME.match(str(name)):
            catalog[str(name)] = {"group": "project", **entry}
    return catalog


def project_config(project_root: Optional[Path]) -> Dict[str, Any]:
    if not project_root:
        return {}
    path = Path(project_root) / PROJECT_FILE
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def approved_tools(project_root: Optional[Path]) -> List[str]:
    """Tools the project installs without asking (``tools`` in .clike/eval-tools.yaml)."""
    return [str(t) for t in (project_config(project_root).get("tools") or []) if _TOOL_NAME.match(str(t))]


def auto_tools(catalog: Dict[str, Dict[str, Any]]) -> set:
    """Catalog tools every project installs without asking (``auto: true``)."""
    return {name for name, entry in catalog.items() if entry.get("auto") is True}


def tool_for_binary(catalog: Dict[str, Dict[str, Any]], binary: str) -> Optional[str]:
    for name, entry in catalog.items():
        if binary in (entry.get("binaries") or []):
            return name
    return None


def tools_bin_dir() -> Optional[Path]:
    raw = os.getenv(TOOLS_BIN_ENV, "").strip()
    return Path(raw) if raw else None


def search_path(path: Optional[str] = None) -> str:
    """PATH with the tools volume last: an installed tool never shadows the image's own programs."""
    base = path if path is not None else os.environ.get("PATH", "")
    tools = tools_bin_dir()
    if tools is None or str(tools) in base.split(os.pathsep):
        return base
    return f"{base}{os.pathsep}{tools}" if base else str(tools)


def installed_versions() -> Dict[str, Dict[str, str]]:
    """Versions of the tools in the volume this process sees (``installed.json`` next to the bin
    directory): recorded in each eval/gate report, the evidence of what the checks ran with."""
    bin_dir = tools_bin_dir()
    if bin_dir is None:
        return {}
    try:
        import json

        data = json.loads((bin_dir.parent / "installed.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    tools = data.get("tools") if isinstance(data, dict) else None
    return {str(n): dict(r.get("versions") or {}) for n, r in (tools or {}).items() if isinstance(r, dict)}


def available(binary: str) -> bool:
    return shutil.which(binary, path=search_path()) is not None


# --- what a REQ needs ----------------------------------------------------------------------

def declared(ltc: Dict[str, Any]) -> List[str]:
    env = ltc.get("environment") if isinstance(ltc.get("environment"), dict) else {}
    raw = env.get("tools") or ltc.get("tools") or []
    out = []
    for item in raw if isinstance(raw, list) else []:
        name = item.get("name") if isinstance(item, dict) else item
        if name and _TOOL_NAME.match(str(name)):
            out.append(str(name))
    return out


def _iter_files(roots: Iterable[Path]) -> Iterable[Path]:
    count = 0
    for root in roots:
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIPPED_DIRS and not d.startswith(".")]
            for name in filenames:
                path = Path(dirpath) / name
                if path.suffix.lower() in _SCANNED_SUFFIXES or name in {"Makefile", "Dockerfile", "justfile"}:
                    count += 1
                    if count > _MAX_SCANNED:
                        return
                    yield path


def used(roots: Iterable[Path], catalog: Dict[str, Dict[str, Any]]) -> List[str]:
    """Catalog programs the code runs: quoted as a program name ("pg_dump", ['kcat', …]) or at
    the start of a command line (`  aws s3 ls`, `RUN mvn -q test`)."""
    binaries = sorted({b for e in catalog.values() for b in (e.get("binaries") or [])}, key=len, reverse=True)
    if not binaries:
        return []
    alternation = "|".join(re.escape(b) for b in binaries)
    # an exact quoted token ("pg_dump", ['kcat', …]) or a quoted command with an option ("aws --version");
    # short names that are also words (go, jq, az…) only as an exact token or a command line
    long_names = "|".join(re.escape(b) for b in binaries if (len(b) >= 5 or b in _DISTINCT_SHORT) and b not in _COMMON_WORDS) or "(?!)"
    quoted = re.compile(rf"""["'`]({alternation})["'`]|["'`]({long_names})\s+-""")
    command = re.compile(rf"^\s*(?:[-*]\s+|RUN\s+|\$\s+|run:\s*|exec\s+)?({alternation})\s", re.MULTILINE)
    found = set()
    for path in _iter_files(roots):
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        found.update(m.group(1) or m.group(2) for m in quoted.finditer(text))
        if path.suffix.lower() in {".sh", ".bash", ".ps1", ".yml", ".yaml"} or path.name in {"Makefile", "Dockerfile", "justfile"}:
            found.update(m.group(1) for m in command.finditer(text))
    return sorted(found)


_MISSING_PATTERNS = (
    r"(?:^|[\s:/])([\w.+-]+): (?:command )?not found",
    r"\bspawn(?:Sync)? (?:\S*/)?([\w.+-]+) ENOENT",
    r"No such file or directory: '(?:[^']*/)?([\w.+-]+)'",
    r"executable file not found in \$PATH: \"?([\w.+-]+)",
    r"Cannot run program \"([\w.+-]+)\"",
)
_MISSING_RE = re.compile("|".join(_MISSING_PATTERNS), re.MULTILINE)


# A check's own wording ("shellcheck missing", "aws is not installed", "requires terraform"): it
# counts only for a catalog program that really is absent here, so prose cannot invent one.
_SAID_MISSING = r"(?:missing|not installed|not available|unavailable|not found|is required|required)"
_SAYS_REQUIRES = r"(?:missing|install|requires?|needs?)"


def missing_from_failure(text: str, catalog: Dict[str, Dict[str, Any]]) -> List[str]:
    """Catalog programs a check reports missing: the shell's own messages, or the check's wording
    about a catalog program that is absent from the sandbox (B2B REQ-033: a check printed
    "shellcheck missing" and exited, and the repair loop tried to fix the code)."""
    known = {b for e in catalog.values() for b in (e.get("binaries") or [])}
    names = {g for m in _MISSING_RE.finditer(text or "") for g in m.groups() if g}
    body = text or ""
    for binary in known - names:
        word = re.escape(binary)
        said = re.search(rf"(?<![\w.+-]){word}(?![\w.+-])\W{{1,3}}(?:is\s+|was\s+)?{_SAID_MISSING}\b", body, re.IGNORECASE) or \
            re.search(rf"\b{_SAYS_REQUIRES}\W{{1,3}}(?:the\s+)?[`'\"]?{word}(?![\w.+-])", body, re.IGNORECASE)
        if said and not available(binary):
            names.add(binary)
    return sorted(n for n in names if n in known)


def needs(
    project_root: Path, ltc: Dict[str, Any], kit_root: Optional[Path], catalog: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """What the REQ needs that the sandbox lacks: one item per catalog tool (or unknown program).

    ``[{"tool", "binaries", "source": "declared" | "used", "about", "in_catalog"}]``"""
    catalog = catalog if catalog is not None else load_catalog(project_root)
    wanted: Dict[str, Dict[str, Any]] = {}

    def want(name: str, source: str) -> None:
        base = name.split("@", 1)[0]
        tool = base if base in catalog else tool_for_binary(catalog, base)
        key = (tool + name[len(base):]) if tool else name
        if key in wanted:
            return
        entry = catalog.get(tool or "", {})
        binaries = list(entry.get("binaries") or [base])
        if tool and "@" not in name and all(available(b) for b in binaries[:1]):
            return
        if not tool and available(base):
            return
        wanted[key] = {"tool": key, "binaries": binaries, "source": source, "about": entry.get("about", ""),
                       "in_catalog": bool(tool)}

    for name in declared(ltc):
        want(name, "declared")
    roots = [kit_root / sub for sub in ("src", "test", "tests", "ci", "scripts")] if kit_root else []
    for binary in used(roots, catalog):
        want(binary, "used")
    return list(wanted.values())


_RUNTIME_ONLY = re.compile(r"^(python|pip)([=<>!].*)?$")


def _pinned(spec: str, version: str, pip: bool = False) -> str:
    name = re.split(r"[=<>!~]", spec, 1)[0]
    if pip:
        return f"{name}=={version}" if "*" not in version else f"{name}=={version}"
    return f"{name}={version}{'' if '*' in version else '.*'}"


def resolve(names: Iterable[str], catalog: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """One install spec per requested tool (``name``, a program it provides, or ``name@version``):
    ``{"tools": [{name, packages, pip, download, binaries}], "unknown": [...]}``. A version pins
    the entry's ``pin`` package, else its first conda package, else (CLIs from PyPI) its first pip
    package."""
    tools: List[Dict[str, Any]] = []
    unknown: List[str] = []
    for raw in names:
        raw = str(raw).strip()
        if not _TOOL_NAME.match(raw):
            unknown.append(raw)
            continue
        base, _, version = raw.partition("@")
        tool = base if base in catalog else tool_for_binary(catalog, base)
        if not tool:
            unknown.append(raw)
            continue
        entry = catalog[tool]
        packages = [str(p) for p in entry.get("packages") or []]
        pip = [str(p) for p in entry.get("pip") or []]
        download = entry.get("download") if isinstance(entry.get("download"), dict) else {}
        if version:
            pin = str(entry.get("pin") or "")
            conda_real = [p for p in packages if not _RUNTIME_ONLY.match(p)]
            if pin and pin in [re.split(r"[=<>!~]", p, 1)[0] for p in pip]:
                pip = [_pinned(p, version, pip=True) if re.split(r"[=<>!~]", p, 1)[0] == pin else p for p in pip]
            elif pin or conda_real:
                target = pin or re.split(r"[=<>!~]", conda_real[0], 1)[0]
                packages = [_pinned(p, version) if re.split(r"[=<>!~]", p, 1)[0] == target else p for p in packages]
            elif pip:
                pip = [_pinned(pip[0], version, pip=True), *pip[1:]]
        if not (packages or download) or not all(_PACKAGE_SPEC.match(p) for p in packages):
            unknown.append(raw)
            continue
        name = tool + (f"@{version}" if version else "")
        if name not in [t["name"] for t in tools]:
            tools.append({"name": name, "packages": packages, "pip": pip, "download": download,
                          "binaries": [str(b) for b in entry.get("binaries") or []]})
    return {"tools": tools, "unknown": unknown}


def package_spec_ok(spec: str) -> bool:
    return bool(_PACKAGE_SPEC.match(spec or ""))


def check(project_root: Path, req_id: Optional[str], profile: Optional[str] = None) -> Dict[str, Any]:
    """What an eval of the REQ (or of the solution profile) needs and the sandbox lacks."""
    from utils.safe_paths import validate_req_id

    project_root = Path(project_root)
    req_id = validate_req_id(req_id) if req_id else None
    if profile:
        ltc_path = project_root / profile
    elif req_id:
        ltc_path = project_root / "runs" / "kit" / req_id / "ci" / "LTC.json"
    else:
        ltc_path = project_root / "ci" / "SOLUTION_LTC.json"
    try:
        import json

        ltc = json.loads(ltc_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ltc = {}
    kit_root = ltc_path.parent.parent  # runs/kit/<REQ>/ for a KIT, the project root for ci/SOLUTION_LTC.json
    catalog = load_catalog(project_root)
    items = needs(project_root, ltc if isinstance(ltc, dict) else {}, kit_root, catalog)
    approved = set(approved_tools(project_root))
    auto = auto_tools(catalog)
    for item in items:
        base = item["tool"].split("@", 1)[0]
        item["approved"] = item["tool"] in approved or base in approved or base in auto
    # the programs of the auto tools too: a report names the program that was missing ("pwsh")
    auto_install = sorted(auto | {b for t in auto for b in (catalog.get(t, {}).get("binaries") or [])})
    return {"missing": items, "approved": sorted(approved), "auto_install": auto_install}
