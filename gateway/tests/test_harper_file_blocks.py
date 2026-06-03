import importlib.util
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_ROOT = REPO_ROOT / "gateway"
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))


def _install_route_import_stubs():
    if "fastapi" not in sys.modules:
        fastapi = types.ModuleType("fastapi")

        class HTTPException(Exception):
            def __init__(self, status_code=None, detail=None):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        class APIRouter:
            def __init__(self, *args, **kwargs):
                pass

            def post(self, *args, **kwargs):
                def decorator(func):
                    return func

                return decorator

            def get(self, *args, **kwargs):
                def decorator(func):
                    return func

                return decorator

        fastapi.APIRouter = APIRouter
        fastapi.HTTPException = HTTPException
        fastapi.Request = object
        sys.modules["fastapi"] = fastapi

    if "pydantic" not in sys.modules:
        pydantic = types.ModuleType("pydantic")

        class BaseModel:
            pass

        def Field(default=None, **kwargs):
            return default

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        sys.modules["pydantic"] = pydantic

    if "httpx" not in sys.modules:
        httpx = types.ModuleType("httpx")
        httpx.AsyncClient = object
        sys.modules["httpx"] = httpx

    if "yaml" not in sys.modules:
        yaml = types.ModuleType("yaml")
        yaml.safe_load = lambda value: {}
        yaml.safe_dump = lambda value, **kwargs: str(value)
        sys.modules["yaml"] = yaml

    utils_module = types.ModuleType("utils.utils")
    utils_module.collect_rag_materials_http = lambda *args, **kwargs: []
    utils_module.decide_inline_or_rag = lambda *args, **kwargs: {}
    sys.modules.setdefault("utils.utils", utils_module)

    rag_store = types.ModuleType("utils.rag_store")
    rag_store.RagStore = object
    sys.modules.setdefault("utils.rag_store", rag_store)

    chat = types.ModuleType("routes.chat")
    for name in [
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE",
        "DEEPSEEK_BASE",
        "OLLAMA_BASE",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "OPENAI_BASE",
        "VLLM_BASE",
    ]:
        setattr(chat, name, "")
    chat._json = lambda value: value
    sys.modules.setdefault("routes.chat", chat)

    pricing = types.ModuleType("pricing")
    pricing.PricingManager = object
    sys.modules.setdefault("pricing", pricing)

    providers = types.ModuleType("providers")
    sys.modules.setdefault("providers", providers)
    for provider_name in ["openai_compat", "anthropic", "deepseek", "ollama", "vllm"]:
        module_name = f"providers.{provider_name}"
        provider_module = types.ModuleType(module_name)
        setattr(providers, provider_name, provider_module)
        sys.modules.setdefault(module_name, provider_module)


def _load_harper_route():
    _install_route_import_stubs()
    module_name = "gateway_routes_harper_file_block_tests"
    path = GATEWAY_ROOT / "routes/harper.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


harper = _load_harper_route()
backtick = chr(96)
BT3 = backtick * 3
BT4 = backtick * 4


def _idea_body(name="CoffeeBuddy"):
    return f"""# IDEA — {name}

## Vision
CoffeeBuddy coordinates office coffee runs.

## Problem Statement
Coffee orders are scattered across chat.

## Target Users & Context
- Office teammates coordinating a shared order.

## Value & Outcomes
- Faster shared ordering.

## Out of Scope
- Payments and loyalty integrations.

## Technology Constraints
{BT3}yaml
tech_constraints:
  version: 1
{BT3}

## Risks & Assumptions
- Teams will use a shared link.

## Success Metrics
- First order submitted under 90 seconds.
"""


def test_triple_backtick_outer_with_nested_triple_does_not_create_yaml_tail_artifact():
    raw = f"""{BT3}file:/docs/harper/IDEA.md
{_idea_body()}{BT3}
"""

    files, remainder = harper._extract_file_blocks(raw, phase="idea")

    assert len(files) == 1
    assert files[0]["path"] == "docs/harper/IDEA.md"
    assert files[0]["content"].startswith("# IDEA — CoffeeBuddy")
    assert not files[0]["content"].lstrip().startswith("yaml")
    assert "## Vision" in files[0]["content"]
    assert "## Risks & Assumptions" not in files[0]["content"]
    assert "## Risks & Assumptions" in remainder

    deduped = harper._dedupe_by_path([
        *files,
        {
            "path": "docs/harper/IDEA.md",
            "content": "yaml\ntech_constraints:\n  version: 1\n",
            "source": "fallback",
        },
    ])

    assert len(deduped) == 1
    assert deduped[0]["content"].startswith("# IDEA — CoffeeBuddy")
    assert not deduped[0]["content"].lstrip().startswith("yaml")


def test_four_backtick_outer_with_nested_yaml_preserves_full_idea():
    raw = f"""{BT4}file:/docs/harper/IDEA.md
{_idea_body()}{BT4}
"""

    files, remainder = harper._extract_file_blocks(raw, phase="idea")

    assert remainder == ""
    assert len(files) == 1
    assert files[0]["path"] == "docs/harper/IDEA.md"
    content = files[0]["content"]
    assert content.startswith("# IDEA — CoffeeBuddy")
    assert "## Vision" in content
    assert f"{BT3}yaml" in content
    assert "## Risks & Assumptions" in content
    assert "## Success Metrics" in content
    assert not content.lstrip().startswith("yaml")


def test_begin_file_with_nested_yaml_preserves_internal_fence():
    raw = f"""BEGIN_FILE docs/harper/IDEA.md
# IDEA — CoffeeBuddy

## Technology Constraints
{BT3}yaml
tech_constraints:
  version: 1
{BT3}

## Risks & Assumptions
Risk...
END_FILE
"""

    files, remainder = harper._extract_file_blocks(raw, phase="idea")

    assert remainder == ""
    assert len(files) == 1
    assert files[0]["path"] == "docs/harper/IDEA.md"
    assert files[0]["content"].startswith("# IDEA — CoffeeBuddy")
    assert f"{BT3}yaml" in files[0]["content"]
    assert "tech_constraints:" in files[0]["content"]


def test_begin_file_preserves_full_idea_with_internal_yaml():
    raw = f"""BEGIN_FILE docs/harper/IDEA.md
{_idea_body()}END_FILE
"""

    files, remainder = harper._extract_file_blocks(raw, phase="idea")

    assert remainder == ""
    assert len(files) == 1
    assert files[0]["path"] == "docs/harper/IDEA.md"
    content = files[0]["content"]
    assert content.startswith("# IDEA")
    assert "## Vision" in content
    assert "## Problem Statement" in content
    assert "## Target Users & Context" in content
    assert "## Value & Outcomes" in content
    assert "## Out of Scope" in content
    assert "## Technology Constraints" in content
    assert f"{BT3}yaml" in content
    assert "tech_constraints:" in content
    assert "## Risks & Assumptions" in content
    assert "## Success Metrics" in content
    assert not content.lstrip().startswith("yaml")


def test_begin_file_remainder_fallback_must_not_override_explicit_file():
    raw = f"""BEGIN_FILE docs/harper/IDEA.md
{_idea_body()}END_FILE

yaml
tech_constraints:
  version: 1
"""

    files, remainder = harper._extract_file_blocks(raw, phase="idea")
    assert remainder.lstrip().startswith("yaml")

    deduped = harper._dedupe_by_path([
        *files,
        {
            "path": "docs/harper/IDEA.md",
            "content": remainder,
            "source": "fallback",
        },
    ])

    assert len(deduped) == 1
    assert deduped[0]["content"].startswith("# IDEA")
    assert not deduped[0]["content"].lstrip().startswith("yaml")
    assert "## Vision" in deduped[0]["content"]


def test_four_backtick_remainder_fallback_must_not_override_explicit_file():
    raw = f"""{BT4}file:/docs/harper/IDEA.md
# IDEA — CoffeeBuddy

## Vision
Explicit content.
{BT4}

yaml
tech_constraints:
  version: 1
"""

    files, remainder = harper._extract_file_blocks(raw, phase="idea")
    assert remainder.lstrip().startswith("yaml")

    deduped = harper._dedupe_by_path([
        *files,
        {
            "path": "docs/harper/IDEA.md",
            "content": remainder,
            "source": "fallback",
        },
    ])

    assert len(deduped) == 1
    assert deduped[0]["content"].startswith("# IDEA — CoffeeBuddy")
    assert "Explicit content." in deduped[0]["content"]


def test_duplicate_explicit_path_uses_last_explicit_block():
    raw = f"""BEGIN_FILE docs/harper/IDEA.md
# IDEA — First
END_FILE
BEGIN_FILE /docs/harper/IDEA.md
# IDEA — Second
END_FILE
"""

    files, remainder = harper._extract_file_blocks(raw, phase="idea")
    deduped = harper._dedupe_by_path(files)

    assert remainder == ""
    assert len(files) == 2
    assert len(deduped) == 1
    assert deduped[0]["path"] == "docs/harper/IDEA.md"
    assert deduped[0]["content"].startswith("# IDEA — Second")


def test_path_traversal_file_block_is_rejected():
    raw = "BEGIN_FILE docs/harper/../IDEA.md\n# IDEA — Bad\nEND_FILE\n"

    files, remainder = harper._extract_file_blocks(raw, phase="idea")

    assert files == []
    assert "BEGIN_FILE" in remainder


def test_idea_output_checklist_prefers_begin_file_blocks():
    checklist = harper._output_checklist_for_phase("idea")

    assert "BEGIN_FILE / END_FILE" in checklist
    assert "Markdown file contents may contain fenced code blocks" in checklist
    assert "Do not wrap Markdown files in triple-backtick file blocks when the file itself contains fenced code blocks" in checklist
    assert "Emit one or more `file:/path` blocks with complete file contents" not in checklist


def test_native_plan_file_header_allowlist_rejects_bmad_architecture_companion():
    raw = """BEGIN_FILE docs/harper/bmad/architecture/ARCHITECTURE.md
# Architecture
END_FILE
"""

    files, remainder = harper._extract_file_blocks(raw, phase="plan")

    assert files == []
    assert "BEGIN_FILE docs/harper/bmad/architecture/ARCHITECTURE.md" in remainder


def test_bmad_plan_architect_file_header_allowlist_accepts_architecture_companions():
    context = {
        "methodology": "bmad",
        "phase": "plan",
        "agent": "architect",
        "artifact_policy": {
            "canonical_outputs": ["docs/harper/PLAN.md", "docs/harper/plan.json", "docs/harper/lane-guides/**"],
            "mandatory_companion_outputs": [
                "docs/harper/bmad/architecture/ARCHITECTURE.md",
                "docs/harper/bmad/architecture/DECISIONS.md",
                "docs/harper/bmad/architecture/INTEGRATION_BOUNDARIES.md",
                "docs/harper/bmad/architecture/RISKS.md",
            ],
            "allowed_companion_root_globs": ["docs/harper/bmad/architecture/**"],
        },
    }
    raw = """BEGIN_FILE docs/harper/bmad/architecture/ARCHITECTURE.md
# Architecture
END_FILE
BEGIN_FILE docs/harper/bmad/architecture/DECISIONS.md
# Decisions
END_FILE
BEGIN_FILE docs/harper/bmad/architecture/INTEGRATION_BOUNDARIES.md
# Boundaries
END_FILE
BEGIN_FILE docs/harper/bmad/architecture/RISKS.md
# Risks
END_FILE
"""

    files, remainder = harper._extract_file_blocks(
        raw,
        phase="plan",
        extra_allowed_patterns=harper._methodology_file_header_allow_patterns(context),
    )

    assert remainder == ""
    assert {item["path"] for item in files} == {
        "docs/harper/bmad/architecture/ARCHITECTURE.md",
        "docs/harper/bmad/architecture/DECISIONS.md",
        "docs/harper/bmad/architecture/INTEGRATION_BOUNDARIES.md",
        "docs/harper/bmad/architecture/RISKS.md",
    }


def test_bmad_plan_pm_file_header_allowlist_accepts_plan_companions():
    context = {
        "methodology": "bmad",
        "phase": "plan",
        "agent": "pm",
        "artifact_policy": {
            "canonical_outputs": ["docs/harper/PLAN.md", "docs/harper/plan.json", "docs/harper/lane-guides/**"],
            "mandatory_companion_outputs": [
                "docs/harper/bmad/plan/STORIES.md",
                "docs/harper/bmad/plan/STORY_MAP.md",
                "docs/harper/bmad/plan/IMPLEMENTATION_READINESS.md",
            ],
            "allowed_companion_root_globs": ["docs/harper/bmad/plan/**"],
        },
    }
    raw = """BEGIN_FILE docs/harper/bmad/plan/STORIES.md
# Stories
END_FILE
BEGIN_FILE docs/harper/bmad/plan/STORY_MAP.md
# Story Map
END_FILE
BEGIN_FILE docs/harper/bmad/plan/IMPLEMENTATION_READINESS.md
# Readiness
END_FILE
"""

    files, remainder = harper._extract_file_blocks(
        raw,
        phase="plan",
        extra_allowed_patterns=harper._methodology_file_header_allow_patterns(context),
    )

    assert remainder == ""
    assert {item["path"] for item in files} == {
        "docs/harper/bmad/plan/STORIES.md",
        "docs/harper/bmad/plan/STORY_MAP.md",
        "docs/harper/bmad/plan/IMPLEMENTATION_READINESS.md",
    }


def test_bmad_plan_file_header_allowlist_does_not_trust_src_globs_from_policy():
    context = {
        "methodology": "bmad",
        "phase": "plan",
        "agent": "architect",
        "artifact_policy": {
            "canonical_outputs": ["docs/harper/PLAN.md", "docs/harper/plan.json", "docs/harper/lane-guides/**"],
            "mandatory_companion_outputs": ["docs/harper/bmad/architecture/ARCHITECTURE.md"],
            "allowed_companion_root_globs": ["docs/harper/bmad/architecture/**", "src/**"],
        },
    }
    raw = """BEGIN_FILE src/should_not_be_allowed.py
print("bad")
END_FILE
BEGIN_FILE docs/harper/bmad/architecture/ARCHITECTURE.md
# Architecture
END_FILE
"""

    files, remainder = harper._extract_file_blocks(
        raw,
        phase="plan",
        extra_allowed_patterns=harper._methodology_file_header_allow_patterns(context),
    )

    assert [item["path"] for item in files] == ["docs/harper/bmad/architecture/ARCHITECTURE.md"]
    assert "BEGIN_FILE src/should_not_be_allowed.py" in remainder
