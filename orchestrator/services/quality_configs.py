"""Quality configurations of a KIT (linters, type checkers, test runner options, coverage thresholds,
pre-commit hooks) and whether a change weakens them.

They are locked with the acceptance surface at the first eval: a repair that makes a check pass by
relaxing its configuration (a rule ignored, a strict flag turned off, a path excluded, a threshold
lowered, a hook removed) is rejected, like a weakened ``ci/LTC.json``. Other changes of these files
(a dependency, a new rule, a stricter flag) stay free.

Each format is read into the same model and the two models are compared:

* ``selected``   rule codes, test paths, hooks: one removed is a weakening;
* ``ignored``    rules ignored or disabled, deselected tests, lax overrides: one added is a weakening;
* ``excluded``   paths left out of a check: one added is a weakening (build outputs excepted);
* ``flags``      strictness flags (effective value): true -> false is a weakening;
* ``thresholds`` minimum values (coverage): lowered is a weakening;
* ``severity``   rule levels (off 0, warn 1, error 2): lowered, or a new rule turned off, is a weakening.
"""

from __future__ import annotations

import configparser
import json
import re
import shlex
from typing import Any, Dict, List, Optional, Set

import yaml

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - the orchestrator runs on 3.12
    tomllib = None  # type: ignore[assignment]

_TOML_NAMES = {"pyproject.toml", "ruff.toml", ".ruff.toml"}
_INI_NAMES = {"setup.cfg", "tox.ini", "mypy.ini", ".mypy.ini", "pytest.ini", ".flake8", ".pylintrc", "pylintrc", ".coveragerc"}
_JSONC_RE = re.compile(r"^(?:tsconfig(?:\.[\w.-]+)?|jsconfig|biome)\.jsonc?$")
_ESLINT_DATA_RE = re.compile(r"^\.eslintrc(?:\.(?:json|ya?ml))?$")
_ESLINT_JS_RE = re.compile(r"^(?:eslint\.config|\.eslintrc)\.(?:js|mjs|cjs|ts|mts|cts)$")
_PRE_COMMIT = ".pre-commit-config.yaml"

# Paths a configuration may exclude without weakening a check: build outputs and caches.
_OUTPUT_EXCLUDES = re.compile(
    r"(?:^|[/*])(?:node_modules|dist|build|out|coverage|\.next|\.venv|venv|\.tox|__pycache__|\.mypy_cache|"
    r"\.ruff_cache|\.pytest_cache|htmlcov|\.git|target|\.turbo|\.cache)(?:[/*]|$)"
)

_MYPY_STRICT = (
    "strict", "disallow_untyped_defs", "disallow_incomplete_defs", "disallow_untyped_calls",
    "disallow_untyped_decorators", "disallow_any_generics", "disallow_subclassing_any", "check_untyped_defs",
    "warn_return_any", "warn_unused_ignores", "warn_redundant_casts", "no_implicit_optional", "strict_equality",
    "strict_optional", "warn_unreachable", "extra_checks",
)
_MYPY_DEFAULT_TRUE = {"strict_optional"}

_TS_STRICT_FAMILY = (
    "noImplicitAny", "strictNullChecks", "strictFunctionTypes", "strictBindCallApply",
    "strictPropertyInitialization", "noImplicitThis", "alwaysStrict", "useUnknownInCatchVariables",
)
_TS_FLAGS = (
    "noUnusedLocals", "noUnusedParameters", "noImplicitReturns", "noFallthroughCasesInSwitch",
    "noUncheckedIndexedAccess", "exactOptionalPropertyTypes", "noImplicitOverride",
    "noPropertyAccessFromIndexSignature", "checkJs", "forceConsistentCasingInFileNames",
)

# pytest options that leave tests out of the run.
_PYTEST_LAX = ("--deselect", "--ignore", "--ignore-glob", "-k", "--continue-on-collection-errors")


def is_quality_config(rel: str) -> bool:
    """Whether a KIT-relative path names a quality configuration."""
    name = str(rel or "").replace("\\", "/").rsplit("/", 1)[-1]
    return (
        name in _TOML_NAMES or name in _INI_NAMES or name == _PRE_COMMIT
        or bool(_JSONC_RE.match(name) or _ESLINT_DATA_RE.match(name) or _ESLINT_JS_RE.match(name))
    )


def _model() -> Dict[str, Any]:
    return {"selected": set(), "ignored": set(), "excluded": set(), "flags": {}, "thresholds": {}, "severity": {}}


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[,\n]", value) if part.strip()]
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [str(value)]


def _bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "yes", "on", "1", "false", "no", "off", "0"}:
        return value.strip().lower() in {"true", "yes", "on", "1"}
    return None


def _number(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip().rstrip("%"))
    except (TypeError, ValueError):
        return None


# --- Python tools ---------------------------------------------------------------------------------

def _ruff(m: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    for scope in (cfg, cfg.get("lint") if isinstance(cfg.get("lint"), dict) else {}):
        for key in ("select", "extend-select"):
            m["selected"].update(f"ruff:{c}" for c in _as_list(scope.get(key)))
        for key in ("ignore", "extend-ignore"):
            m["ignored"].update(f"ruff:{c}" for c in _as_list(scope.get(key)))
        for key in ("per-file-ignores", "extend-per-file-ignores"):
            for pattern, codes in (scope.get(key) or {}).items():
                m["ignored"].update(f"ruff:{pattern}:{c}" for c in _as_list(codes))
        for key in ("exclude", "extend-exclude"):
            m["excluded"].update(f"ruff:{p}" for p in _as_list(scope.get(key)))


def _mypy_flags(m: Dict[str, Any], section: Dict[str, Any], prefix: str = "mypy") -> None:
    for flag in _MYPY_STRICT:
        value = _bool(section.get(flag))
        if value is not None:
            m["flags"][f"{prefix}:{flag}"] = value
    if _bool(section.get("ignore_errors")):
        m["ignored"].add(f"{prefix}:ignore_errors")
    m["excluded"].update(f"{prefix}:{p}" for p in _as_list(section.get("exclude")))


def _mypy_override(m: Dict[str, Any], module: str, section: Dict[str, Any]) -> None:
    """A per-module override: only what it relaxes counts (stricter overrides are free)."""
    if _bool(section.get("ignore_errors")):
        m["ignored"].add(f"mypy[{module}]:ignore_errors")
    for flag in _MYPY_STRICT:
        if _bool(section.get(flag)) is False:
            m["ignored"].add(f"mypy[{module}]:{flag}=false")


def _pytest(m: Dict[str, Any], section: Dict[str, Any]) -> None:
    raw = section.get("addopts")
    tokens = raw if isinstance(raw, list) else shlex.split(str(raw or ""), posix=True) if raw else []
    tokens = [str(t) for t in tokens]
    i = 0
    while i < len(tokens):
        token = tokens[i]
        head, _, value = token.partition("=")
        if head in _PYTEST_LAX:
            arg = value or (tokens[i + 1] if i + 1 < len(tokens) and not value and head != "--continue-on-collection-errors" else "")
            m["ignored"].add(f"pytest:{head} {arg}".strip())
            i += 2 if (not value and arg) else 1
            continue
        if head == "-p" and i + 1 < len(tokens) and tokens[i + 1].startswith("no:"):
            m["ignored"].add(f"pytest:-p {tokens[i + 1]}")
            i += 2
            continue
        if head == "--cov-fail-under":
            number = _number(value or (tokens[i + 1] if i + 1 < len(tokens) else ""))
            if number is not None:
                m["thresholds"]["pytest:cov-fail-under"] = number
        i += 1
    warnings = section.get("filterwarnings")
    entries = warnings.splitlines() if isinstance(warnings, str) else [str(x) for x in warnings or []]
    for entry in (e.strip() for e in entries):
        if entry.startswith("error"):
            m["selected"].add(f"pytest:filterwarnings:{entry}")
        elif entry.startswith("ignore"):
            m["ignored"].add(f"pytest:filterwarnings:{entry}")
    paths = section.get("testpaths")
    m["selected"].update(f"pytest:testpaths:{p}" for p in (paths.split() if isinstance(paths, str) else _as_list(paths)))


def _coverage(m: Dict[str, Any], report: Dict[str, Any], run: Dict[str, Any]) -> None:
    number = _number(report.get("fail_under"))
    if number is not None:
        m["thresholds"]["coverage:fail_under"] = number
    m["excluded"].update(f"coverage:{p}" for p in _as_list(run.get("omit")) + _as_list(report.get("omit")))


def _flake8(m: Dict[str, Any], section: Dict[str, Any], tool: str = "flake8") -> None:
    m["selected"].update(f"{tool}:{c}" for c in _as_list(section.get("select")) + _as_list(section.get("extend-select")))
    m["ignored"].update(f"{tool}:{c}" for c in _as_list(section.get("ignore")) + _as_list(section.get("extend-ignore")))
    for line in str(section.get("per-file-ignores") or "").splitlines():
        if ":" in line:
            pattern, codes = line.split(":", 1)
            m["ignored"].update(f"{tool}:{pattern.strip()}:{c}" for c in _as_list(codes))
    m["excluded"].update(f"{tool}:{p}" for p in _as_list(section.get("exclude")) + _as_list(section.get("extend-exclude")))
    number = _number(section.get("max-complexity"))
    if number is not None:
        m["thresholds"][f"{tool}:-max-complexity"] = -number  # a higher limit is laxer


def _toml(text: str, name: str) -> Dict[str, Any]:
    if tomllib is None:
        raise ValueError("tomllib unavailable")
    data = tomllib.loads(text)
    m = _model()
    if name in {"ruff.toml", ".ruff.toml"}:
        _ruff(m, data)
        return m
    tool = data.get("tool") if isinstance(data.get("tool"), dict) else {}
    if isinstance(tool.get("ruff"), dict):
        _ruff(m, tool["ruff"])
    mypy = tool.get("mypy") if isinstance(tool.get("mypy"), dict) else None
    if mypy is not None:
        _mypy_flags(m, mypy)
        for override in mypy.get("overrides") or []:
            if isinstance(override, dict):
                for module in _as_list(override.get("module")):
                    _mypy_override(m, module, override)
    pytest = (tool.get("pytest") or {}).get("ini_options") if isinstance(tool.get("pytest"), dict) else None
    if isinstance(pytest, dict):
        _pytest(m, pytest)
    coverage = tool.get("coverage") if isinstance(tool.get("coverage"), dict) else {}
    _coverage(m, coverage.get("report") or {}, coverage.get("run") or {})
    pylint = tool.get("pylint") if isinstance(tool.get("pylint"), dict) else {}
    control = pylint.get("messages_control") or pylint.get("MESSAGES CONTROL") or {}
    if isinstance(control, dict):
        m["ignored"].update(f"pylint:{c}" for c in _as_list(control.get("disable")))
        m["selected"].update(f"pylint:{c}" for c in _as_list(control.get("enable")))
    return m


def _ini(text: str, name: str) -> Dict[str, Any]:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read_string(text)
    m = _model()
    for section in parser.sections():
        values = dict(parser.items(section))
        lower = section.lower()
        if lower == "mypy":
            _mypy_flags(m, values)
        elif lower.startswith("mypy-"):
            for module in section[5:].split(","):
                _mypy_override(m, module.strip(), values)
        elif lower in {"tool:pytest", "pytest"}:
            _pytest(m, values)
        elif lower in {"flake8", "pycodestyle", "pydocstyle"}:
            _flake8(m, values, lower)
        elif lower in {"coverage:report", "report"} and (name == ".coveragerc" or lower == "coverage:report"):
            _coverage(m, values, {})
        elif lower in {"coverage:run", "run"} and (name == ".coveragerc" or lower == "coverage:run"):
            _coverage(m, {}, values)
        elif lower in {"messages control", "pylint.messages_control"}:
            m["ignored"].update(f"pylint:{c}" for c in _as_list(values.get("disable")))
            m["selected"].update(f"pylint:{c}" for c in _as_list(values.get("enable")))
    return m


# --- JavaScript / TypeScript tools ----------------------------------------------------------------

def _strip_jsonc(text: str) -> str:
    """JSON with comments and trailing commas (tsconfig, biome) as plain JSON."""
    out: List[str] = []
    i, n, in_string = 0, len(text), False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
        else:
            out.append(ch)
            i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


_LEVELS = {"off": 0, "0": 0, "warn": 1, "warning": 1, "info": 1, "1": 1, "error": 2, "2": 2, "on": 2}


def _level(value: Any) -> Optional[int]:
    if isinstance(value, list) and value:
        value = value[0]
    if isinstance(value, dict):
        value = value.get("level")
    if isinstance(value, bool):
        return 2 if value else 0
    return _LEVELS.get(str(value).strip().lower()) if value is not None else None


def _tsconfig(m: Dict[str, Any], data: Dict[str, Any]) -> None:
    options = data.get("compilerOptions") if isinstance(data.get("compilerOptions"), dict) else {}
    strict = _bool(options.get("strict")) is True
    m["flags"]["ts:strict"] = strict
    for flag in _TS_STRICT_FAMILY:
        value = _bool(options.get(flag))
        m["flags"][f"ts:{flag}"] = strict if value is None else value
    for flag in _TS_FLAGS:
        value = _bool(options.get(flag))
        if value is not None:
            m["flags"][f"ts:{flag}"] = value
    m["selected"].update(f"ts:include:{p}" for p in _as_list(data.get("include")))
    m["excluded"].update(f"ts:{p}" for p in _as_list(data.get("exclude")))


def _biome(m: Dict[str, Any], data: Dict[str, Any]) -> None:
    for tool in ("linter", "formatter"):
        section = data.get(tool) if isinstance(data.get(tool), dict) else {}
        if "enabled" in section:
            m["flags"][f"biome:{tool}"] = _bool(section.get("enabled")) is not False
    rules = ((data.get("linter") or {}).get("rules") or {}) if isinstance(data.get("linter"), dict) else {}
    if isinstance(rules, dict):
        if "recommended" in rules:
            m["flags"]["biome:recommended"] = _bool(rules.get("recommended")) is not False
        for group, entries in rules.items():
            if isinstance(entries, dict):
                for rule, value in entries.items():
                    level = _level(value)
                    if level is not None:
                        m["severity"][f"biome:{group}/{rule}"] = level
    files = data.get("files") if isinstance(data.get("files"), dict) else {}
    m["excluded"].update(f"biome:{p}" for p in _as_list(files.get("ignore")) if not str(p).startswith("!"))
    m["excluded"].update(f"biome:{str(p)[1:]}" for p in _as_list(files.get("includes")) if str(p).startswith("!"))


def _eslint_data(m: Dict[str, Any], data: Dict[str, Any], prefix: str = "eslint") -> None:
    for rule, value in (data.get("rules") or {}).items():
        level = _level(value)
        if level is not None:
            m["severity"][f"{prefix}:{rule}"] = level
    m["selected"].update(f"{prefix}:extends:{e}" for e in _as_list(data.get("extends")))
    m["excluded"].update(f"{prefix}:{p}" for p in _as_list(data.get("ignorePatterns")))
    for index, override in enumerate(data.get("overrides") or []):
        if isinstance(override, dict):
            _eslint_data(m, override, f"{prefix}[{','.join(_as_list(override.get('files'))) or index}]")


_JS_OFF_RE = re.compile(r"""['"][\w@/-]+['"]\s*:\s*(?:\[\s*)?(?:['"]off['"]|0\b)""")
_JS_STRING_RE = re.compile(r"""['"]([^'"]+)['"]""")
_JS_IGNORES_RE = re.compile(r"(?:\bignores\s*:\s*|\bglobalIgnores\s*\(\s*|\bignorePatterns\s*:\s*)\[([^\]]*)\]")


def _eslint_js(m: Dict[str, Any], text: str) -> None:
    """A JavaScript config cannot be evaluated here: rules set to off and ignored paths are read from its text."""
    m["ignored"].update(f"eslint:off:{match.group(0).split(':')[0].strip().strip(chr(34) + chr(39))}" for match in _JS_OFF_RE.finditer(text))
    for block in _JS_IGNORES_RE.findall(text):
        m["excluded"].update(f"eslint:{p}" for p in _JS_STRING_RE.findall(block))


def _pre_commit(m: Dict[str, Any], data: Dict[str, Any]) -> None:
    for repo in data.get("repos") or []:
        for hook in (repo or {}).get("hooks") or [] if isinstance(repo, dict) else []:
            if isinstance(hook, dict) and hook.get("id"):
                m["selected"].add(f"pre-commit:{hook['id']}")
    m["excluded"].update(f"pre-commit:{p}" for p in _as_list(data.get("exclude")))


def settings(rel: str, text: str) -> Dict[str, Any]:
    """The quality settings a configuration file declares (raises ValueError when it does not parse)."""
    name = str(rel or "").replace("\\", "/").rsplit("/", 1)[-1]
    try:
        if name in _TOML_NAMES:
            return _toml(text, name)
        if name in _INI_NAMES:
            return _ini(text, name)
        m = _model()
        if _JSONC_RE.match(name):
            data = json.loads(_strip_jsonc(text) or "{}")
            if not isinstance(data, dict):
                raise ValueError("not an object")
            (_biome if name.startswith("biome") else _tsconfig)(m, data)
        elif _ESLINT_DATA_RE.match(name):
            data = (yaml.safe_load(text) if name.endswith((".yml", ".yaml")) else json.loads(_strip_jsonc(text) or "{}")) or {}
            if not isinstance(data, dict):
                raise ValueError("not an object")
            _eslint_data(m, data)
        elif _ESLINT_JS_RE.match(name):
            _eslint_js(m, text)
        elif name == _PRE_COMMIT:
            data = yaml.safe_load(text) or {}
            if not isinstance(data, dict):
                raise ValueError("not a mapping")
            _pre_commit(m, data)
        return m
    except ValueError:
        raise
    except Exception as exc:  # tomllib/configparser/yaml errors
        raise ValueError(str(exc)) from exc


def _real_exclusion(item: str) -> bool:
    return not _OUTPUT_EXCLUDES.search(item.split(":", 1)[-1])


def weakening(rel: str, before: str, after: str) -> List[str]:
    """What the change of a quality configuration relaxes; empty when it relaxes nothing.

    A configuration that parsed before and no longer parses is a weakening (the tool stops or falls
    back to its defaults); one that did not parse before cannot be compared and is not judged."""
    try:
        old = settings(rel, before)
    except ValueError:
        return []
    try:
        new = settings(rel, after)
    except ValueError as exc:
        return [f"the configuration no longer parses ({str(exc)[:120]})"]
    issues: List[str] = []
    removed: Set[str] = old["selected"] - new["selected"]
    issues += [f"no longer enforced: {item}" for item in sorted(removed)]
    issues += [f"now ignored: {item}" for item in sorted(new["ignored"] - old["ignored"])]
    issues += [f"now excluded: {item}" for item in sorted(new["excluded"] - old["excluded"]) if _real_exclusion(item)]
    for flag, value in sorted(old["flags"].items()):
        default = flag.split(":", 1)[-1] in _MYPY_DEFAULT_TRUE
        now = new["flags"].get(flag, default)
        if value and not now:
            issues.append(f"strict flag turned off: {flag}")
    for key, value in sorted(old["thresholds"].items()):
        now = new["thresholds"].get(key)
        if now is None or now < value:
            shown = "removed" if now is None else f"{abs(value):g} -> {abs(now):g}"
            issues.append(f"threshold lowered: {key.replace(':-', ':')} ({shown})")
    for rule, level in sorted(new["severity"].items()):
        before_level = old["severity"].get(rule)
        if before_level is None and level == 0:
            issues.append(f"rule turned off: {rule}")
        elif before_level is not None and level < before_level:
            issues.append(f"rule relaxed: {rule} ({before_level} -> {level})")
    for rule, level in sorted(old["severity"].items()):
        if rule not in new["severity"] and level > 0:
            # an explicit rule dropped falls back to the preset, which may not enforce it
            issues.append(f"rule removed: {rule}")
    return issues
