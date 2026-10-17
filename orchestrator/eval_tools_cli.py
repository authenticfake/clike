"""Eval tools from the command line, inside the orchestrator container (docker/rebuild.sh):

    python -m eval_tools_cli status    # installed tools, versions, whether an update is due
    python -m eval_tools_cli restore   # rebuild from the lock the tools a new volume lacks
    python -m eval_tools_cli update    # rebuild every tool at the latest versions, print the changes

It calls the orchestrator's own API on loopback with the service token of its environment (never
printed). Exit code 0 on success, 1 when something failed (the details are printed).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.getenv("CLIKE_EVAL_TOOLS_CLI_URL", "http://127.0.0.1:8080")


def _call(method: str, path: str, body=None, timeout: float = 3600):
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": "Bearer " + os.getenv("CLIKE_API_TOKEN", ""), "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - loopback
        return json.load(response)


def _versions(record) -> str:
    return ", ".join(f"{k} {v}" for k, v in (record.get("versions") or {}).items()) or "-"


def status() -> int:
    data = _call("GET", "/v1/eval/tools", timeout=30)
    tools = data.get("installed") or {}
    if not tools:
        print("eval tools: none installed (CLike installs them when an eval needs them)")
        return 0
    for name, record in sorted(tools.items()):
        print(f"  {name}: {_versions(record)}")
    days = data.get("updated_days_ago")
    if data.get("update_due"):
        print(f"eval tools: last updated {days} days ago — run ./rebuild.sh --update-tools (or /tools update)")
    elif days is not None:
        print(f"eval tools: updated {days} day(s) ago")
    return 0


def restore() -> int:
    result = _call("POST", "/v1/eval/tools/restore", {})
    if not result.get("lock"):
        print("eval tools: no lock yet, nothing to restore")
    elif result.get("restored"):
        print("eval tools restored from the lock: " + ", ".join(result["restored"]))
    for name, error in (result.get("failed") or {}).items():
        print(f"eval tools: {name} not restored: {error}")
    return 1 if result.get("failed") else 0


def update() -> int:
    result = _call("POST", "/v1/eval/tools/update", {"tools": []})
    changes = result.get("changes") or {}
    if not result.get("updated") and not result.get("failed"):
        print("eval tools: none installed, nothing to update")
    for name, diff in sorted(changes.items()):
        print(f"  {name}: " + ", ".join(f"{pkg} {old or '-'} -> {new}" for pkg, (old, new) in diff.items()))
    if result.get("updated") and not changes:
        print("eval tools: already at the latest versions")
    for name, error in (result.get("failed") or {}).items():
        print(f"eval tools: {name} not updated (the previous version stays): {error}")
    return 1 if result.get("failed") else 0


def main(argv) -> int:
    command = argv[1] if len(argv) > 1 else "status"
    actions = {"status": status, "restore": restore, "update": update}
    if command not in actions:
        print(__doc__)
        return 2
    try:
        return actions[command]()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"eval tools {command}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
