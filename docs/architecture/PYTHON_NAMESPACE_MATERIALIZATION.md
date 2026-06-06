# Python Namespace Materialization

Python dotted module boundaries are import namespaces, not literal directory names. When a target contract identifies a Python boundary such as `coffeebuddy.runtime`, CLike must materialize it as a package path:

```text
coffeebuddy.runtime -> coffeebuddy/runtime
```

This rule prevents candidate output such as `src/coffeebuddy.runtime/`, which is a directory named with a dot rather than a normal Python package hierarchy.

## Scope

The conversion is Python-specific. It is applied only when runtime evidence identifies a Python ecosystem through target contracts, TECH_CONSTRAINTS, plan metadata, or file-requirement context. Non-Python ecosystems are not rewritten unless their own package semantics explicitly opt in.

## Generated Guidance

For Python KIT runs, the Orchestrator includes namespace materialization context in FILE_REQUIREMENTS and the shared context envelope:

- `ecosystem: python`
- `import_namespace: coffeebuddy.runtime`
- `package_path: coffeebuddy/runtime`
- `source_root: runs/kit/<REQ-ID>/src/coffeebuddy/runtime`

Cloud prompts and local-agent prompts must repeat the rule:

- materialize `coffeebuddy.runtime` as `coffeebuddy/runtime`
- do not create `src/coffeebuddy.runtime`
- do not insert a dotted directory into `sys.path` as a workaround
- include `__init__.py` files unless the project explicitly uses namespace packages
- import tests through `coffeebuddy.runtime`

## Data Path

The namespace helper lives in `orchestrator/utils/namespace_paths.py`. Target contract generation and file requirement generation use it to produce source and test path hints. Gateway renders the same guidance in cloud KIT prompts, and local-agent packages include it in `AGENT_PROMPT.md`.

The rule applies to native and BMAD runs equally. BMAD skill guidance cannot override Python package materialization, just as it cannot override canonical output contracts or CLike write boundaries.
