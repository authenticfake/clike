from __future__ import annotations

import re
from typing import Any, Dict, Optional


_PYTHON_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$")


def is_python_runtime_context(
    *,
    lane: Optional[str] = None,
    runtime_profile: Optional[str] = None,
    text: Optional[str] = None,
) -> bool:
    """Return true only when available evidence identifies Python."""
    blob = " ".join(
        [
            str(lane or ""),
            str(runtime_profile or ""),
            str(text or ""),
        ]
    ).lower()
    return any(
        token in blob
        for token in (
            "python",
            "pytest",
            "ruff",
            "mypy",
            "fastapi",
            "pyproject.toml",
            "requirements.txt",
        )
    )


def python_module_boundary_to_package_path(namespace: str) -> str:
    """
    Convert a Python import namespace into its package directory path.

    Python treats dots as import separators, so `coffeebuddy.runtime` must
    materialize as `coffeebuddy/runtime`, not as a literal directory name.
    """
    value = str(namespace or "").strip().replace("\\", "/").strip("/")
    if value.startswith("src/"):
        value = value[len("src/") :].strip("/")
    if value.startswith("test/"):
        value = value[len("test/") :].strip("/")
    if value.startswith("tests/"):
        value = value[len("tests/") :].strip("/")
    if _PYTHON_IDENTIFIER_RE.match(value):
        return value.replace(".", "/")
    return value


def materialize_namespace_path(value: str, *, ecosystem: Optional[str]) -> str:
    """Materialize a namespace-like value only for opted-in ecosystems."""
    if str(ecosystem or "").strip().lower() != "python":
        return str(value or "").strip().replace("\\", "/").strip("/")
    return python_module_boundary_to_package_path(value)


def materialize_repo_path(value: str, *, ecosystem: Optional[str]) -> str:
    """Materialize dotted Python namespaces inside src/test path hints."""
    path = str(value or "").strip().replace("\\", "/").strip("/")
    if str(ecosystem or "").strip().lower() != "python":
        return path

    for prefix in ("src/", "test/", "tests/"):
        if path.startswith(prefix):
            return prefix + python_module_boundary_to_package_path(path[len(prefix) :])
    return python_module_boundary_to_package_path(path)


def namespace_materialization_context(
    *,
    main_module_boundary: Optional[str],
    ecosystem: Optional[str],
    req_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return bounded guidance for cloud prompts and local-agent packages."""
    namespace = str(main_module_boundary or "").strip()
    ecosystem_name = str(ecosystem or "").strip().lower() or "unknown"
    package_path = materialize_namespace_path(namespace, ecosystem=ecosystem_name)
    applies = bool(namespace and ecosystem_name == "python" and package_path != namespace.strip("/"))
    source_root = f"runs/kit/{req_id}/src/{package_path}" if req_id and package_path else f"src/{package_path}" if package_path else ""
    test_root = f"runs/kit/{req_id}/test/{package_path}" if req_id and package_path else f"test/{package_path}" if package_path else ""
    return {
        "ecosystem": ecosystem_name,
        "applies": applies,
        "import_namespace": namespace,
        "package_path": package_path,
        "source_root": source_root,
        "test_root": test_root,
        "rules": [
            "For Python, dotted namespaces are import namespaces, not literal directory names.",
            "Materialize `coffeebuddy.runtime` as `coffeebuddy/runtime`.",
            "Do not create `src/coffeebuddy.runtime`.",
            "Do not insert `src/coffeebuddy.runtime` into sys.path as a package workaround.",
            "Include `__init__.py` files unless the project explicitly uses namespace packages.",
            "Tests must import through the Python namespace, for example `coffeebuddy.runtime`.",
        ]
        if ecosystem_name == "python"
        else [],
    }
