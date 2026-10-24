"""Every rule in the phase texts is a sentence: a rule containing `word: ` unquoted is read by YAML as
a mapping and reached the prompts as a Python dict ("{'Checks and tests …': 'later REQs …'}")."""

from pathlib import Path

import yaml

PHASES = Path(__file__).resolve().parents[1] / "phases"


def _lists(node, path=""):
    if isinstance(node, list):
        yield path, node
        for i, item in enumerate(node):
            yield from _lists(item, f"{path}[{i}]")
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _lists(value, f"{path}.{key}")


def test_no_rule_of_a_phase_text_is_parsed_as_a_mapping():
    found = []
    for path in sorted(PHASES.rglob("*.yaml")):
        for where, items in _lists(yaml.safe_load(path.read_text(encoding="utf-8"))):
            for item in items:
                if isinstance(item, dict) and len(item) == 1 and len(str(next(iter(item)))) > 40:
                    found.append(f"{path.relative_to(PHASES)}{where}: {str(next(iter(item)))[:60]}…")
    assert not found, "quote these rules (a ': ' inside makes them a mapping):\n" + "\n".join(found)
